import shutil
import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

import media_management.management.commands._media_manager as media_manager

DEFAULT_MEDIA_PATH: str = "./media/"
DEFAULT_TARGET_FORMAT = "webp"
CONVERTABLE_FORMATS = [".jpeg", ".png", ".jpg", ".bmp", ".gif", ".webp", ".avif"]


class Command(BaseCommand):
    help = "Convert media files to webp for smaller size"

    def add_arguments(self, parser):
        parser.add_argument(
            "--media-path", help=f"The path to the media folder. If not provided, {DEFAULT_MEDIA_PATH} is used."
        )
        parser.add_argument(
            "--target-format",
            "-t",
            help=f"The target file format (no dot). If not provided, {DEFAULT_TARGET_FORMAT} is used.",
        )

        parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm conversion")

    def handle(self, *args, **options):
        try:
            self.convert_media(*args, **options)
        except KeyboardInterrupt:
            self.stdout.write(self.style.ERROR("Conversion cancelled."))

    def _get_ffmpeg_command(self, input_file: Path, output_file: Path) -> list[str]:
        return [
            "ffmpeg",
            "-y",
            "-i",
            str(input_file.absolute()),
            str(output_file.absolute()),
        ]

    @transaction.atomic
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
                        (f"Skipping converting {file.name} since it does not appear to be an image format")
                    )
                )
                continue

            target = file.with_suffix(target_format)

            if target.exists():
                self.stderr.write(f"{target.name} already exists! Can't convert {file.name}")
                continue

            to_convert[file] = target
            self.stdout.write(f"Will convert {file.name} to {target.name}")

        if not to_convert:
            self.stderr.write(self.style.ERROR("Nothing to convert!"))
            return

        if not options["yes"] and not media_manager.boolean_input(
            f"Convert {len(to_convert)} files? This will not erase existing files.", default=True
        ):
            self.stdout.write(self.style.ERROR("Conversion cancelled."))
            return

        with tempfile.TemporaryDirectory(prefix="bd-convert-") as tmp_dir_path:
            tmp_dir = Path(tmp_dir_path)

            total = len(to_convert)
            for index, (input_file, output_file) in enumerate(
                to_convert.items(), start=1
            ):
                temp_output = tmp_dir / output_file.name
                self.stdout.write(
                    f"[{index}/{total}] Converting {input_file.name}..."
                )
                command = self._get_ffmpeg_command(
                    input_file,
                    temp_output,
                )
                result = subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if result.returncode != 0:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to convert {input_file.name}."
                        )
                    )

                    raise CommandError(
                        f"ffmpeg exited with non-0 exit code "
                        f"{result.returncode} while converting "
                        f"{input_file.name}!\n\n"
                        f"{result.stderr}"
                    )

                shutil.copy2(temp_output, media_path / output_file.name)
            self.stdout.write(self.style.SUCCESS("Files converted!"))


        for model_instance, model_image, media_attr in medias:
            model_image_path = model_image.absolute()
            if model_image_path in to_convert:
                model_image_field = getattr(model_instance, media_attr)
                new_path = to_convert[model_image_path]

                # Django won't take a non-relative path here
                model_image_field.name = str(new_path.relative_to(media_path.absolute()))
                model_instance.save()

        self.stdout.write(self.style.SUCCESS("Database updated!"))
        self.stdout.write("You may want to run remove_unused_media to remove the old copies.")
        self.stdout.write("Remember to reloadcache to apply!")
