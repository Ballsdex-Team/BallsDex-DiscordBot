"""
Telling players they finished a quest, where they were playing.

One message per player for everything they finished in the same moment (a catch finishing three quests at once),
with the reward they can claim and where to claim it.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from discord.ui import Container, LayoutView, Section, Separator, TextDisplay, Thumbnail

from ballsdex.core.utils.background import run_on_bot_loop
from ballsdex.core.utils.notifications import notify_player
from bd_models.models import Player

from .models import Announce
from .rewards import reward_preview
from .types import player_description

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

    from .engine import Completion

MAX_SHOWN = 5


def quest_item(bot: BallsDexBot | None, completion: Completion) -> TextDisplay | Section:
    quest = completion.quest
    lines = [f"**{quest.emoji} {quest.name}**".strip(), player_description(quest)]
    if completion.auto_claimed:
        lines.append(f"Received: {completion.summary or 'nothing'}")
    elif quest.reward_id:
        lines.append(f"Reward to claim: {reward_preview(quest.reward, bot)}")
    if quest.completion_message:
        lines.append(quest.completion_message)
    text = TextDisplay("\n".join(lines))
    if url := quest.thumbnail_url:
        return Section(text, accessory=Thumbnail(url))
    return text


def completed_view(bot: BallsDexBot | None, discord_id: int, completions: list[Completion]) -> LayoutView:
    event_pass = completions[0].quest.event_pass
    title = "Quest complete!" if len(completions) == 1 else f"{len(completions)} quests complete!"
    container = Container(
        TextDisplay(f"## {event_pass.emoji} {title}".strip()), Separator(), accent_colour=event_pass.accent_colour
    )
    for completion in completions[:MAX_SHOWN]:
        container.add_item(quest_item(bot, completion))
    if len(completions) > MAX_SHOWN:
        container.add_item(TextDisplay(f"...and **{len(completions) - MAX_SHOWN}** more!"))
    if any(not completion.auto_claimed and completion.quest.reward_id for completion in completions):
        container.add_item(TextDisplay(f"-# Claim your rewards with /pass view {event_pass.name}"))
    else:
        container.add_item(TextDisplay(f"-# See your progress with /pass view {event_pass.name}"))

    view = LayoutView()
    view.add_item(TextDisplay(f"<@{discord_id}>"))
    view.add_item(container)
    return view


class PassNotifier:
    DELAY = 1.5

    def __init__(self, bot: BallsDexBot):
        self.bot = bot
        self._pending: dict[int, tuple[list[Completion], int | None]] = {}

    async def add(self, player_id: int, completions: list[Completion], channel_id: int | None):
        if player_id in self._pending:
            pending, pending_channel = self._pending[player_id]
            known = {(completion.quest.pk, completion.period) for completion in pending}
            pending.extend(
                completion for completion in completions if (completion.quest.pk, completion.period) not in known
            )
            self._pending[player_id] = (pending, pending_channel or channel_id)
            return
        self._pending[player_id] = (list(completions), channel_id)
        asyncio.get_running_loop().call_later(self.DELAY, lambda: run_on_bot_loop(lambda: self._flush(player_id)))

    async def _flush(self, player_id: int):
        completions, channel_id = self._pending.pop(player_id, ([], None))
        if not completions:
            return
        # each quest says where its message goes: the channel, the channel but only for them, their DMs, or nowhere
        groups = {
            mode: [x for x in completions if x.quest.announce == mode]
            for mode in (Announce.PUBLIC, Announce.EPHEMERAL, Announce.PRIVATE)
        }
        if not any(groups.values()):
            return
        player = await Player.objects.aget(pk=player_id)
        for mode, batch in groups.items():
            if not batch:
                continue
            view = completed_view(self.bot, player.discord_id, batch)
            if mode == Announce.PUBLIC:
                await notify_player(
                    self.bot, player.discord_id, view, channel_id=channel_id, mention=player.can_be_mentioned
                )
            elif mode == Announce.EPHEMERAL:
                await notify_player(self.bot, player.discord_id, view, ephemeral=True)
            else:
                await notify_player(self.bot, player.discord_id, view, use_recent_channel=False, mention=False)
