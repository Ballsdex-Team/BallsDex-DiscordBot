"""
The pass as players see it: a page per tier (several for a long one), with what they finished, what is still locked
and one button to claim everything they earned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord.ui import ActionRow, Button, MediaGallery, Select, Separator, TextDisplay
from discord.utils import format_dt

from ballsdex.core.discord import Container, LayoutView

from ..engine import engine
from ..models import EventPass, PlayerQuest, RewardChoice
from ..rewards import resolve_choice, reward_preview
from ..state import PassState, QuestState, TierState, build_state

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from bd_models.models import Player

type Interaction = discord.Interaction["BallsDexBot"]

# a quest takes about three lines: past eight of them, a page gets too close to Discord's 4000 characters limit
QUESTS_PER_PAGE = 8
MANDATORY_MARK = "\N{PUSHPIN}"


def progress_bar(progress: int, target: int, length: int = 10) -> str:
    filled = min(length, progress * length // max(target, 1))
    return "\N{BLACK PARALLELOGRAM}" * filled + "\N{WHITE PARALLELOGRAM}" * (length - filled)


def quest_line(state: QuestState, bot: BallsDexBot | None = None, *, pin: bool = False) -> str:
    quest = state.quest
    if quest.hidden and not state.completed:
        return "\N{BLACK QUESTION MARK ORNAMENT} **Secret quest**"
    mark = "\N{WHITE HEAVY CHECK MARK}" if state.completed else "\N{BLACK PARALLELOGRAM}"
    if state.claimable:
        mark = "\N{WRAPPED PRESENT}"
    title = f"{quest.emoji} {quest.name}".strip()
    lines = [f"{mark} **{title}**{f' {MANDATORY_MARK}' if pin else ''}", f"-# {state.description}"]
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
    # a long tier is split over several pages
    part: int = 1
    parts: int = 1


def split_quests(quests: list[QuestState]) -> list[list[QuestState]]:
    """
    The quests of a tier, split into pages as even as possible: 10 quests make two pages of 5, not one of 8 and one
    of 2.
    """
    if len(quests) <= QUESTS_PER_PAGE:
        return [quests]
    count = -(-len(quests) // QUESTS_PER_PAGE)
    size = -(-len(quests) // count)
    return [quests[index : index + size] for index in range(0, len(quests), size)]


def build_pages(state: PassState, bot: BallsDexBot | None = None) -> list[Page]:
    pages: list[Page] = []
    if state.loose_quests:
        chunks = split_quests(state.loose_quests)
        pages.extend(
            Page(title="Quests", tier=None, quests=chunk, part=index, parts=len(chunks))
            for index, chunk in enumerate(chunks, start=1)
        )
    for tier_state in state.tiers:
        tier = tier_state.tier
        # a locked tier doesn't list its quests, one page is enough to say what it waits for
        chunks = split_quests(tier_state.quests) if tier_state.unlocked else [tier_state.quests]
        pages.extend(
            Page(
                title=f"{tier.emoji} {tier.name}".strip(),
                tier=tier_state,
                quests=chunk,
                locked=not tier_state.unlocked,
                missing=tier_state.missing,
                reward=reward_preview(tier.reward, bot) if tier.reward_id else "",
                part=index,
                parts=len(chunks),
            )
            for index, chunk in enumerate(chunks, start=1)
        )
    return pages or [Page(title="Quests", tier=None, quests=[])]


def current_page(pages: list[Page]) -> int:
    """
    Where the pass opens: the first tier the player hasn't finished yet, so nobody has to page through the tiers
    they are done with.
    """
    for index, page in enumerate(pages):
        if page.tier is not None and not page.tier.finished:
            return index
    return 0


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


class ChoiceSelect(Select["PassView"]):
    """
    The menu for one reserved reward. Its options are the treasures written down when the reward was claimed, so
    they never change between two visits.
    """

    def __init__(self, choice: RewardChoice, bot: BallsDexBot | None):
        self.choice = choice
        balls = choice.option_balls()
        options = [
            discord.SelectOption(
                label=ball.country[:100],
                value=str(ball.pk),
                emoji=_ball_emoji(bot, ball),
                description=f"T{ball.rarity:g}",
            )
            for ball in balls[:25]
        ]
        picks = min(max(choice.picks, 1), len(options) or 1)
        placeholder = f"Pick {picks}" if picks > 1 else "Pick your reward"
        if choice.label:
            placeholder = f"{placeholder} — {choice.label}"[:150]
        super().__init__(placeholder=placeholder, min_values=picks, max_values=picks, options=options)

    async def callback(self, interaction: Interaction):
        assert self.view
        await self.view.pick(interaction, self.choice, [int(value) for value in self.values])


def _ball_emoji(bot: BallsDexBot | None, ball) -> discord.PartialEmoji | None:
    if bot is None or not ball.emoji_id:
        return None
    emoji = bot.get_emoji(ball.emoji_id)
    return discord.PartialEmoji(name=emoji.name, id=emoji.id) if emoji else None


class PassView(LayoutView):
    """
    A page per tier, several for a long one. Only the player who ran the command can use the buttons.
    """

    def __init__(self, bot: BallsDexBot, player: Player, state: PassState, *, index: int | None = None):
        super().__init__(timeout=300)
        self.bot = bot
        self.player = player
        self.state = state
        self.pages = build_pages(state, bot)
        self.index = min(current_page(self.pages) if index is None else index, len(self.pages) - 1)
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
        if self.state.locked_out:
            container.add_item(TextDisplay(self._locked_out_text()))
            self.add_item(container)
            return
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
        # Discord allows five rows per container, and the pager and the claim button already take two
        for choice in self.state.choices[:3]:
            if choice.option_balls():
                container.add_item(ActionRow(ChoiceSelect(choice, self.bot)))
        self.add_item(container)

    def _locked_out_text(self) -> str:
        access = self.state.access
        default = "\N{LOCK} This event is not open to you."
        lines = [self.state.event_pass.access_message or default]
        if access and access.missing_text:
            lines.append("")
            lines.extend(f"-# · {text}" for text in access.missing_text)
        return "\n".join(lines)

    def _claimable_count(self) -> int:
        if self.state.locked_out:
            return 0
        count = self.state.claimable_count
        count += sum(
            1 for tier in self.state.tiers if tier.finished and tier.tier.reward_id and not tier.reward_claimed
        )
        if self.state.all_tiers_finished and self.state.event_pass.final_reward_id and not self.state.final_claimed:
            count += 1
        return count

    def _page_text(self) -> str:
        page = self.page
        lines = [f"## {page.title}" + (f" ({page.part}/{page.parts})" if page.parts > 1 else "")]
        if page.locked:
            tier = page.tier.tier if page.tier else None
            if tier and tier.locked_message:
                lines.append(tier.locked_message)
            else:
                lines.append("\N{LOCK} This tier is locked.")
            if page.missing:
                lines.extend(f"-# · {text}" for text in page.missing)
            return "\n".join(lines)

        tier_state = page.tier
        # the tier presentation sits on its first page only, the next ones are just the rest of its quests
        if tier_state and page.part == 1:
            if tier_state.tier.description:
                lines.append(tier_state.tier.description)
            if tier_state.uses_mandatory:
                lines.append(
                    f"{MANDATORY_MARK} **{tier_state.required_done}/{tier_state.required_total} mandatory quests** "
                    "done, finish them to complete the tier."
                )
            if page.reward:
                if tier_state.reward_claimed:
                    status = " (claimed)"
                elif tier_state.finished:
                    status = ", ready to claim!"
                else:
                    status = ", for finishing the tier"
                lines.append(f"**Tier reward:** {page.reward}{status}")
        if not page.quests:
            lines.append("-# No quest here yet.")
            return "\n".join(lines)
        pin = bool(tier_state and tier_state.uses_mandatory)
        for quest_state in page.quests:
            lines.append(quest_line(quest_state, self.bot, pin=pin and quest_state.quest.mandatory))
        return "\n".join(lines)

    async def pick(self, interaction: Interaction, choice: RewardChoice, ball_ids: list[int]):
        """
        Hand over a reward the player had reserved and is now picking.

        The reward was already set aside when they claimed it, so nothing can be lost here: a second click finds
        the choice resolved and is told so instead of giving anything twice.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await resolve_choice(
            choice.pk, ball_ids, server_id=interaction.guild_id, channel_id=interaction.channel_id
        )
        await self.reload()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
        if result.lines:
            text = "\N{WRAPPED PRESENT} **You received:**\n" + result.summary
        else:
            text = "That reward was already picked."
        await interaction.followup.send(text, ephemeral=True)

    async def claim(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if self.state.locked_out:
            await interaction.followup.send(self._locked_out_text(), ephemeral=True)
            return
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
            if not tier_state.finished or not tier_state.tier.reward_id or tier_state.reward_claimed:
                continue
            status, summary = await engine.claim_tier(
                self.player.pk, tier_state.tier, channel_id=interaction.channel_id, server_id=interaction.guild_id
            )
            if status == "claimed":
                got.append(f"**{tier_state.tier.name}**\n{summary}")

        if self.state.all_tiers_finished and event_pass.final_reward_id and not self.state.final_claimed:
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
