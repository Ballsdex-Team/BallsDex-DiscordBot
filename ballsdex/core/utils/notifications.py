import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.core.utils.notifications")


async def _resolve_channel(bot: "BallsDexBot", channel_id: int) -> discord.abc.Messageable | None:
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None
    return channel if isinstance(channel, discord.abc.Messageable) else None


async def _send_dm(bot: "BallsDexBot", discord_id: int, view: discord.ui.LayoutView) -> bool:
    try:
        user = bot.get_user(discord_id) or await bot.fetch_user(discord_id)
        await user.send(view=view)
        return True
    except discord.HTTPException:
        log.debug("Failed to notify %s in DMs", discord_id)
        return False


async def _send_ephemeral(bot: "BallsDexBot", discord_id: int, view: discord.ui.LayoutView) -> bool:
    """
    Answer the player privately in the channel, by following up on the last thing they did with the bot.

    Discord only allows an ephemeral message as part of an interaction, and an interaction token dies after 15
    minutes, so this only works while the player is playing. It is never sent publicly as a fallback: a message
    meant for one player must not end up in front of the whole server.
    """
    interaction = bot.recent_interactions.get(discord_id)
    if interaction is None:
        return False
    try:
        await interaction.followup.send(view=view, ephemeral=True)
        return True
    except discord.HTTPException:
        log.debug("Failed to notify %s privately in the channel, trying DMs", discord_id)
        return False


async def notify_player(
    bot: "BallsDexBot",
    discord_id: int,
    view: discord.ui.LayoutView,
    *,
    channel_id: int | None = None,
    use_recent_channel: bool = True,
    mention: bool = True,
    ephemeral: bool = False,
) -> bool:
    """
    Send a message to a player where they are playing.

    The message goes to `channel_id` if given, else to the channel where the player last used the bot if it was
    recent enough, and to their DMs if none of those work.

    Parameters
    ----------
    ephemeral: bool
        Send the message in the channel but only visible to the player, by following up on their last interaction.
        Falls back to their DMs, never to a public message.

    Returns
    -------
    bool
        Whether the message could be delivered somewhere.
    """
    if ephemeral:
        return await _send_ephemeral(bot, discord_id, view) or await _send_dm(bot, discord_id, view)

    if channel_id is None and use_recent_channel:
        channel_id = bot.recent_interaction_channels.get(discord_id)

    if channel_id is not None and (channel := await _resolve_channel(bot, channel_id)):
        try:
            await channel.send(view=view, allowed_mentions=discord.AllowedMentions(users=mention, roles=False))
            return True
        except discord.HTTPException:
            log.debug("Failed to notify %s in channel %s, trying DMs", discord_id, channel_id)

    return await _send_dm(bot, discord_id, view)
