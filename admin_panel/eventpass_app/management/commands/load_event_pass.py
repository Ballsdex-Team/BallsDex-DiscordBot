import json
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from eventpass_app.loader import PassLoader


class Command(BaseCommand):
    help = "Build an event pass from a JSON file, or update the draft it built before"

    def add_arguments(self, parser):
        parser.add_argument(
            "file", type=str, help='Path to the JSON file, or "-" to read it from stdin (see eventexample/README.md)'
        )
        parser.add_argument("--dry-run", action="store_true", help="Check the file without saving anything")

    def handle(self, *args, **options):
        if options["file"] == "-":
            raw = sys.stdin.buffer.read()
        else:
            path = Path(options["file"])
            if not path.exists():
                raise CommandError(f"File not found: {path}")
            raw = path.read_bytes()
        try:
            # utf-8-sig: a file saved by Notepad or piped by PowerShell starts with a byte order mark
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CommandError(f"This is not a valid JSON file: {error}") from error

        loader = PassLoader(data)
        # one transaction for the whole pass: a single mistake in the file and nothing at all is saved
        with transaction.atomic():
            loader.load()
            if loader.errors or options["dry_run"]:
                transaction.set_rollback(True)

        if loader.errors:
            raise CommandError("Nothing was saved:\n" + "\n".join(f"- {error}" for error in loader.errors))
        for line in loader.report:
            self.stdout.write(line)
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("The file is valid. Dry run: nothing was saved."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{loader.event_pass} is saved, as a draft until you publish it."))
