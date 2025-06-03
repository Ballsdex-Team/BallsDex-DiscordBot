from pathlib import Path

from bd_models.models import Ball, Economy, Regime, Special
from django.core.management.base import BaseCommand, CommandError

DEFAULT_MEDIA_PATH: str = "./media/"


class Command(BaseCommand):
    help = "Remove unused files"

    def boolean_input(self, question, default=None):
        query = f"{question} [{'y/n' if default is None else ('Y/n' if default else 'y/N')}]: "
        result = None
        while not result:
            result = input(query)
            if result == "" and default is not None:
                return default
            if result.lower() in ["y", "yes", "yeah", "yay", "ya"]:
                return True
            elif result.lower() in ["n", "no", "nay", "nah"]:
                return False

    def add_arguments(self, parser):
        parser.add_argument(
            "--media-path",
            help=f"The path to the media folder."
            f"If not provided, {DEFAULT_MEDIA_PATH} is used.",
        )

    def handle(self, *args, **options):
        self.remove_unused_media(*args, **options)

    def remove_unused_media(self, *args, **options):
        used_paths = set()

        used_paths.update(Ball.objects.values_list("wild_card", flat=True))
        used_paths.update(Ball.objects.values_list("collection_card", flat=True))
        used_paths.update(Special.objects.values_list("background", flat=True))
        used_paths.update(Economy.objects.values_list("icon", flat=True))
        used_paths.update(Regime.objects.values_list("background", flat=True))

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

        if self.boolean_input("Do you want to remove these files?"):
            for file in unused_files:
                if self.boolean_input(f"Remove {file.name}?", default=True):
                    file.unlink()
