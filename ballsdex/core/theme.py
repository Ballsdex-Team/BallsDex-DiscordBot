"""
Bot-wide color theme.

Everything in this repository uses `settings.embed_colour` directly. Third-party packages installed
through `extra.toml` cannot be edited from here though, and most of them hardcode
`discord.Colour.blurple()` for their embeds. `apply_theme` redirects that color to the configured
one so every embed sent by the bot shares the same color.
"""

import discord

from settings.models import settings


def apply_theme():
    def themed_blurple(cls: type[discord.Colour]) -> discord.Colour:
        return cls(settings.embed_colour.value)

    discord.Colour.blurple = classmethod(themed_blurple)  # type: ignore[method-assign]
