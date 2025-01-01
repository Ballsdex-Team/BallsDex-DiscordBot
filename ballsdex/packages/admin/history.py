import datetime

import discord
from discord import app_commands
from tortoise.expressions import Q

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import BallInstance, Trade
from ballsdex.core.utils.paginator import Pages
from ballsdex.packages.trade.display import TradeViewFormat, fill_trade_embed_fields
from ballsdex.packages.trade.trade_user import TradingUser
from ballsdex.settings import settings


class History(app_commands.Group):
    """
    Trade history management
    """

    @app_commands.command(name="user")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.choices(
        sorting=[
            app_commands.Choice(name="Most Recent", value="-date"),
            app_commands.Choice(name="Oldest", value="date"),
        ]
    )
    async def history_user(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        sorting: app_commands.Choice[str],
        user2: discord.User | None = None,
        days: int | None = None,
    ):
        """
        Show the history of a user.

        Parameters
        ----------
        user: discord.User
            The user you want to check the history of.
        sorting: str
            The sorting method you want to use.
        user2: discord.User | None
            The second user you want to check the history of.
        days: Optional[int]
            Retrieve trade history from last x days.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        if days is not None and days < 0:
            await interaction.followup.send(
                "Invalid number of days. Please provide a non-negative value.", ephemeral=True
            )
            return

        queryset = Trade.all()
        if user2:
            queryset = queryset.filter(
                (Q(player1__discord_id=user.id) & Q(player2__discord_id=user2.id))
                | (Q(player1__discord_id=user2.id) & Q(player2__discord_id=user.id))
            )
        else:
            queryset = queryset.filter(
                Q(player1__discord_id=user.id) | Q(player2__discord_id=user.id)
            )

        if days is not None and days > 0:
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=days)
            queryset = queryset.filter(date__range=(start_date, end_date))

        queryset = queryset.order_by(sorting.value).prefetch_related("player1", "player2")
        history = await queryset

        if not history:
            await interaction.followup.send("No history found.", ephemeral=True)
            return

        if user2:
            await interaction.followup.send(
                f"History of {user.display_name} and {user2.display_name}:"
            )

        source = TradeViewFormat(history, user.display_name, interaction.client, True)
        pages = Pages(source=source, interaction=interaction)
        await pages.start(ephemeral=True)

    @app_commands.command(name="countryball")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    @app_commands.choices(
        sorting=[
            app_commands.Choice(name="Most Recent", value="-date"),
            app_commands.Choice(name="Oldest", value="date"),
        ]
    )
    async def history_ball(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball_id: str,
        sorting: app_commands.Choice[str] | None = None,
        days: int | None = None,
    ):
        """
        Show the history of a countryball.

        Parameters
        ----------
        countryball_id: str
            The ID of the countryball you want to check the history of.
        sorting: str | None
            The sorting method you want to use.
        days: Optional[int]
            Retrieve ball history from last x days.
        """
        sort_value = sorting.value if sorting else "-date"

        try:
            pk = int(countryball_id, 16)
        except ValueError:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True
            )
            return

        ball = await BallInstance.get(id=pk)
        if not ball:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        if days is not None and days < 0:
            await interaction.followup.send(
                "Invalid number of days. Please provide a non-negative value.", ephemeral=True
            )
            return

        queryset = Trade.all()
        if days is None or days == 0:
            queryset = queryset.filter(tradeobjects__ballinstance_id=pk)
        else:
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=days)
            queryset = queryset.filter(
                tradeobjects__ballinstance_id=pk, date__range=(start_date, end_date)
            )
        trades = await queryset.order_by(sort_value).prefetch_related("player1", "player2")

        if not trades:
            await interaction.followup.send("No history found.", ephemeral=True)
            return

        source = TradeViewFormat(
            trades, f"{settings.collectible_name} {ball}", interaction.client, True
        )
        pages = Pages(source=source, interaction=interaction)
        await pages.start(ephemeral=True)

    @app_commands.command(name="trade")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def trade_info(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        trade_id: str,
    ):
        """
        Show the contents of a certain trade.

        Parameters
        ----------
        trade_id: str
            The ID of the trade you want to check the history of.
        """
        try:
            pk = int(trade_id, 16)
        except ValueError:
            await interaction.response.send_message(
                "The trade ID you gave is not valid.", ephemeral=True
            )
            return
        trade = await Trade.get(id=pk).prefetch_related("player1", "player2")
        if not trade:
            await interaction.response.send_message(
                "The trade ID you gave does not exist.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title=f"Trade {trade.pk:0X}",
            description=f"Trade ID: {trade.pk:0X}",
            timestamp=trade.date,
        )
        embed.set_footer(text="Trade date: ")
        fill_trade_embed_fields(
            embed,
            interaction.client,
            await TradingUser.from_trade_model(trade, trade.player1, interaction.client),
            await TradingUser.from_trade_model(trade, trade.player2, interaction.client),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
