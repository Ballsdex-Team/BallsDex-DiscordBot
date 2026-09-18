from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord.ui import Container, LayoutView, Section, Separator, TextDisplay, Thumbnail

from ballsdex.core.utils.background import run_on_bot_loop
from ballsdex.core.utils.notifications import notify_player
from bd_models.models import Player
from settings.models import settings
from settings.utils import format_currency

from .types import player_description

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

    from .models import Achievement

MAX_SHOWN = 5


def achievement_item(
    bot: BallsDexBot | None, achievement: Achievement, *, heading: str | None = None, details: str = ""
) -> discord.ui.Item:
    """
    An achievement as a text block, with its thumbnail on the side if it has one. The heading defaults to the name of
    the achievement, an empty string removes it.
    """
    lines = []
    if heading is None:
        lines.append(f"**{achievement.name}**")
    elif heading:
        lines.append(heading)
    lines.append(player_description(achievement))
    if achievement.currency_reward:
        lines.append(f"Reward: {format_currency(achievement.currency_reward, False, bot)}")
    if details:
        lines.append(details)
    text = TextDisplay("\n".join(lines))
    if url := achievement.thumbnail_url:
        return Section(text, accessory=Thumbnail(url))
    return text


def unlocked_view(bot: BallsDexBot | None, discord_id: int, achievements: list[Achievement]) -> LayoutView:
    title = "Achievement unlocked!" if len(achievements) == 1 else f"{len(achievements)} achievements unlocked!"
    container = Container(TextDisplay(f"## \N{TROPHY} {title}"), Separator(), accent_colour=settings.embed_colour)
    for achievement in achievements[:MAX_SHOWN]:
        container.add_item(achievement_item(bot, achievement))
    if len(achievements) > MAX_SHOWN:
        container.add_item(TextDisplay(f"...and **{len(achievements) - MAX_SHOWN}** more!"))
    container.add_item(TextDisplay("-# See all your achievements with /achievement list"))

    view = LayoutView()
    view.add_item(TextDisplay(f"<@{discord_id}>"))
    view.add_item(container)
    return view


class AchievementNotifier:
    """
    Sends one message per player for everything they unlocked in a short time (a catch unlocking several achievements
    at once, a trade...), in the channel where it happened.
    """

    DELAY = 1.5

    def __init__(self, bot: BallsDexBot):
        self.bot = bot
        self._pending: dict[int, tuple[list[Achievement], int | None]] = {}

    async def add(self, player_id: int, achievements: list[Achievement], channel_id: int | None):
        if player_id in self._pending:
            pending, pending_channel = self._pending[player_id]
            pending.extend(achievement for achievement in achievements if achievement not in pending)
            self._pending[player_id] = (pending, pending_channel or channel_id)
            return
        self._pending[player_id] = (list(achievements), channel_id)
        asyncio.get_running_loop().call_later(self.DELAY, lambda: run_on_bot_loop(lambda: self._flush(player_id)))

    async def _flush(self, player_id: int):
        achievements, channel_id = self._pending.pop(player_id, ([], None))
        if not achievements:
            return
        player = await Player.objects.aget(pk=player_id)
        view = unlocked_view(self.bot, player.discord_id, achievements)
        await notify_player(self.bot, player.discord_id, view, channel_id=channel_id, mention=player.can_be_mentioned)
