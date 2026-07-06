"""
Extracts every translatable string into a single gettext POT template, from two sources:

1. The command tree (command/group names and descriptions, parameter names and
   descriptions, choice names). discord.py resolves a command's description from its
   docstring (parsed and shortened) before ever handing it to `ballsdex.core.bot.Translator`,
   so re-deriving those exact strings via static analysis of source files would mean
   duplicating that parsing logic and risks drifting out of sync with it. Instead, this
   loads the bot's bundled command packages and walks the live, already-resolved command
   tree - the exact same strings `Translator.translate` will be asked to translate at
   runtime. This does not connect to Discord: it only builds a local `BallsDexBot`
   instance and loads cogs, which needs a database connection but no bot token or
   gateway connection. Third-party/extra packages (installed as separate Django apps)
   are not covered.
2. Runtime UI strings wrapped in `ballsdex.core.translation.t(...)`, found via a static
   scan of the `ballsdex` package.
"""

import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.extract import extract_from_dir
from babel.messages.pofile import write_po
from discord.ext import commands
from django.core.management.base import BaseCommand, CommandParser

from ballsdex.core.bot import DEFAULT_PACKAGES, BallsDexBot
from ballsdex.core.translation import DOMAIN, LOCALES_DIR
from settings.models import load_settings

log = logging.getLogger(__name__)

AddFn = Callable[..., None]


class Command(BaseCommand):
    help = "Extract translatable strings (command tree + runtime t() calls) into a gettext POT template."

    def add_arguments(self, parser: CommandParser):
        parser.add_argument(
            "-o", "--output", type=str, default=None, help="Output .pot path, defaults to ballsdex/locales/ballsdex.pot"
        )

    def handle(self, *args, **options):
        load_settings()
        asyncio.run(self.extract(options["output"]))

    async def extract(self, output: str | None):
        catalog = Catalog(project="BallsDex", charset="utf-8")
        seen: set[str] = set()

        def add(
            message: str | None, *, locations: Sequence[tuple[str, int]] = (), comments: Sequence[str] = ()
        ) -> None:
            if not message or message in seen:
                return
            seen.add(message)
            catalog.add(message, locations=list(locations), auto_comments=list(comments))

        await self._extract_command_tree(add)
        self._extract_runtime_strings(add)

        output_path = Path(output) if output else LOCALES_DIR / f"{DOMAIN}.pot"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as f:
            write_po(f, catalog, width=0)

        self.stdout.write(self.style.SUCCESS(f"Extracted {len(seen)} strings into {output_path}"))

    async def _extract_command_tree(self, add: AddFn) -> None:
        bot = BallsDexBot(command_prefix=commands.when_mentioned)

        loaded_packages = []
        for package_name, path in DEFAULT_PACKAGES:
            try:
                await bot.load_extension(path)
            except Exception:
                log.exception(f"Failed to load package {package_name!r}, its strings will be missing from extraction")
            else:
                loaded_packages.append(package_name)
        self.stdout.write(f"Loaded {len(loaded_packages)}/{len(DEFAULT_PACKAGES)} packages to walk the command tree.")

        for command in bot.tree.walk_commands():
            add(command.name, comments=[f"Name of /{command.qualified_name}"])
            add(command.description, comments=[f"Description of /{command.qualified_name}"])
            for param in getattr(command, "parameters", ()):
                add(param.name, comments=[f"Parameter of /{command.qualified_name}"])
                add(param.description, comments=[f"Parameter description of /{command.qualified_name}"])
                for choice in param.choices or ():
                    add(choice.name, comments=[f"Choice of /{command.qualified_name} {param.name}"])

    def _extract_runtime_strings(self, add: AddFn) -> None:
        ballsdex_dir = LOCALES_DIR.parent
        for filename, lineno, message, comments, _context in extract_from_dir(ballsdex_dir, keywords={"t": None}):
            if isinstance(message, tuple):  # pragma: no cover - t() only ever takes a single string argument
                continue
            add(message, locations=[(f"ballsdex/{filename}", lineno)], comments=list(comments))
