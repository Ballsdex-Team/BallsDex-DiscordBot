from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from collector_app.models import Collector, CollectorTier
from discord.ui import ActionRow, Button, Separator, TextDisplay

from ballsdex.core.discord import Container, LayoutView, Modal
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.utils import can_mention
from bd_models.models import Player
from settings.models import settings
from settings.utils import format_currency

from .requirements import (
    ClaimResult,
    RequirementStatus,
    claim_tier,
    collector_card_special_ids,
    evaluate_requirements,
    is_claimed,
    tier_requirements,
)

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

type Interaction = discord.Interaction["BallsDexBot"]

# a collector asking for dozens of treasures can't show them all in a message
MAX_REQUIREMENT_LINES = 10


def missing_text(statuses: list[RequirementStatus], bot: "BallsDexBot | None" = None) -> str:
    lines = [status.describe(bot) for status in statuses[:MAX_REQUIREMENT_LINES]]
    if len(statuses) > MAX_REQUIREMENT_LINES:
        lines.append(f"-# ...and {len(statuses) - MAX_REQUIREMENT_LINES} more")
    return "\n".join(lines)


@dataclass
class TierState:
    tier: CollectorTier
    claimed: bool
    statuses: list[RequirementStatus]

    @property
    def available(self) -> bool:
        return self.tier.enabled and self.tier.level.claimable

    @property
    def missing(self) -> list[RequirementStatus]:
        return [status for status in self.statuses if not status.met]

    @property
    def ready(self) -> bool:
        return self.available and not self.claimed and not self.missing

    @property
    def needs_confirmation(self) -> bool:
        return bool(self.tier.price) or any(status.requirement.delete_balls for status in self.statuses)


@dataclass
class CollectorPage:
    collector: Collector
    tiers: list[CollectorTier]
    states: list[TierState] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return any(state.ready for state in self.states)

    @property
    def missing_count(self) -> int:
        return min((len(state.missing) for state in self.states if state.available and not state.claimed), default=999)


def load_tier_states(player_id: int, tiers: list[CollectorTier]) -> list[TierState]:
    excluded_specials = collector_card_special_ids()
    return [
        TierState(
            tier=tier,
            claimed=is_claimed(player_id, tier),
            statuses=evaluate_requirements(player_id, tier_requirements(tier), excluded_specials),
        )
        for tier in tiers
    ]


class ClaimTierButton(Button["CollectorClaimView"]):
    def __init__(self, state: TierState):
        tier = state.tier
        if state.claimed:
            style, label = discord.ButtonStyle.secondary, f"{tier.level.name} (claimed)"
        elif not state.available:
            style, label = discord.ButtonStyle.secondary, f"{tier.level.name} (soon)"
        else:
            style = discord.ButtonStyle.success if not state.missing else discord.ButtonStyle.primary
            label = tier.level.name
        super().__init__(
            style=style,
            label=label,
            emoji=tier.level.emoji or None,
            disabled=state.claimed or not state.available,
            row=1,
        )
        self.tier_id = tier.pk

    async def callback(self, interaction: Interaction):
        assert self.view
        await self.view.claim(interaction, self.tier_id)


class PageButton(Button["CollectorClaimView"]):
    def __init__(self, label: str, step: int, disabled: bool):
        super().__init__(style=discord.ButtonStyle.secondary, label=label, disabled=disabled, row=0)
        self.step = step

    async def callback(self, interaction: Interaction):
        assert self.view
        await self.view.show_page(interaction, self.view.index + self.step)


class JumpButton(Button["CollectorClaimView"]):
    def __init__(self, label: str):
        super().__init__(style=discord.ButtonStyle.primary, label=label, row=0)

    async def callback(self, interaction: Interaction):
        assert self.view
        await interaction.response.send_modal(JumpModal(self.view))


class JumpModal(Modal, title="Go to a collector"):
    page = discord.ui.TextInput(label="Page number", placeholder="Enter a number", min_length=1, max_length=5)

    def __init__(self, view: "CollectorClaimView"):
        super().__init__()
        self.claim_view = view
        self.page.placeholder = f"Enter a number between 1 and {len(view.pages)}"

    async def on_submit(self, interaction: Interaction):
        try:
            index = int(self.page.value) - 1
        except ValueError:
            await interaction.response.send_message("That's not a number.", ephemeral=True)
            return
        if not 0 <= index < len(self.claim_view.pages):
            await interaction.response.send_message(
                f"Enter a number between 1 and {len(self.claim_view.pages)}.", ephemeral=True
            )
            return
        await self.claim_view.show_page(interaction, index)


