import logging
from typing import TYPE_CHECKING

import discord
from discord.ui import Select, select
from merchant_app.models import GlobalShop, MerchantItem

from ballsdex.core.utils.menus.old import ListPageSource, Pages
from bd_models.models import Player

from .purchase import PurchaseError, buy_item, purchase_message

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)


class BuyItemSource(ListPageSource):
    def __init__(self, entries: list[MerchantItem]):
        super().__init__(entries, per_page=25)

    async def format_page(self, menu, items):
        menu.set_options(items)
        return True  # signal to edit the page


class BuyItemView(Pages):
    def __init__(self, interaction: discord.Interaction["BallsDexBot"], shop: GlobalShop, items: list[MerchantItem]):
        self.bot = interaction.client
        self.shop = shop
        source = BuyItemSource(items)
        super().__init__(source, interaction=interaction)
        self.add_item(self.buy_item_select)

    def set_options(self, items: list[MerchantItem]):
        options: list[discord.SelectOption] = []
        for item in items:
            description = f"Prize: {item.prize if item.prize else 'Free'}"
            if item.stock is not None:
                description += f" • {item.stock_text}"
            options.append(discord.SelectOption(label=item.name, description=description, value=str(item.pk)))
        self.buy_item_select.options = options

    @select(placeholder="Select an item to buy")
    async def buy_item_select(self, interaction: discord.Interaction["BallsDexBot"], select: Select):
        value = int(select.values[0])
        item = await MerchantItem.objects.aget(pk=value)
        if item.sold_out:
            await interaction.response.send_message(f"**{item.name}** is sold out!", ephemeral=True)
            return
        if not item.enabled:
            await interaction.response.send_message("This item isn't enabled.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            player = await Player.objects.aget(discord_id=interaction.user.id)
        except Player.DoesNotExist:
            await interaction.followup.send("You're not registred in the economy system yet.")
            return

        try:
            instance = await buy_item(self.bot, player, item, server_id=interaction.guild_id)
        except PurchaseError as error:
            await interaction.followup.send(str(error))
            return
        await interaction.followup.send(purchase_message(self.bot, item, instance))
