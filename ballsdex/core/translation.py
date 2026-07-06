"""
Runtime translation primitives: gettext catalog loading, and the ambient "current
interaction locale" used to translate UI strings (embeds, messages, view labels) as
they're written, following the Discord client locale of whoever is interacting.

This module intentionally has no Django dependency: it's imported from
`ballsdex.core.discord`, which is itself imported from Django model files
(`bd_models.models`), so importing anything Django-dependent here would create an
import cycle.

This is unrelated to countryball display language (`ballsdex.core.i18n.resolve_locale`),
which is gated to an explicitly configured language, never an arbitrary client locale.
See that module's docstring for the full picture.
"""

import contextvars
import gettext
import logging
from pathlib import Path

log = logging.getLogger("ballsdex.core.translation")

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
DOMAIN = "ballsdex"

_catalogs: dict[str, gettext.GNUTranslations] = {}

# Set once per interaction (see ballsdex.core.discord and ballsdex.core.bot.CommandTree)
# so call sites don't need to thread an interaction/locale through every function.
current_locale: contextvars.ContextVar[str] = contextvars.ContextVar("current_locale", default="en-US")


def load_catalogs() -> None:
    """
    Load every compiled `.mo` catalog under `LOCALES_DIR` into memory, keyed by the
    directory name (expected to be a `discord.Locale` value, e.g. "fr", "es-ES").
    """
    _catalogs.clear()
    if not LOCALES_DIR.is_dir():
        return
    for locale_dir in LOCALES_DIR.iterdir():
        mo_path = locale_dir / "LC_MESSAGES" / f"{DOMAIN}.mo"
        if not mo_path.is_file():
            continue
        with mo_path.open("rb") as f:
            _catalogs[locale_dir.name] = gettext.GNUTranslations(f)
    if _catalogs:
        log.info(f"Loaded {len(_catalogs)} translation catalog(s): {', '.join(sorted(_catalogs))}")


def gettext_translate(message: str, locale: str) -> str | None:
    """
    Look up `message` in the catalog for `locale`.

    Returns `None` (instead of the original text) if no catalog is loaded for this
    locale, or if the message has no translation entry, so the caller can fall back
    to the original string.
    """
    catalog = _catalogs.get(locale)
    if catalog is None:
        return None
    translated = catalog.gettext(message)
    return translated if translated != message else None


def t(message: str) -> str:
    """
    Translate a runtime UI string into the current interaction's Discord client locale.

    Not named `_` on purpose: this codebase uses `_` pervasively as a throwaway variable
    (e.g. `player, _ = await Player.objects.aget_or_create(...)`), which would silently
    turn every such function into an `UnboundLocalError` trap if `_` were also imported
    as a module-level callable there.

    Falls back to `message` unchanged if there is no catalog for the current locale, or
    no translation entry for it.
    """
    return gettext_translate(message, current_locale.get()) or message
