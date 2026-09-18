"""
Bot-wide color theme.

Everything in this repository uses `settings.embed_colour` directly. Third-party packages installed
through `extra.toml` cannot be edited from here though, and most of them hardcode
`discord.Colour.blurple()` for their embeds. `apply_theme` redirects that color to the configured
one, and gives the same color to every message box (components v2 container) that doesn't set
one, so everything sent by the bot shares the same color.
"""

import functools

import discord

from settings.models import settings


def apply_theme():
    if getattr(discord.ui.Container, "_ballsdex_themed", False):
        return

    def themed_blurple(cls: type[discord.Colour]) -> discord.Colour:
        return cls(settings.embed_colour.value)

    discord.Colour.blurple = classmethod(themed_blurple)  # type: ignore[method-assign]

    original_container_init = discord.ui.Container.__init__

    @functools.wraps(original_container_init)
    def themed_container_init(self, *children, accent_colour=None, accent_color=None, **kwargs):
        colour = accent_colour if accent_colour is not None else accent_color
        if colour is None:
            colour = settings.embed_colour
        original_container_init(self, *children, accent_colour=colour, **kwargs)

    discord.ui.Container.__init__ = themed_container_init  # type: ignore[method-assign]
    discord.ui.Container._ballsdex_themed = True  # type: ignore[attr-defined]
