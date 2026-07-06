"""
Locale resolution for countryball display, gated to whatever language a player or a
server has explicitly configured (`Player.language`, `GuildConfig.language`, falling
back to `Settings.default_language`).

This is deliberately separate from `ballsdex.core.translation`, which backs both the
command tree's own localization (command/parameter names and descriptions) and runtime
UI strings (embeds, messages, view labels) - both of which instead follow each user's
Discord client locale. See that module's docstring for details.

These must not be conflated: countryball data must only ever be displayed in a language
that was explicitly opted into, never in an arbitrary client locale nobody configured
for that purpose.
"""

from typing import TYPE_CHECKING

import discord

from bd_models.models import GuildConfig, Player
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

type Interaction = discord.Interaction["BallsDexBot"]


async def resolve_locale(
    interaction: Interaction, *, player: Player | None = None, guild_config: GuildConfig | None = None
) -> str:
    """
    Resolve the language to use to display countryballs for this interaction.

    Resolution order:
    1. The invoking player's configured language (`Player.language`)
    2. The current server's configured language (`GuildConfig.language`)
    3. The bot's configured default language (`Settings.default_language`)

    Parameters
    ----------
    interaction: Interaction
        The interaction to resolve a language for.
    player: Player | None
        If already fetched, avoids an extra query.
    guild_config: GuildConfig | None
        If already fetched, avoids an extra query.

    Returns
    -------
    str
        The resolved language code. Always one of `settings.available_languages`.
    """
    if player is None:
        player = await Player.objects.only("language").aget_or_none(discord_id=interaction.user.id)
    if player and player.language:
        return player.language

    if guild_config is None and interaction.guild_id is not None:
        guild_config = await GuildConfig.objects.only("language").aget_or_none(guild_id=interaction.guild_id)
    if guild_config and guild_config.language:
        return guild_config.language

    return settings.default_language
