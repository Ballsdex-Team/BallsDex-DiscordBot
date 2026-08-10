import logging
import random
from typing import TYPE_CHECKING

import discord
from currency_app.models import CurrencySettings
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt
from django.utils import timezone
from merchant_app.models import (
    GlobalShop,
    MerchantInstance,
    MerchantItem,
    MerchantSettings,
    global_shops,
    merchant_items,
)

from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.menus.old import FieldPageSource, Pages
from bd_models.models import BallInstance, Player
from settings.models import settings
from settings.utils import format_currency

from .components import BuyItemView
from .transformers import GlobalShopTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)


class Merchant(commands.GroupCog):
    """
    Merchant commands.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._merchant_settings: MerchantSettings | None = None

    rotation = app_commands.Group(name="rotation", description="Merchant rotation commands.")
    global_group = app_commands.Group(name="global", description="Merchant global commands.")

    @commands.group(invoke_without_command=True)
    async def merchant(self, ctx: commands.Context):
        """
        Merchant prefix commands.
        """
        await ctx.send_help(ctx.command)

    @merchant.command()
    @commands.is_owner()
    async def reloadcache(self, ctx: commands.Context["BallsDexBot"]):
        """
        Reload the cache of Merchant models.
        """
        merchant_items.clear()
        async for merchant in MerchantItem.objects.all():
            merchant_items[merchant.pk] = merchant

        global_shops.clear()
        async for shop in GlobalShop.objects.all():
            global_shops[shop.pk] = shop

        await ctx.message.add_reaction("✅")

    @rotation.command(name="shop")
    async def rotation_shop(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check the available items in the rotation shop.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        merchant_settings = await self.get_merchant_settings()
        instance, created = await MerchantInstance.objects.prefetch_related("items").aget_or_create(
            player=player, defaults={"rotation_ends_at": timezone.now() + merchant_settings.rotation_delta}
        )
        has_items = bool(instance.items)

        if created or not has_items or instance.rotation_expired:
            items = self._get_random_items(merchant_settings.items)
            if not items:
                await interaction.followup.send("Failed to select items for rotation.")
                return

            if not created and has_items:
                await instance.items.aclear()
            await instance.items.aadd(*items)

            instance.rotation_ends_at = timezone.now() + merchant_settings.rotation_delta
            await instance.asave(update_fields=("rotation_ends_at",))
        else:
            items = [x async for x in instance.items.all()]

        entries: list[tuple[str, str]] = [
            (x.name, format_currency(x.prize or 0, False, self.bot)) for x in items if x.enabled
        ]
        source = FieldPageSource(entries, per_page=merchant_settings.items, inline=True, clear_description=False)
        source.embed.title = f"{settings.bot_name} shop"
        source.embed.description = (
            "Check out your items! Your rotation will update "
            f"Your rotation will update {format_dt(instance.rotation_ends_at)}"
            "\n-# Note: Cost depends on rarity."
        )

        pages = Pages(source, interaction=interaction, compact=True)
        await pages.start()

    @rotation.command()
    @app_commands.rename(item_id="item")
    async def buy(self, interaction: discord.Interaction["BallsDexBot"], item_id: int):
        """
        Buy an item from the rotation shop.

        Parameters
        ----------
        item_id: int
            The item that you want to
        """
        try:
            item = await MerchantItem.objects.aget(pk=item_id)
        except MerchantItem.DoesNotExist:
            await interaction.response.send_message(f"Item with id `#{item_id:0X}` doesn't exist.", ephemeral=True)
            return
        try:
            player = await Player.objects.aget(discord_id=interaction.user.id)
            instance = await MerchantInstance.objects.aget(player=player)
        except (Player.DoesNotExist, MerchantInstance.DoesNotExist):
            await interaction.response.send_message("You're not registred in the economy system yet.")
            return

        has_item = await instance.items.filter(pk=item_id).aexists()
        if not has_item:
            await interaction.response.send_message(
                "You can't buy this item because it's not in your current selection.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

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

    @global_group.command(name="shop")
    async def global_shop(self, interaction: discord.Interaction["BallsDexBot"], shop: GlobalShopTransform):
        """
        Check the available items from a global shop.

        Parameters
        ----------
        shop: GlobalShop
            The shop you want to visit
        """
        await interaction.response.defer(thinking=True)
        entries: list[tuple[str, str]] = [
            (x.name, format_currency(x.prize, False, self.bot)) async for x in shop.items.all()
        ]
        source = FieldPageSource(entries, per_page=3, inline=True)
        source.embed.title = f"{settings.bot_name} {shop.name}"
        source.embed.set_image(url=f"{settings.site_base_url}/media/{shop.banner.name}")
        pages = Pages(source, interaction=interaction, compact=True)
        await pages.start()

    @global_group.command(name="buy")
    async def global_buy(self, interaction: discord.Interaction["BallsDexBot"], shop: GlobalShopTransform):
        """
        Buy an item from a global shop.

        Parameters
        ----------
        shop: GlobalShop
            The shop that you want to buy items
        """
        items = [x async for x in shop.items.all() if x.enabled]
        if not items:
            await interaction.response.send_message(f"{shop.name} doesn't any active items.", ephemeral=True)
            return

        paginator = BuyItemView(interaction, shop, items)
        await paginator.start(ephemeral=True)

    @app_commands.command()
    async def convert_token(self, interaction: discord.Interaction["BallsDexBot"], amount: int = 1):
        """
        Convert a token into coins.

        Parameters
        ----------
        amount: int
            Number of tokens to convert.
        """
        merchant_settings = await self.get_merchant_settings()
        if not merchant_settings.cached_token_ball:
            await interaction.response.send_message("This command isn't configured yet.", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("Please select a valid amount.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        token_ball = merchant_settings.cached_token_ball
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        query = BallInstance.objects.filter(player=player, special_id__isnull=True, ball_id=token_ball.pk)
        if (count := await query.acount()) < amount:
            await interaction.followup.send(
                f"You can't convert **{amount} tokens** because you don't have that amount.\n"
                f"Actual amount: **{count} tokens**"
            )
            return
        query = query.order_by("-catch_date")[:amount]

        grammar = "token" if amount == 1 else "tokens"
        view = ConfirmChoiceView(
            interaction,
            accept_message=f"Confirmed, converting {amount} {grammar}...",
            cancel_message="Request cancelled.",
        )
        await interaction.followup.send(
            f"Are you sure you want to convert **{amount} {grammar}** into "
            f"**{format_currency(merchant_settings.token_conversion_rate * amount, False, self.bot)}**?",
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if not view.value:
            return

        ids = [x async for x in query.values_list("id", flat=True)]
        try:
            await BallInstance.objects.filter(id__in=ids).adelete()
        except Exception:
            log.exception("Failed to delete token ball instances while converting tokens.", exc_info=True)
            await interaction.followup.send("An error occurred while trying to convert tokens.")
            return
        else:
            await player.add_money(merchant_settings.token_conversion_rate * amount)
            await interaction.followup.send(
                f"Converted! All tokens successfully converted into {settings.currency_plural}.\n"
                f"Converted tokens: **{amount}**\n"
                "Given amount: "
                f"**{format_currency(merchant_settings.token_conversion_rate * amount, False, self.bot)}**\n"
                f"Actual balance: **{format_currency(player.money, False, self.bot)}**",
                ephemeral=True,
            )

    @buy.autocomplete("item_id")
    async def item_autocomplete(
        self, interaction: discord.Interaction["BallsDexBot"], current: str
    ) -> list[app_commands.Choice[int]]:
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        merchant_settings = await self.get_merchant_settings()
        instance, created = await MerchantInstance.objects.prefetch_related("items").aget_or_create(
            player=player, defaults={"rotation_ends_at": timezone.now() + merchant_settings.rotation_delta}
        )
        has_items = bool(instance.items)

        if created or not has_items or instance.rotation_expired:
            items = self._get_random_items(merchant_settings.items)
            if not items:
                return []

            if not created and has_items:
                await instance.items.aclear()
            await instance.items.aadd(*items)

            instance.rotation_ends_at = timezone.now() + merchant_settings.rotation_delta
            await instance.asave(update_fields=("rotation_ends_at",))
        else:
            items = [x async for x in instance.items.all()]

        return [
            app_commands.Choice(name=f"#{x.pk:0X} {x.name} ({format_currency(x.prize or 0)})", value=x.pk)
            for x in items
            if current.lower() in x.name.lower()
        ]

    def _get_random_items(self, amount: int) -> list[MerchantItem] | None:
        population = [x for x in merchant_items.values() if x.enabled]

        if not population:
            return None

        amount = min(amount, len(population))
        selected = []

        for _ in range(amount):
            weights = [x.rarity for x in population]
            choice = random.choices(population, weights=weights, k=1)[0]
            selected.append(choice)
            population.remove(choice)

        return selected

    async def get_merchant_settings(self, refresh: bool = True):
        if not self._merchant_settings:
            self._merchant_settings = await MerchantSettings.aload()
        if refresh:
            await self._merchant_settings.arefresh_from_db()
        return self._merchant_settings
