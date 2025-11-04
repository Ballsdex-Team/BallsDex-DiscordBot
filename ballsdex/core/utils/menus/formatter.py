from typing import TYPE_CHECKING, Iterable

import discord
import discord.ui
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


class ItemFormatter(Formatter[Iterable[discord.ui.Item], discord.ui.Container]):
    """
    This formatter takes as source a list of UI items, and dynamically add them to the given container.
    Useful for iterations where a list of [`Section`][discord.ui.Section] or [`TextDisplay`][discord.ui.TextDisplay]
    need to be given.

    You are responsible of passing a list of items that respect the container limits. Use
    [`dynamic_chunks`][ballsdex.core.utils.menus.utils.dynamic_chunks] to pagify your items while respecting limits.

    Parameters
    ----------
    item: discord.ui.Container
        Must be of container type.
    position: int
        The position at which items must be inserted.
    footer: bool
        Whether to include a "Page 1/max" footer at the end.
    """

    def __init__(self, item: discord.ui.Container, position: int, footer: bool = True):
        super().__init__(item)
        self.position = position
        self.footer = footer

    async def format_page(self, page):
        for i, item in enumerate(self.item.children):
            if i > self.position:
                self.item.remove_item(item)
        for section in page:
            self.item.add_item(section)
        if self.footer and self.menu.source.get_max_pages() > 1:
            self.item.add_item(
                discord.ui.TextDisplay(f"-# Page {self.menu.current_page + 1}/{self.menu.source.get_max_pages()}")
            )


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
