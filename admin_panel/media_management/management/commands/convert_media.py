import shutil
import subprocess
from pathlib import Path

import media_management.management.commands._media_manager as media_manager
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

DEFAULT_MEDIA_PATH: str = "./media/"
DEFAULT_TARGET_FORMAT = "webp"
CONVERTABLE_FORMATS = [".jpeg", ".png", ".jpg", ".bmp", ".gif", ".webp", ".avif"]


class Command(BaseCommand):
    help = "Remove unused files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--media-path",
            help=f"The path to the media folder."
            f"If not provided, {DEFAULT_MEDIA_PATH} is used.",
        )
        parser.add_argument(
            "--target-format",
            "-t",
            help="The target file format (no dot)."
            f"If not provided, {DEFAULT_TARGET_FORMAT} is used.",
        )

        parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm conversion")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            self.convert_media(*args, **options)
        except KeyboardInterrupt:
            self.stdout.write(self.style.ERROR("Conversion cancelled."))

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
        media_path = Path(options.get("media_path") or DEFAULT_MEDIA_PATH)
        if not media_path.exists():
            raise CommandError("Provided media-path does not exist.")

        medias = media_manager.all_media()

        to_convert: dict[Path, Path] = {}

        target_format: str = "." + (options.get("target_format") or DEFAULT_TARGET_FORMAT)

        for model_instance, model_image, media_attr in medias:
            file = Path(model_image).absolute()
            if file.suffix == target_format:
                continue

            if file.suffix not in CONVERTABLE_FORMATS:
                self.stdout.write(
                    self.style.WARNING(
                        (
                            f"Skipping converting {file.name} since it does "
                            "not appear to be an image format"
                        )
                    )
                )

            target = file.with_suffix(target_format)

            if target.exists():
                self.stderr.write(f"{target.name} already exists! Can't convert {file.name}")
                continue

            to_convert[file] = target
            self.stdout.write(f"Will convert {file.name} to {target.name}")

        self.stdout.write("")
        if not options["yes"] and not media_manager.boolean_input(
            f"Convert {len(to_convert)} files? This will not erase existing files.",
            default=True,
        ):
            self.stdout.write(self.style.ERROR("Conversion cancelled."))
            return

        tmp_dir = Path("/tmp/bd-convert-dest")
        try:
            shutil.rmtree(tmp_dir)
        except FileNotFoundError:
            pass
        tmp_dir.mkdir()

        if to_convert:
            command = self._get_ffmpeg_command(
                {src: (tmp_dir / target.name).absolute() for src, target in to_convert.items()}
            )

            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode != 0:
                raise CommandError(f"FFmpeg exited with non-0 exit code {result.returncode}!")

            self.stdout.write(self.style.SUCCESS("Files converted!"))
            shutil.copytree(tmp_dir, media_path, dirs_exist_ok=True)
            self.stdout.write(self.style.SUCCESS("Moved files to media dir!"))

            for model_instance, model_image, media_attr in medias:
                model_image_path = model_image.absolute()
                if model_image_path in to_convert:
                    model_image_field = getattr(model_instance, media_attr)
                    new_path = to_convert[model_image_path]

                    # Django won't take a non-relative path here
                    model_image_field.name = str(new_path.relative_to(media_path.absolute()))
                    model_instance.save()

            self.stdout.write(self.style.SUCCESS("Database updated!"))
            self.stdout.write("You may want to run remove_unused_files to remove the old copies.")
