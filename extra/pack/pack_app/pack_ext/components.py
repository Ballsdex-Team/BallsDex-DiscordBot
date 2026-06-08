from typing import TYPE_CHECKING

import discord
from currency_app.models import CurrencySettings, Item

from ballsdex.core.utils.menus.old import Pages, menus
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class ShopMenuSource(menus.ListPageSource):
    def __init__(self, entries: list[Item], bot: "BallsDexBot", currency_settings: CurrencySettings):
        super().__init__(entries, per_page=1)
        self.bot = bot
        self.currency_settings = currency_settings

    async def format_page(self, menu: Pages, page: Item) -> discord.Embed:
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
