import random
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import discord
from currency_app.models import CurrencySettings, Item, MoneyInstance
from discord.ui import Button, View, button, select

from ballsdex.core.utils.menus.old import Pages, menus
from ballsdex.packages.countryballs.countryball import BallSpawnView
from ballsdex.settings import settings
from bd_models.models import Ball, BallInstance, Player

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class SelectBallPackSource(menus.ListPageSource):
    def __init__(self, entries: list[Ball]):
        super().__init__(entries, per_page=25)

    async def format_page(self, menu: "SelectBallPackView", balls: list[Ball]):
        menu.set_options(balls)
        return True  # signal to edit the page


class SelectBallPackView(Pages):
    def __init__(self, pack: Item, interaction: discord.Interaction["BallsDexBot"], balls: list[Ball]):
        self.pack = pack
        self.bot = interaction.client
        source = SelectBallPackSource(balls)
        super().__init__(source=source, interaction=interaction)
        self.add_item(self.select_ball_menu)

    def set_options(self, balls: list[Ball]):
        options: list[discord.SelectOption] = []
        for ball in balls:
            emoji = self.bot.get_emoji(int(ball.emoji_id))
            options.append(discord.SelectOption(label=ball.country, emoji=emoji, value=f"{ball.pk}"))
        self.select_ball_menu.options = options

    @select()
    async def select_ball_menu(self, interaction: discord.Interaction["BallsDexBot"], item: discord.ui.Select):
        await interaction.response.defer(thinking=True, ephemeral=True)
        ball = await Ball.objects.aget(pk=int(interaction.data.get("values")[0]))  # type: ignore
        pack = self.pack
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        special = pack.special or BallSpawnView.get_random_special()
        rarity = ball.rarity
        instance = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            special=special,
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
        )
        embed = discord.Embed(title=f"🎁 You got {ball.country}!", color=discord.Color.gold())
        desc = f"📖 **Rarity:** {rarity}\n❤️ **Health:** {ball.health}\n⚔️ **Attack:** {ball.attack}\n"
        if special:
            desc += f"⚡ **Special:** {special.name}\n"
        embed.description = desc
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        with ThreadPoolExecutor() as pool:
            buffer = await interaction.client.loop.run_in_executor(pool, instance.draw_card)
        file = discord.File(buffer, "card.webp")
        embed.set_image(url="attachment://card.webp")

        self.stop()
        self.disable_button()
        await self.original_interaction.edit_original_response(view=self)
        await interaction.followup.send(embed=embed, file=file)

    def disable_button(self):
        self.stop()
        for item in self.children:
            item.disabled = True  # type: ignore


class ShopPages(Pages):
    def __init__(self, source, *, interaction, check_embeds=False, compact=False):
        super().__init__(source, interaction=interaction, check_embeds=check_embeds, compact=compact)
        self._current_item: Item | None = None
        self.add_item(self.buy_item)

    @button(style=discord.ButtonStyle.primary, label="Buy it!")
    async def buy_item(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        if not self._current_item:
            await interaction.response.send_message("There isn't any item to buy.", ephemeral=True)
            return
        pack = self._current_item
        currency_settings = await CurrencySettings.aload()
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        instance, _ = await MoneyInstance.objects.aget_or_create(player=player)
        currency_emoji = self.bot.get_emoji(currency_settings.emoji_id) if currency_settings.emoji_id else ""
        if pack.prize:
            if instance.amount < pack.prize:
                emoji = self.bot.get_emoji(pack.emoji_id) if pack.emoji_id else ""
                await interaction.response.send_message(
                    f"You don't enough {currency_emoji} {currency_settings.name} to buy "
                    f"**{emoji} {pack.name}**\n"
                    f"Your actual balance: "
                    f"**{currency_emoji} {instance.amount:,} {currency_settings.display_name(instance.amount)}**"
                )
                return
            else:
                instance.amount -= pack.prize
                await instance.asave(update_fields=("amount",))

        balls = [x.cached_ball async for x in pack.balls.all()]
        if balls:
            paginator = SelectBallPackView(pack, interaction, balls)
            await paginator.start(
                content=f"Select the {settings.collectible_name} that you want to purchase.", ephemeral=True
            )
            return
        else:
            await interaction.response.defer(thinking=True, ephemeral=True)
            balls = [
                x
                async for x in Ball.objects.filter(
                    enabled=True, tradeable=True, rarity__range=(pack.minimum_rarity, pack.maximum_rarity)
                )
            ]
        ball = await self._get_random_countryball(balls)
        special = pack.special or BallSpawnView.get_random_special()
        rarity = ball.rarity
        instance = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            special=special,
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
        )
        embed = discord.Embed(title=f"🎁 You got {ball.country}!", color=discord.Color.gold())
        desc = f"📖 **Rarity:** {rarity}\n❤️ **Health:** {ball.health}\n⚔️ **Attack:** {ball.attack}\n"
        if special:
            desc += f"⚡ **Special:** {special.name}\n"
        embed.description = desc
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        with ThreadPoolExecutor() as pool:
            buffer = await interaction.client.loop.run_in_executor(pool, instance.draw_card)
        file = discord.File(buffer, "card.webp")
        embed.set_image(url="attachment://card.webp")
        await interaction.followup.send(embed=embed, file=file)

    async def _get_random_countryball(self, countryballs: list[Ball]) -> Ball:
        if not countryballs:
            raise RuntimeError("No ball to spawn")
        rarities = [x.rarity for x in countryballs]
        cb = random.choices(population=countryballs, weights=rarities, k=1)[0]
        return cb


class ShopMenuSource(menus.ListPageSource):
    def __init__(self, entries: list[Item], bot: "BallsDexBot", currency_settings: CurrencySettings):
        super().__init__(entries, per_page=1)
        self.bot = bot
        self.currency_settings = currency_settings

    async def format_page(self, menu: ShopPages, page: Item) -> discord.Embed:
        menu._current_item = self.entries[menu.current_page]
        embed = discord.Embed(title=page.name, color=discord.Color.blurple())
        embed.set_footer(text=f"Item {menu.current_page + 1}/{menu.source.get_max_pages()}")
        emoji = str(self.bot.get_emoji(page.emoji_id)) if page.emoji_id else ""
        currency_emoji = self.bot.get_emoji(self.currency_settings.emoji_id) if self.currency_settings.emoji_id else ""

        if page.description:
            description = (
                f"{page.description}\n\n"
                f"Price: **{currency_emoji} {page.prize:,} {self.currency_settings.display_name(page.prize)}**\n"
                f"Special: **{page.special.name if page.special else 'Any'}**\n"
            )
        else:
            description = (
                f"Price: **{currency_emoji} {page.prize:,} {self.currency_settings.display_name(page.prize)}**\n"
                f"Special: **{page.special.name if page.special else 'Any'}**\n"
            )

        countryballs = [x async for x in page.balls.all()]
        if countryballs:
            description += f"# Possible {settings.plural_collectible_name.title()}\n"
            for countryball in countryballs:
                emoji = self.bot.get_emoji(countryball.cached_ball.emoji_id)
                if emoji:
                    description += f"- {emoji} {countryball.cached_ball.country}\n"
                else:
                    description += f"- {countryball.cached_ball.country}\n"
        else:
            description += f"Minimum Rarity: **{page.minimum_rarity}**\nMaximum Rarity: **{page.maximum_rarity}**\n"

        embed.description = description
        return embed
