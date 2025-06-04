import subprocess
from pathlib import Path

import media_management.management.commands._media_manager as media_manager
from django.core.management.base import BaseCommand, CommandError

DEFAULT_MEDIA_PATH: str = "/code/admin_panel/media/"
TARGET_FORMAT = ".webp"


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
        self.convert_media(*args, **options)

    def _get_ffmpeg_command(self, to_convert: dict[Path, Path]) -> list[str]:
        command: list[str] = ["ffmpeg"]
        inputs: list[str] = []
        outputs: list[str] = []

        for i, (input_file, output_file) in enumerate(to_convert.items()):
            inputs.append("-i")
            inputs.append(str(input_file.absolute()))

            outputs.append("-map")
            outputs.append(str(i))
            outputs.append(str(output_file.absolute()))

        command.extend(inputs)
        command.extend(outputs)

        return command

    def convert_media(self, *args, **options):
        media_path = Path(options.get("media-path") or DEFAULT_MEDIA_PATH)
        if not media_path.exists():
            raise CommandError("Provided media-path does not exist.")

        medias = media_manager.all_media()

        to_convert: dict[Path, Path] = {}

        for model_instance, model_image, media_attr in medias:
            file = Path(model_image).absolute()
            if file.suffix == TARGET_FORMAT:
                continue

            target = file.with_suffix(TARGET_FORMAT)

            if target.exists():
                self.stderr.write(f"{target.name} already exists! Can't convert {file.name}")
                continue

            if options["yes"] or media_manager.boolean_input(
                f"Convert {file.name} to {file.stem}.webp?", default=True
            ):
                to_convert[file] = target

        if to_convert:
            command = self._get_ffmpeg_command(to_convert)
            print(command)

            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode != 0:
                self.stderr.write(f"FFmpeg exited with non-0 exit code {result.returncode}!")
                self.stderr.write(result.stderr)
                raise CommandError()

            self.stdout.write("Files converted!")

            for model_instance, model_image, media_attr in medias:
                model_image_path = model_image.absolute()
                if model_image_path in to_convert:
                    model_image_field = getattr(model_instance, media_attr)
                    new_path = to_convert[model_image_path]

                    # Django won't take a non-relative path here
                    model_image_field.name = str(new_path.relative_to(media_path))
                    model_instance.save()

            self.stdout.write("Database updated!")
            self.stdout.write("You may want to run remove_unused_files to remove the old copies.")
