from collections import Counter
from typing import TYPE_CHECKING

import discord

from ballsdex.core.discord import View
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.menus.bulk_selector import BaseBulkSelector
from ballsdex.core.utils.utils import can_mention
from bd_models.enums import DonationPolicy
from bd_models.models import BallInstance, Player, Trade, TradeObject
from settings.models import settings

from .donation import BulkDonationRequest, add_view_all_button, check_giveable

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot

type Interaction = discord.Interaction["BallsDexBot"]


class BulkGiveSelector(BaseBulkSelector):
    async def configure(
        self,
        bot: "BallsDexBot",
        queryset: "QuerySet[BallInstance]",
        *,
        user: discord.User,
        new_player: Player,
        old_player: Player,
    ):
        self.target_user = user
        self.new_player = new_player
        self.old_player = old_player
        await super().configure(
            bot,
            queryset,
            header=f"## Bulk Give selection\nYour selected {settings.plural_collectible_name} are shown below.",
            description="-# Use the drop-down menu below to select your items to give.",
            select_placeholder=f"Select {settings.plural_collectible_name} to give",
            confirm_label="Give selected",
        )

    async def _finalize(self):
        assert self.view
        self.view.stop()
        for child in self.view.walk_children():
            if hasattr(child, "disabled"):
                child.disabled = True  # type: ignore
        if self.view.original_message:
            try:
                await self.view.original_message.edit(view=self.view)
            except discord.NotFound:
                pass

    async def on_confirm(self, interaction: Interaction, selected_ids: set[int]):
        balls = [
            ball
            async for ball in BallInstance.objects.filter(id__in=selected_ids).select_related("ball", "special")
        ]

        valid: list[BallInstance] = []
        skipped: list = []
        for ball in balls:
            reason = await check_giveable(ball)
            if reason is None:
                valid.append(ball)
            else:
                skipped.append(reason)

        if not valid:
            await interaction.response.send_message(
                f"Nothing was given, all {len(balls)} selected {settings.plural_collectible_name} "
                "are no longer valid.",
                ephemeral=True,
            )
            return

        favorites = [ball for ball in valid if ball.favorite]
        if favorites:
            confirm_view = ConfirmChoiceView(
                interaction,
                accept_message="Continuing with the donation.",
                cancel_message="This request has been cancelled.",
            )
            await interaction.response.send_message(
                f"{len(favorites)} of your selected {settings.plural_collectible_name} are favorites. "
                "Are you sure you want to donate them?",
                view=confirm_view,
                ephemeral=True,
            )
            await confirm_view.wait()
            if not confirm_view.value:
                return
            interaction = confirm_view.interaction_response
        else:
            await interaction.response.defer(ephemeral=True)

        for ball in valid:
            await ball.lock_for_trade()

        skip_txt = ""
        if skipped:
            counts = Counter(skipped)
            reasons = ", ".join(f"{count} {reason.value}" for reason, count in counts.items())
            skip_txt = f"\n{len(skipped)} were skipped: {reasons}."

        if self.new_player.donation_policy == DonationPolicy.REQUEST_APPROVAL:
            lines = [ball.description(include_emoji=True, bot=self.bot, is_trade=True) for ball in valid]
            if len(lines) > 15:
                listing = "\n".join(f"- {line}" for line in lines[:15]) + f"\n… and {len(lines) - 15} more"
            else:
                listing = "\n".join(f"- {line}" for line in lines)
            await interaction.followup.send(
                f"Hey {self.target_user.mention}, {interaction.user.name} wants to give you "
                f"{len(valid)} {settings.plural_collectible_name}:\n{listing}\nDo you accept this donation?",
                view=BulkDonationRequest(self.bot, interaction, valid, self.new_player, self.old_player),
                allowed_mentions=await can_mention([self.new_player, self.old_player]),
            )
            if skip_txt:
                await interaction.followup.send(skip_txt.strip(), ephemeral=True)
            await self._finalize()
            return

        trade = await Trade.objects.acreate(player1=self.old_player, player2=self.new_player)
        for ball in valid:
            ball.player = self.new_player
            ball.trade_player = self.old_player
            ball.favorite = False
            await ball.asave()
            await TradeObject.objects.acreate(trade=trade, ballinstance=ball, player=self.old_player)
            await ball.unlock()

        result_view = View()
        add_view_all_button(
            result_view,
            self.bot,
            [ball.pk for ball in valid],
            sender_id=self.old_player.discord_id,
            recipient_id=self.new_player.discord_id,
        )
        await interaction.followup.send(
            f"{interaction.user.mention} just gave {len(valid)} {settings.plural_collectible_name} "
            f"to {self.target_user.mention}!{skip_txt}",
            view=result_view,
            allowed_mentions=await can_mention([self.new_player, self.old_player]),
        )
        await self._finalize()
