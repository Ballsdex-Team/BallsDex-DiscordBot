import sys
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError

from settings.models import Settings
from settings.services.yml_import import import_settings_from_yaml


class Command(BaseCommand):
    help = "Import config.yml from a file or stdin"

    def add_arguments(self, parser):
        parser.add_argument("file", nargs="?", type=str, help="Path to config.yml file")

    def handle(self, *args, **options):
        if options["file"]:
            path = Path(options["file"])
            if not path.exists():
                raise CommandError(f"File not found: {path}")
            raw = path.read_text()
        elif not sys.stdin.isatty():
            raw = sys.stdin.read()
        else:
            raise CommandError("Provide a file path or pipe input via stdin")

        content = yaml.load(raw, yaml.Loader)

        s = Settings.objects.first()
        if not s:
            raise CommandError("No settings instance found")

        import_settings_from_yaml(content, s)

        self.stdout.write(self.style.SUCCESS("Settings imported successfully"))
