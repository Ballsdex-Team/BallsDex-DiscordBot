import logging
import random
from typing import TYPE_CHECKING

import discord
from discord.ui import Select, select
from django.utils import timezone
from merchant_app.models import GlobalShop, MerchantItem

from ballsdex.core.utils.menus.old import ListPageSource, Pages
from bd_models.models import BallInstance, Player
from settings.models import settings
from settings.utils import format_currency

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
            options.append(
                discord.SelectOption(
                    label=item.name, description=f"Prize: {item.prize if item.prize else 'Free'}", value=str(item.pk)
                )
            )
        self.buy_item_select.options = options

    @select(placeholder="Select an item to buy")
    async def buy_item_select(self, interaction: discord.Interaction["BallsDexBot"], select: Select):
        value = int(select.values[0])
        item = await MerchantItem.objects.aget(pk=value)
        if not item.enabled:
            await interaction.response.send_message("This item isn't enabled.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            player = await Player.objects.aget(discord_id=interaction.user.id)
        except Player.DoesNotExist:
            await interaction.response.send_message("You're not registred in the economy system yet.")
            return

        if not item.prize:
            instance = await BallInstance.objects.acreate(
                player=player,
                ball=item.cached_ball,
                special=item.cached_special,
                health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                catch_date=timezone.now(),
                server_id=interaction.guild_id,
            )
            await interaction.followup.send(
                f"You've bought {item.name} for **free!**\n{instance.description(include_emoji=True, bot=self.bot)}"
            )
            return

        if player.money < item.prize:
            await interaction.followup.send(
                f"You don't enough {settings.currency_display_plural(self.bot)} to buy "
                f"**{item.name}**\n"
                f"Your actual balance: {format_currency(player.money, False, self.bot)}"
            )
            return

        try:
            instance = await BallInstance.objects.acreate(
                player=player,
                ball=item.cached_ball,
                special=item.cached_special,
                health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                catch_date=timezone.now(),
                server_id=interaction.guild_id,
            )
        except Exception:
            log.exception("Failed to create a ball instance while a user trying to buy an item.", exc_info=True)
            await interaction.followup.send("An error occurred while trying to buy the item.")
            return
        else:
            await player.remove_money(item.prize)
            await interaction.followup.send(
                f"You've bought {item.name} for **{format_currency(player.money, False, self.bot)}!**\n"
                f"{instance.description(include_emoji=True, bot=self.bot)}"
            )
            return
