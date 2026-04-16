import sys

import yaml
from django.core.management.base import BaseCommand, CommandError

from settings.models import Settings
from settings.services.yml_import import import_settings_from_yaml


class Command(BaseCommand):
    help = "Import config.yml from stdin"

    def handle(self, *args, **options):
        if sys.stdin.isatty():
            raise CommandError("No input provided")

        raw = sys.stdin.read()
        content = yaml.load(raw, yaml.Loader)

        s = Settings.objects.first()
        if not s:
            raise CommandError("No settings instance found")

        import_settings_from_yaml(content, s)
        s.save()

        self.stdout.write(self.style.SUCCESS("Settings imported successfully"))
