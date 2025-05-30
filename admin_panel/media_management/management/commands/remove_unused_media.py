import asyncio
from pathlib import Path

from bd_models.models import Ball, Economy, Regime, Special
from django.core.management.base import BaseCommand, CommandError

DEFAULT_MEDIA_PATH: str = "./media/"


class Command(BaseCommand):
    help = "Remove unused files"

    def boolean_input(self, question, default=None):
        result = input("%s " % question)
        if not result and default is not None:
            return default
        while len(result) < 1 or result[0].lower() not in "yn":
            result = input("Please answer yes or no: ")
        return result[0].lower() == "y"

    def add_arguments(self, parser):
        parser.add_argument(
            "--media-path",
            help=f"The path to the media folder."
            f"If not provided, {DEFAULT_MEDIA_PATH} is used.",
        )

    def handle(self, *args, **options):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.remove_unused_media(*args, **options))

    async def remove_unused_media(self, *args, **options):
        used_paths = set()

        used_paths.update(
            [filename async for filename in Ball.objects.values_list("wild_card", flat=True)]
        )
        used_paths.update(
            [filename async for filename in Ball.objects.values_list("collection_card", flat=True)]
        )
        used_paths.update(
            [filename async for filename in Special.objects.values_list("background", flat=True)]
        )
        used_paths.update(
            [filename async for filename in Economy.objects.values_list("icon", flat=True)]
        )
        used_paths.update(
            [filename async for filename in Regime.objects.values_list("background", flat=True)]
        )

        unused_files = []
        if not (media_path := options.get("media-path")):
            media_path = DEFAULT_MEDIA_PATH

        if not Path(media_path).exists():
            raise CommandError("Provided media-path does not exist.")

        for file in Path(media_path).iterdir():
            if file.name not in used_paths:
                unused_files.append(file)

        if unused_files:
            self.stdout.write(
                f"Unused files: \n - {"\n - ".join(file.name for file in unused_files)}"
            )
        else:
            self.stdout.write("No unused files!")
            return

        if self.boolean_input("Do you want to remove these files? [y/n]: "):
            for file in unused_files:
                if self.boolean_input(f"Remove {file.name}? [y/n]: ", default=True):
                    file.unlink()
