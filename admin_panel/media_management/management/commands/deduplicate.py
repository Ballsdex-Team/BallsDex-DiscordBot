import hashlib
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction

import media_management.management.commands._media_manager as media_manager

DEFAULT_MEDIA_PATH: str = "./media/"


def sha1sum(file: Path) -> str:
    sha1 = hashlib.sha1()
    with file.open("rb") as f:
        while chunk := f.read(65536):
            sha1.update(chunk)
    return sha1.hexdigest()


class Command(BaseCommand):
    help = "Deduplicate files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--media-path", help=f"The path to the media folder.If not provided, {DEFAULT_MEDIA_PATH} is used."
        )
        parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm deletion")

    def handle(self, *args, **options):
        try:
            self.deduplicate_media(*args, **options)
        except KeyboardInterrupt:
            self.stdout.write(self.style.ERROR("Deduplication cancelled."))

    def deduplicate_media(self, *args, **options):
        media_path = Path(options.get("media_path") or DEFAULT_MEDIA_PATH)
        if not media_path.exists():
            raise CommandError("Provided media-path does not exist.")

        medias = media_manager.all_media()

        references: dict[Path, list[tuple[models.Model, str]]] = defaultdict(list)
        for model_instance, path, media_attr in medias:
            references[path.absolute()].append((model_instance, media_attr))

        files_by_hash: dict[str, list[Path]] = defaultdict(list)
        for file in references:
            if not file.is_file():
                self.stderr.write(self.style.WARNING(f"Skipping {file.name} since it does not exist"))
                continue
            files_by_hash[sha1sum(file)].append(file)

        to_replace: dict[Path, Path] = {}
        for files in files_by_hash.values():
            if len(files) < 2:
                continue
            # keep the most referenced file
            files.sort(key=lambda f: (-len(references[f]), f.name))
            kept, *duplicates = files
            self.stdout.write(f"Keeping {kept.name}, duplicates: {', '.join(f.name for f in duplicates)}")
            for duplicate in duplicates:
                to_replace[duplicate] = kept

        if not to_replace:
            self.stdout.write("No duplicate files!")
            return

        if not options["yes"] and not media_manager.boolean_input(
            f"Remove {len(to_replace)} duplicate files and update the database?",
            default=False,
        ):
            self.stdout.write(self.style.ERROR("Deduplication cancelled."))
            return

        with transaction.atomic():
            for duplicate, kept in to_replace.items():
                kept_instance, kept_attr = references[kept][0]
                kept_name = getattr(kept_instance, kept_attr).name

                for model_instance, media_attr in references[duplicate]:
                    getattr(model_instance, media_attr).name = kept_name
                    model_instance.save(update_fields=[media_attr])

        self.stdout.write(self.style.SUCCESS("Database updated!"))

        # only delete the files once the DB no longer references them
        for duplicate in to_replace:
            duplicate.unlink()
            self.stdout.write(f"Removed {duplicate.name}")

        self.stdout.write(self.style.SUCCESS(f"Removed {len(to_replace)} duplicate files!"))
