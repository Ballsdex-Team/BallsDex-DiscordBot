import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from eventpass_app.loader import PassLoader

PASSES = Path(__file__).resolve().parents[2] / "passes"


class Command(BaseCommand):
    help = "Build an event pass from a JSON file, or update the draft it built before"

    def add_arguments(self, parser):
        parser.add_argument(
            "file",
            type=str,
            help='Path to the JSON file, or the name of a file of eventpass_app/passes, like "birthday_voyage"',
        )
        parser.add_argument("--dry-run", action="store_true", help="Check the file without saving anything")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            path = PASSES / f"{options['file'].removesuffix('.json')}.json"
        if not path.exists():
            raise CommandError(f"File not found: {options['file']}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise CommandError(f"{path.name} is not valid JSON: {error}") from error

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