class CollectorClaimView(LayoutView):
    """
    Shows one collector per page with the player's progress on each of its tiers, and a button to claim them.
    """

    def __init__(self, bot: "BallsDexBot", player: Player, pages: list[CollectorPage]):
        super().__init__(timeout=300)
        self.bot = bot
        self.player = player
        self.pages = pages
        self.index = 0
        self.message: discord.Message | None = None

    @property
    def page(self) -> CollectorPage:
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
        await self.refresh()
        await interaction.response.edit_message(view=self)

    async def refresh(self, *, reload_states: bool = False):
        page = self.page
        if reload_states or not page.states:
            page.states = await sync_to_async(load_tier_states)(self.player.pk, page.tiers)
        self.clear_items()

        ball = page.collector.cached_ball
        emoji = self.bot.get_emoji(ball.emoji_id) if ball else None
        container = Container(
            TextDisplay(f"# {f'{emoji} ' if emoji else ''}{page.collector.name}"),
            TextDisplay("-# Pick the tier you want to claim."),
            Separator(),
            accent_colour=settings.embed_colour,
        )
        for state in page.states:
            container.add_item(TextDisplay(self._describe(state)))

        row = ActionRow()
        if len(self.pages) > 1:
            container.add_item(TextDisplay(f"-# Collector {self.index + 1}/{len(self.pages)}"))
            row.add_item(PageButton("◀", -1, self.index == 0))
            row.add_item(JumpButton(f"{self.index + 1}/{len(self.pages)}"))
            row.add_item(PageButton("▶", 1, self.index >= len(self.pages) - 1))
            container.add_item(row)
            row = ActionRow()
        for state in page.states:
            if len(row.children) == 5:
                container.add_item(row)
                row = ActionRow()
            row.add_item(ClaimTierButton(state))
        container.add_item(row)
        self.add_item(container)

    def _describe(self, state: TierState) -> str:
        level = state.tier.level
        title = f"### {f'{level.emoji} ' if level.emoji else ''}{level.name}"
        if state.claimed:
            return f"{title}\n\N{WHITE HEAVY CHECK MARK} Already claimed"
        if not state.available:
            return f"{title}\n\N{LOCK} Not available yet"

        lines = [title]
        if not state.statuses:
            lines.append("No requirement, it's free to claim!")
        elif state.missing:
            lines.append(f"Missing {len(state.missing)} of {len(state.statuses)} requirements:")
        else:
            lines.append("\N{SPARKLES} You meet every requirement, you can claim it!")

        # long recipes only show what is missing, a message can't hold hundreds of lines
        shown = state.statuses if len(state.statuses) <= MAX_REQUIREMENT_LINES else (state.missing or [])
        lines.extend(status.describe(self.bot) for status in shown[:MAX_REQUIREMENT_LINES])
        if len(shown) > MAX_REQUIREMENT_LINES:
            lines.append(f"-# ...and {len(shown) - MAX_REQUIREMENT_LINES} more missing")
        elif len(state.statuses) > MAX_REQUIREMENT_LINES:
            lines.append(f"-# {len(state.statuses)} treasures needed, they are all used up when claiming")

        if state.tier.price:
            lines.append(f"Cost: **{format_currency(state.tier.price, False, self.bot)}**")
        return "\n".join(lines)

    async def claim(self, interaction: Interaction, tier_id: int):
        state = next(state for state in self.page.states if state.tier.pk == tier_id)
        tier = state.tier
        tier_name = f"**{self.page.collector.name}** ({tier.level.name})"

        if state.missing:
            # tell exactly what is missing, the list above may be outdated
            statuses = await sync_to_async(evaluate_requirements)(
                self.player.pk, [status.requirement for status in state.statuses]
            )
            state.statuses = statuses
            if missing := state.missing:
                await interaction.response.send_message(
                    f"You can't claim {tier_name} yet, you're missing:\n" + missing_text(missing, self.bot),
                    ephemeral=True,
                )
                return

        if state.needs_confirmation:
            costs = []
            if tier.price:
                costs.append(f"cost **{format_currency(tier.price, False, self.bot)}**")
            if consumed := [status for status in state.statuses if status.requirement.delete_balls]:
                listed = ", ".join(
                    f"{status.requirement.amount}× {status.label(self.bot)}"
                    for status in consumed[:MAX_REQUIREMENT_LINES]
                )
                if len(consumed) > MAX_REQUIREMENT_LINES:
                    listed += f" and {len(consumed) - MAX_REQUIREMENT_LINES} more"
                costs.append(f"use up {listed}")
            confirm = ConfirmChoiceView(
                interaction, accept_message="Claiming...", cancel_message="The claim was cancelled."
            )
            await interaction.response.send_message(
                f"Claiming {tier_name} will {' and '.join(costs)}. Do you want to continue?",
                view=confirm,
                ephemeral=True,
            )
            await confirm.wait()
            if not confirm.value:
                return
            interaction = confirm.interaction_response
        else:
            await interaction.response.defer()

        result = await sync_to_async(claim_tier)(self.player.pk, tier_id, interaction.guild_id)
        await self._send_result(interaction, tier_name, result)

    async def _send_result(self, interaction: Interaction, tier_name: str, result: ClaimResult):
        match result.status:
            case "claimed":
                assert result.card
                await self.refresh(reload_states=True)
                if self.message:
                    await self.message.edit(view=self)
                await interaction.followup.send(
                    f"\N{PARTY POPPER} {interaction.user.mention} claimed the {tier_name} collector card!\n"
                    f"{result.card.description(include_emoji=True, bot=self.bot)}",
                    allowed_mentions=await can_mention([self.player]),
                )
            case "missing":
                await interaction.followup.send(
                    f"You can't claim {tier_name} yet, you're missing:\n" + missing_text(result.missing, self.bot),
                    ephemeral=True,
                )
            case "already_claimed":
                await interaction.followup.send(f"You already claimed {tier_name}.", ephemeral=True)
            case "not_enough_money":
                await interaction.followup.send(
                    f"You don't have enough {settings.currency_display_plural(self.bot)} to claim {tier_name}.",
                    ephemeral=True,
                )
            case "locked":
                await interaction.followup.send(
                    f"Some of the {settings.plural_collectible_name} needed for {tier_name} are locked in a trade, "
                    "try again once it's over.",
                    ephemeral=True,
                )
            case "unavailable":
                await interaction.followup.send(f"{tier_name} can't be claimed right now.", ephemeral=True)
