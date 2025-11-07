from typing import TYPE_CHECKING

import discord
from discord.ui import ActionRow, Button, Container, Section, Select, Separator, TextDisplay, Thumbnail
from django.db.models import Count, F, Q, QuerySet

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import Formatter, Menu, TextFormatter, TextSource
from ballsdex.settings import settings
from bd_models.models import BallInstance, Player, Trade

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

    from .cog import Trade as TradeCog


class TradeListFormatter(Formatter[QuerySet[Trade], Select]):
    def __init__(self, item: Select, cog: "TradeCog", user: discord.abc.User):
        super().__init__(item)
        self.cog = cog
        self.user = user

    async def format_page(self, page: QuerySet[Trade]) -> None:
        self.item.options.clear()
        async for trade in page.annotate(
            p1_items=Count("tradeobject", filter=Q(tradeobject__player=F("player1"))),
            p2_items=Count("tradeobject", filter=Q(tradeobject__player=F("player2"))),
        ):
            self.item.add_option(
                label=f"Trade #{trade.pk:0X}",
                description=f"{trade.player1.discord_id} ({trade.p1_items} items) • "  # pyright: ignore[reportAttributeAccessIssue]
                f"{trade.player1.discord_id} ({trade.p2_items} items)",  # pyright: ignore[reportAttributeAccessIssue]
                value=trade.pk,
            )


class HistoryView(LayoutView):
    def __init__(self, bot: "BallsDexBot", trade: Trade, *, admin_view: bool = False, timeout: float | None = 180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.trade = trade
        self.admin_view = admin_view

    async def initialize(self, player1: Player, user1: discord.abc.User, player2: Player, user2: discord.abc.User):
        self.add_item(TextDisplay(f"## Trade #{self.trade.pk:0X} history"))
        self.add_item(await self.generate_container(player1, user1))
        self.add_item(await self.generate_container(player2, user2))
        if self.admin_view and settings.admin_url:
            self.add_item(
                ActionRow(
                    Button(label="View online", url=f"{settings.admin_url}/bd_models/trade/{self.trade.pk}/change/")
                )
            )

    async def generate_container(self, player: Player, user: discord.abc.User):
        container = Container()
        container.add_item(
            Section(
                TextDisplay(f"## {user.display_name}'s proposal"),
                TextDisplay("These items were traded away and no longer theirs."),
                accessory=Thumbnail(user.display_avatar.url),
            )
        )
        container.add_item(Separator())

        text = ""
        async for ball in BallInstance.objects.filter(tradeobject__trade=self.trade, tradeobject__player=player):
            description = ball.description(include_emoji=True, bot=self.bot, is_trade=True)
            if self.admin_view and settings.admin_url:
                description = f"[{description}]({settings.admin_url}/bd_models/ballinstance/{ball.pk}/change/)"
            text += f"- {description}\n"

        item = TextDisplay("")
        container.add_item(item)
        if text:
            menu = Menu(self.bot, self, TextSource(text, page_length=1900), TextFormatter(item))
            await menu.init(container=container)
        else:
            item.content = "Nothing traded."
        return container
