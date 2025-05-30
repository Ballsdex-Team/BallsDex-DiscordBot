import asyncio
from pathlib import Path

from bd_models.models import Ball, Economy, Regime, Special
from django.core.management.base import BaseCommand

MEDIA_PATH: str = "./media/"


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.remove_unused_media(*args, **options))

    async def remove_unused_media(self, *args, **options):
        used_paths = set()

        ball: Ball
        async for ball in Ball.objects.all():
            used_paths.add(ball.wild_card)
            used_paths.add(ball.collection_card)

        special: Special
        async for special in Special.objects.all():
            used_paths.add(special.background)

        economy: Economy
        async for economy in Economy.objects.all():
            used_paths.add(economy.icon)

        regime: Regime
        async for regime in Regime.objects.all():
            used_paths.add(regime.background)

        unused_files = []
        for file in Path(MEDIA_PATH).iterdir():
            if file.name not in used_paths:
                unused_files.append(file)

        if unused_files:
            self.stderr.write(
                f"Unused files: \n - {"\n - ".join(file.name for file in unused_files)}"
            )
        else:
            self.stderr.write("No unused files!")
