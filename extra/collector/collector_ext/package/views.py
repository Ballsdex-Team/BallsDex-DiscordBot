from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from collector_app.models import Collector, CollectorTier
from discord.ui import ActionRow, Button, Separator, TextDisplay

from ballsdex.core.discord import Container, LayoutView
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
    def needs_confirmation(self) -> bool:
        return bool(self.tier.price) or any(status.requirement.delete_balls for status in self.statuses)


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
            style=style, label=label, emoji=tier.level.emoji or None, disabled=state.claimed or not state.available
        )
        self.tier_id = tier.pk

    async def callback(self, interaction: Interaction):
        assert self.view
        await self.view.claim(interaction, self.tier_id)


class CollectorClaimView(LayoutView):
    """
    Shows every tier of a collector with the player's progress, and a button to claim each of them.
    """

    def __init__(self, bot: "BallsDexBot", player: Player, collector: Collector, tiers: list[CollectorTier]):
        super().__init__(timeout=300)
        self.bot = bot
        self.player = player
        self.collector = collector
        self.tiers = tiers
        self.states: list[TierState] = []
        self.message: discord.Message | None = None

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def refresh(self):
        self.states = await sync_to_async(load_tier_states)(self.player.pk, self.tiers)
        self.clear_items()

        ball = self.collector.cached_ball
        emoji = self.bot.get_emoji(ball.emoji_id) if ball else None
        container = Container(
            TextDisplay(f"# {f'{emoji} ' if emoji else ''}{self.collector.name}"),
            TextDisplay("-# Pick the tier you want to claim."),
            Separator(),
            accent_colour=settings.embed_colour,
        )
        for state in self.states:
            container.add_item(TextDisplay(self._describe(state)))
        row = ActionRow()
        for state in self.states:
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
        lines.extend(status.describe(self.bot) for status in state.statuses)
        if state.tier.price:
            lines.append(f"Cost: **{format_currency(state.tier.price, False, self.bot)}**")
        return "\n".join(lines)

    async def claim(self, interaction: Interaction, tier_id: int):
        state = next(state for state in self.states if state.tier.pk == tier_id)
        tier = state.tier
        tier_name = f"**{self.collector.name}** ({tier.level.name})"

        if state.missing:
            # tell exactly what is missing, the list above may be outdated
            statuses = await sync_to_async(evaluate_requirements)(
                self.player.pk, [s.requirement for s in state.statuses]
            )
            state.statuses = statuses
            if missing := state.missing:
                await interaction.response.send_message(
                    f"You can't claim {tier_name} yet, you're missing:\n"
                    + "\n".join(status.describe(self.bot) for status in missing),
                    ephemeral=True,
                )
                return

        if state.needs_confirmation:
            costs = []
            if tier.price:
                costs.append(f"cost **{format_currency(tier.price, False, self.bot)}**")
            if consumed := [status for status in state.statuses if status.requirement.delete_balls]:
                costs.append(
                    "use up "
                    + ", ".join(f"{status.requirement.amount}× {status.label(self.bot)}" for status in consumed)
                )
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
                await self.refresh()
                if self.message:
                    await self.message.edit(view=self)
                await interaction.followup.send(
                    f"\N{PARTY POPPER} {interaction.user.mention} claimed the {tier_name} collector card!\n"
                    f"{result.card.description(include_emoji=True, bot=self.bot)}",
                    allowed_mentions=await can_mention([self.player]),
                )
            case "missing":
                await interaction.followup.send(
                    f"You can't claim {tier_name} yet, you're missing:\n"
                    + "\n".join(status.describe(self.bot) for status in result.missing),
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
