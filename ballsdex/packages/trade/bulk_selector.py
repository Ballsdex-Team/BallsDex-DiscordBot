from typing import TYPE_CHECKING

import discord

from ballsdex.core.translation import t
from ballsdex.core.utils.menus.bulk_selector import BaseBulkSelector
from bd_models.models import BallInstance
from settings.models import settings

from .errors import TradeError

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot

    from .cog import Trade

type Interaction = discord.Interaction["BallsDexBot"]


class BulkSelector(BaseBulkSelector):
    async def configure(self, bot: "BallsDexBot", cog: "Trade", queryset: "QuerySet[BallInstance]"):
        self.cog = cog
        await super().configure(
            bot,
            queryset,
            header=t("## Trade bulk selection\nYour selected {collectibles} are shown below.").format(
                collectibles=settings.plural_collectible_name
            ),
            description=t("-# Use the drop-down menu below to select your items."),
            select_placeholder=t("Select {collectibles} to add").format(collectibles=settings.plural_collectible_name),
            confirm_label=t("Add to trade"),
        )

    async def on_confirm(self, interaction: Interaction, selected_ids: set[int]):
        result = await self.cog.get_trade(interaction)
        if result is None:
            await interaction.response.send_message(
                t("Your trade was not found, it may have ended before you finished your bulk trade."), ephemeral=True
            )
            return
        trade, trader = result

        try:
            await trader.add_to_proposal(BallInstance.objects.filter(id__in=selected_ids))
        except TradeError as e:
            await interaction.response.send_message(e.error_message, ephemeral=True)
        else:
            assert self.view
            await interaction.response.defer()
            self.view.stop()
            for children in self.view.walk_children():
                if hasattr(children, "disabled"):
                    children.disabled = True  # type: ignore
            await interaction.edit_original_response(view=self.view)
            await trade.edit_message(None)
            await interaction.followup.send(
                t("{count} {collectibles} added.").format(
                    count=len(selected_ids), collectibles=settings.plural_collectible_name
                ),
                ephemeral=True,
            )
