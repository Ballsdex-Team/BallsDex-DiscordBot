from datetime import timedelta
from typing import TYPE_CHECKING, Literal, cast

import discord
from cachetools import LRUCache
from discord import app_commands
from discord.ext import commands
from django.db.models import Q
from django.utils import timezone

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import Menu, ModelSource
from ballsdex.core.utils.transformers import BallEnabledTransform, BallInstanceTransform, SpecialEnabledTransform
from bd_models.models import BallInstance, Player
from bd_models.models import Trade as TradeModel

from .errors import TradeError
from .history import HistoryView, TradeListFormatter
from .trade import TradeInstance, TradingUser

if TYPE_CHECKING:
    import discord.types.interactions

    from ballsdex.core.bot import BallsDexBot

type Interaction = discord.Interaction["BallsDexBot"]


class Trade(commands.GroupCog):
    # used by admin cog at runtime
    history_view_cls = HistoryView
    trade_list_fmt_cls = TradeListFormatter

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.lockdown: str | None = None
        self.trades: dict[int, TradeInstance] = {}
        self.user_cache: LRUCache[int, discord.User] = LRUCache(maxsize=2000)

    async def fetch_user(self, discord_id: int) -> discord.User:
        if cached := self.user_cache.get(discord_id, None):
            return cached
        user = await self.bot.fetch_user(discord_id)
        self.user_cache[user.id] = user
        return user

    async def get_trade(self, user: discord.Member | discord.User) -> None | tuple[TradeInstance, TradingUser]:
        trade = self.trades.get(user.id)
        if not trade:
            return None
        if not trade.active:
            del self.trades[trade.trader1.user.id]
            del self.trades[trade.trader2.user.id]
            await trade.cleanup()
            return None
        trader = trade.trader1 if trade.trader1.user == user else trade.trader2
        return trade, trader

    @app_commands.command()
    async def start(self, interaction: Interaction, user: discord.User):
        """
        Start trading with someone.

        Parameters
        ----------
        user: discord.User
            The user you want to trade with.
        """
        if self.lockdown is not None:
            await interaction.response.send_message(
                f"Trading has been globally disabled by the admins for the following reason: {self.lockdown}",
                ephemeral=True,
            )
            return

        if user.bot:
            await interaction.response.send_message("You cannot trade with bots.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message("You cannot trade with yourself.", ephemeral=True)
            return

        player1, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        player2, _ = await Player.objects.aget_or_create(discord_id=user.id)
        blocked = await player1.is_blocked(player2)
        if blocked:
            await interaction.response.send_message(
                "You cannot begin a trade with a user that you have blocked.", ephemeral=True
            )
            return
        blocked2 = await player2.is_blocked(player1)
        if blocked2:
            await interaction.response.send_message(
                "You cannot begin a trade with a user that has blocked you.", ephemeral=True
            )
            return
        if await self.get_trade(interaction.user) is not None:
            await interaction.response.send_message("You already have an active trade.", ephemeral=True)
            return
        if await self.get_trade(user) is not None:
            await interaction.response.send_message(f"{user.mention} already has an active trade.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        trade = TradeInstance.configure(self, (player1, interaction.user), (player2, user))
        self.trades[interaction.user.id] = trade
        self.trades[user.id] = trade
        await trade.trader1.refresh_container()
        await trade.trader2.refresh_container()
        trade.message = await interaction.channel.send(view=trade)  # type: ignore
        await interaction.followup.send("The trade has started.", ephemeral=True)

    @app_commands.command()
    async def add(self, interaction: Interaction, countryball: BallInstanceTransform):
        """
        Add a countryball to your trade proposal. You must have a trade open.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you are adding to your trade.
        """
        result = await self.get_trade(interaction.user)
        if result is None:
            await interaction.response.send_message("You do not have any active trade.", ephemeral=True)
            return
        trade, trader = result
        try:
            await trader.add_to_proposal(BallInstance.objects.filter(id=countryball.pk))
        except TradeError as e:
            await interaction.response.send_message(e.error_message, ephemeral=True)
        else:
            await trade.edit_message(None)
            await interaction.response.send_message(
                f"{countryball.description(is_trade=True, include_emoji=True, bot=self.bot)} added.", ephemeral=True
            )

    @app_commands.command()
    async def remove(self, interaction: Interaction, countryball: BallInstanceTransform):
        """
        Remove a countryball from your trade proposal. You must have a trade open.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you are removing from your trade.
        """
        result = await self.get_trade(interaction.user)
        if result is None:
            await interaction.response.send_message("You do not have any active trade.", ephemeral=True)
            return
        trade, trader = result
        try:
            await trader.remove_from_proposal(BallInstance.objects.filter(id=countryball.pk))
        except TradeError as e:
            await interaction.response.send_message(e.error_message, ephemeral=True)
        else:
            await trade.edit_message(None)
            await interaction.response.send_message(
                f"{countryball.description(is_trade=True, include_emoji=True, bot=self.bot)} removed.", ephemeral=True
            )

    @app_commands.command()
    async def history(
        self,
        interaction: Interaction,
        sorting: Literal["Recent", "Oldest"] = "Recent",
        trade_user: discord.User | None = None,
        days: int | None = None,
        countryball: BallEnabledTransform | None = None,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Show your trade history.

        Parameters
        ----------
        sorting: Literal["Recent", "Oldest"]
            The sorting order of your trades.
        trade_user: discord.User | None
            The user you want to filter your trade history with.
        days: int | None
            Retrieve trade history from the last x days at most.
        countryball: Ball | None
            The countryball you want to filter the trade history by.
        special: Special | None
            The special you want to filter the trade history by.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)

        user = interaction.user
        if sorting == "Recent":
            sort_value = "-date"
        else:
            sort_value = "date"

        if days is not None and days <= 0:
            await interaction.followup.send(
                "Invalid number of days. Please provide a strictly positive value.", ephemeral=True
            )
            return

        queryset = TradeModel.objects.order_by(sort_value).prefetch_related("player1", "player2")
        if trade_user:
            queryset = queryset.filter(
                (Q(player1__discord_id=user.id, player2__discord_id=trade_user.id))
                | (Q(player1__discord_id=trade_user.id, player2__discord_id=user.id))
            )
        else:
            queryset = queryset.filter(Q(player1__discord_id=user.id) | Q(player2__discord_id=user.id))

        if days is not None and days > 0:
            start_date = timezone.now() - timedelta(days=days)
            queryset = queryset.filter(date__ge=start_date)

        if countryball:
            queryset = queryset.filter(Q(tradeobjects__ballinstance__ball=countryball)).distinct()
        if special:
            queryset = queryset.filter(Q(tradeobjects__ballinstance__special=special)).distinct()

        if not await queryset.aexists():
            await interaction.followup.send("No history found.", ephemeral=True)
            return

        async def callback(interaction: Interaction):
            await interaction.response.defer(thinking=True, ephemeral=True)
            data = cast("discord.types.interactions.SelectMessageComponentInteractionData", interaction.data)
            trade = await TradeModel.objects.prefetch_related("player1", "player2").aget(pk=data["values"][0])
            view = HistoryView(self.bot, trade)
            await view.initialize(
                trade.player1,
                await self.fetch_user(trade.player1.discord_id),
                trade.player2,
                await self.fetch_user(trade.player2.discord_id),
            )
            await interaction.followup.send(view=view, ephemeral=True)

        view = LayoutView()
        view.add_item(discord.ui.TextDisplay("## Trade history"))
        action = discord.ui.ActionRow()
        select = discord.ui.Select(placeholder="Choose a trade to display")
        select.callback = callback
        action.add_item(select)
        view.add_item(action)
        menu = Menu(self.bot, view, ModelSource(queryset), TradeListFormatter(select, self, interaction.user))
        await menu.init()
        await interaction.followup.send(view=view, ephemeral=True)
