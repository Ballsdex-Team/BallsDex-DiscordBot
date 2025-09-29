from pathlib import Path

import media_management.management.commands._media_manager as media_manager
from django.core.management.base import BaseCommand, CommandError

DEFAULT_MEDIA_PATH: str = "./media/"


class Command(BaseCommand):
    help = "Remove unused files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--media-path",
            help=f"The path to the media folder."
            f"If not provided, {DEFAULT_MEDIA_PATH} is used.",
        )
        parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm deletion")

    def handle(self, *args, **options):
        self.remove_unused_media(*args, **options)

    def remove_unused_media(self, *args, **options):
        media_path = Path(options.get("media_path") or DEFAULT_MEDIA_PATH)
        if not media_path.exists():
            raise CommandError("Provided media-path does not exist.")

        medias = media_manager.all_media()
        used_paths: set[Path] = set()
        used_paths.update([path for (_, path, _) in medias])

        unused_files = []
        for file in Path(media_path).iterdir():
            if not file.is_file():
                continue
            # Django path is absolute so this has to be as well
            if file.absolute() not in used_paths:
                unused_files.append(file)

        if unused_files:
            self.stdout.write(
                f"Unused files: \n - {'\n - '.join(file.name for file in unused_files)}"
            )
        else:
            self.stdout.write("No unused files!")
            return

        if options["yes"] or media_manager.boolean_input(
            "Do you want to remove all of these files? "
            + self.style.WARNING("WARNING: there is no going back from this."),
            default=False,
        ):
            for file in unused_files:
                self.stdout.write(f"Removed {file.name}")
                file.unlink()
        else:
            self.stdout.write("Aborting")
