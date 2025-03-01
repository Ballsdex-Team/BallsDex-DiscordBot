import asyncio
import os
import sys

from django.core.management.base import BaseCommand, CommandError, CommandParser
from tortoise.exceptions import DoesNotExist

from ballsdex.core.image_generator.image_gen import draw_card
from ballsdex.core.models import Ball, BallInstance, Special
from ballsdex.settings import settings

from ...utils import refresh_cache


class Command(BaseCommand):
    help = (
        "Generate a local preview of a card. This will use the system's image viewer "
        "or print to stdout if the output is being piped."
    )

    def add_arguments(self, parser: CommandParser):
        parser.add_argument(
            "--ball",
            help=f"The name of the {settings.collectible_name} you want to generate. "
            "If not provided, the first entry is used.",
        )
        parser.add_argument(
            "--special",
            help="The special event's background you want to use, otherwise regime is used",
        )

    async def generate_preview(self, *args, **options):
        await refresh_cache()

        if ball_name := options.get("ball"):
            try:
                ball = await Ball.get(country__iexact=ball_name)
            except DoesNotExist as e:
                raise CommandError(
                    f'No {settings.collectible_name} found with the name "{ball_name}"'
                ) from e
        else:
            ball = await Ball.first()
            if ball is None:
                raise CommandError(f"You need at least one {settings.collectible_name} created.")

        special = None
        if special_name := options.get("special"):
            try:
                special = await Special.get(name__iexact=special_name)
            except DoesNotExist as e:
                raise CommandError(f'No special found with the name "{special_name}"') from e

        # use stderr to avoid piping
        self.stderr.write(
            self.style.SUCCESS(
                f"Generating card for {ball.country}" + (f" ({special.name})" if special else "")
            )
        )

        instance = BallInstance(ball=ball, special=special)
        image = draw_card(instance, media_path="./media/")

        if sys.platform not in ("win32", "darwin") and not os.environ.get("DISPLAY"):
            self.stderr.write(
                self.style.WARNING(
                    "\nThis command displays the generated card using your system's image viewer, "
                    "but no display was detected. Are you running this inside Docker?\n"
                    'You can append "> image.png" at the end of your command to instead write the '
                    "image to disk, which you can then open manually.\n"
                )
            )
            raise CommandError("No display detected.")
        if sys.stdout.isatty():
            image.show(title=ball.country)
        else:
            image.save(sys.stdout.buffer, "png")

    def handle(self, *args, **options):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.generate_preview(*args, **options))
