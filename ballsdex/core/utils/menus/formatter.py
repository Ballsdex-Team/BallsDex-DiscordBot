from typing import TYPE_CHECKING

import discord
from django.db.models import QuerySet

from ballsdex.settings import settings
from bd_models.models import BallInstance

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

    from .menus import Menu

type Interaction = discord.Interaction["BallsDexBot"]


class Formatter[P, I: discord.ui.Item]:
    """
    A class that edits one of the layout's components from a page of the menu.

    Parameters
    ----------
    item: discord.ui.Item
        An item to edit from a page. Must be part of the view attached to the menu.
    """

    def __init__(self, item: I):
        self.menu: "Menu[P]"
        self.item = item

    def configure(self, menu: "Menu[P]"):
        self.menu = menu

    async def format_page(self, page: P) -> None:
        """
        Edits the `item` attached with the given page.

        Parameters
        ----------
        page: P
            The current page of the menu
        """
        raise NotImplementedError


class TextFormatter(Formatter[str, discord.ui.TextDisplay]):
    async def format_page(self, page):
        self.item.content = page


class SelectFormatter(Formatter[list[discord.SelectOption], discord.ui.Select]):
    async def format_page(self, page):
        self.item.options = page


class CountryballFormatter(Formatter[QuerySet[BallInstance], discord.ui.Select]):
    async def format_page(self, page):
        self.item.options = []
        async for ball in page:
            emoji = self.menu.bot.get_emoji(int(ball.countryball.emoji_id))
            favorite = f"{settings.favorited_collectible_emoji} " if ball.favorite else ""
            special = ball.specialcard.emoji if ball.specialcard else ""
            self.item.add_option(
                label=f"{favorite}{special}#{ball.pk:0X} {ball.countryball.country}",
                description=(
                    f"ATK: {ball.attack}({ball.attack_bonus:+d}%) "
                    f"• HP: {ball.health}({ball.health_bonus:+d}%) • "
                    f"{ball.catch_date.strftime('%Y/%m/%d | %H:%M')}"
                ),
                emoji=emoji,
                value=f"{ball.pk}",
            )
