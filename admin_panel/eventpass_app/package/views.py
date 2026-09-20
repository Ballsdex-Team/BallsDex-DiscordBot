"""
The pass as players see it: one page per tier, with what they finished, what is still locked and one button to
claim everything they earned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord.ui import ActionRow, Button, MediaGallery, Separator, TextDisplay
from discord.utils import format_dt

from ballsdex.core.discord import Container, LayoutView

from ..engine import engine
from ..models import EventPass, PlayerQuest
from ..rewards import reward_preview
from ..state import PassState, QuestState, TierState, build_state

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from bd_models.models import Player

type Interaction = discord.Interaction["BallsDexBot"]

MAX_QUESTS_SHOWN = 12


def progress_bar(progress: int, target: int, length: int = 10) -> str:
    filled = min(length, progress * length // max(target, 1))
    return "\N{BLACK PARALLELOGRAM}" * filled + "\N{WHITE PARALLELOGRAM}" * (length - filled)


def quest_line(state: QuestState, bot: BallsDexBot | None = None) -> str:
    quest = state.quest
    if quest.hidden and not state.completed:
        return "\N{BLACK QUESTION MARK ORNAMENT} **Secret quest**"
    mark = "\N{WHITE HEAVY CHECK MARK}" if state.completed else "\N{BLACK PARALLELOGRAM}"
    if state.claimable:
        mark = "\N{WRAPPED PRESENT}"
    title = f"{quest.emoji} {quest.name}".strip()
    lines = [f"{mark} **{title}**", f"-# {state.description}"]
    if not state.completed:
        lines.append(f"-# {progress_bar(state.progress, state.target)} {state.progress:,}/{state.target:,}")
    elif state.claimable:
        lines.append(f"-# Ready to claim: {reward_preview(quest.reward, bot)}")
    elif quest.reward_id:
        lines.append("-# Claimed")
    return "\n".join(lines)


@dataclass
class Page:
    title: str
    tier: TierState | None
    quests: list[QuestState]
    locked: bool = False
    missing: list[str] | None = None
    reward: str = ""


def build_pages(state: PassState, bot: BallsDexBot | None = None) -> list[Page]:
    pages: list[Page] = []
    if state.loose_quests:
        pages.append(Page(title="Quests", tier=None, quests=state.loose_quests))
    for tier_state in state.tiers:
        tier = tier_state.tier
        pages.append(
            Page(
                title=f"{tier.emoji} {tier.name}".strip(),
                tier=tier_state,
                quests=tier_state.quests,
                locked=not tier_state.unlocked,
                missing=tier_state.missing,
                reward=reward_preview(tier.reward, bot) if tier.reward_id else "",
            )
        )
    return pages or [Page(title="Quests", tier=None, quests=[])]


class PageButton(Button["PassView"]):
    def __init__(self, label: str, step: int, disabled: bool):
        super().__init__(style=discord.ButtonStyle.secondary, label=label, disabled=disabled)
        self.step = step

    async def callback(self, interaction: Interaction):
        assert self.view
        await self.view.show_page(interaction, self.view.index + self.step)


class ClaimButton(Button["PassView"]):
    def __init__(self, count: int, disabled: bool):
        label = "Nothing to claim" if disabled else f"Claim {count} reward{'s' if count > 1 else ''}"
        super().__init__(style=discord.ButtonStyle.success, label=label, emoji="\N{WRAPPED PRESENT}", disabled=disabled)

    async def callback(self, interaction: Interaction):
        assert self.view
        await self.view.claim(interaction)


class PassView(LayoutView):
    """
    One page per tier. Only the player who ran the command can use the buttons.
    """

    def __init__(self, bot: BallsDexBot, player: Player, state: PassState, *, index: int = 0):
        super().__init__(timeout=300)
        self.bot = bot
        self.player = player
        self.state = state
        self.pages = build_pages(state, bot)
        self.index = min(index, len(self.pages) - 1)
        self.message: discord.Message | None = None
        self.restrict_author(player.discord_id)

    @property
    def page(self) -> Page:
        return self.pages[self.index]

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def show_page(self, interaction: Interaction, index: int):
        self.index = max(0, min(index, len(self.pages) - 1))
        self.refresh()
        await interaction.response.edit_message(view=self)

    async def reload(self):
        self.state = await build_state(self.player, self.state.event_pass)
        self.pages = build_pages(self.state, self.bot)
        self.index = min(self.index, len(self.pages) - 1)
        self.refresh()

    def refresh(self):
        self.clear_items()
        event_pass = self.state.event_pass
        container = Container(accent_colour=event_pass.accent_colour)
        if url := event_pass.banner_url:
            container.add_item(MediaGallery(discord.MediaGalleryItem(url)))
        header = [f"# {event_pass.emoji} {event_pass.name}".strip()]
        if event_pass.status == EventPass.Status.DRAFT:
            header.append(
                "\N{CONSTRUCTION SIGN}\N{VARIATION SELECTOR-16} **Draft** — only staff can see this pass, and "
                "nothing progresses until it is published."
            )
        if event_pass.description:
            header.append(event_pass.description)
        header.append(
            f"-# {self.state.completed_count}/{self.state.total_count} quests completed · "
            f"ends {format_dt(event_pass.ends_at, style='R')}"
        )
        container.add_item(TextDisplay("\n".join(header)))
        container.add_item(Separator())
        container.add_item(TextDisplay(self._page_text()))
        if len(self.pages) > 1:
            container.add_item(
                ActionRow(
                    PageButton("◀", -1, self.index == 0),
                    PageButton(f"{self.index + 1}/{len(self.pages)}", 0, True),
                    PageButton("▶", 1, self.index >= len(self.pages) - 1),
                )
            )
        claimable = self._claimable_count()
        container.add_item(ActionRow(ClaimButton(claimable, claimable == 0)))
        self.add_item(container)

    def _claimable_count(self) -> int:
        count = self.state.claimable_count
        count += sum(
            1 for tier in self.state.tiers if tier.unlocked and tier.tier.reward_id and not tier.reward_claimed
        )
        if self.state.all_tiers_unlocked and self.state.event_pass.final_reward_id and not self.state.final_claimed:
            count += 1
        return count

    def _page_text(self) -> str:
        page = self.page
        lines = [f"## {page.title}"]
        if page.locked:
            tier = page.tier.tier if page.tier else None
            if tier and tier.locked_message:
                lines.append(tier.locked_message)
            else:
                lines.append("\N{LOCK} This tier is locked.")
            if page.missing:
                lines.extend(f"-# · {text}" for text in page.missing)
            return "\n".join(lines)

        if page.tier and page.tier.tier.description:
            lines.append(page.tier.tier.description)
        if page.reward:
            claimed = page.tier.reward_claimed if page.tier else False
            lines.append(f"**Tier reward:** {page.reward}{' (claimed)' if claimed else ''}")
        if not page.quests:
            lines.append("-# No quest here yet.")
            return "\n".join(lines)
        for quest_state in page.quests[:MAX_QUESTS_SHOWN]:
            lines.append(quest_line(quest_state, self.bot))
        if len(page.quests) > MAX_QUESTS_SHOWN:
            lines.append(f"-# ...and {len(page.quests) - MAX_QUESTS_SHOWN} more quests")
        return "\n".join(lines)

    async def claim(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        event_pass = self.state.event_pass
        got: list[str] = []
        problems: list[str] = []

        for quest_state in self.state.quest_states:
            if not quest_state.claimable:
                continue
            status, summary = await engine.claim(
                self.player.pk, quest_state.quest, channel_id=interaction.channel_id, server_id=interaction.guild_id
            )
            if status == "claimed":
                got.append(f"**{quest_state.quest.name}**\n{summary}")
            elif status == "closed":
                problems.append("This pass is over, its rewards can't be claimed anymore.")
                break

        for tier_state in self.state.tiers:
            if not tier_state.unlocked or not tier_state.tier.reward_id or tier_state.reward_claimed:
                continue
            status, summary = await engine.claim_tier(
                self.player.pk, tier_state.tier, channel_id=interaction.channel_id, server_id=interaction.guild_id
            )
            if status == "claimed":
                got.append(f"**{tier_state.tier.name}**\n{summary}")

        if self.state.all_tiers_unlocked and event_pass.final_reward_id and not self.state.final_claimed:
            status, summary = await engine.claim_final(
                self.player.pk, event_pass, channel_id=interaction.channel_id, server_id=interaction.guild_id
            )
            if status == "claimed":
                got.append(f"**{event_pass.final_message or 'Pass completed!'}**\n{summary}")

        await self.reload()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

        if got:
            text = "\N{WRAPPED PRESENT} **You received:**\n" + "\n".join(got)
        elif problems:
            text = problems[0]
        else:
            text = "There was nothing left to claim."
        await interaction.followup.send(text, ephemeral=True)


async def player_summary(player: Player, event_pass: EventPass) -> tuple[int, int]:
    """
    How many quests a player completed in a pass, and how many they claimed. Used by the comparison command.
    """
    completed = await PlayerQuest.objects.filter(
        player=player, quest__event_pass=event_pass, completed_at__isnull=False
    ).acount()
    claimed = await PlayerQuest.objects.filter(
        player=player, quest__event_pass=event_pass, claimed_at__isnull=False
    ).acount()
    return completed, claimed
