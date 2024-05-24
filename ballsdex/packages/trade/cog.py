import datetime
from collections import defaultdict
from typing import TYPE_CHECKING, Optional, cast

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import MISSING
from tortoise.expressions import Q

from ballsdex.core.models import Player
from ballsdex.core.models import Trade as TradeModel
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.paginator import Pages
from ballsdex.core.utils.transformers import (
    BallInstanceTransform,
    SpecialEnabledTransform,
    TradeCommandType,
)
from ballsdex.packages.trade.display import TradeViewFormat
from ballsdex.packages.trade.menu import TradeMenu
from ballsdex.packages.trade.trade_user import TradingUser
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Trade(commands.GroupCog):
    """
    Trade countryballs with other players.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.trades: dict[int, dict[int, list[TradeMenu]]] = defaultdict(lambda: defaultdict(list))

    def get_trade(
        self,
        interaction: discord.Interaction | None = None,
        *,
        channel: discord.TextChannel | None = None,
        user: discord.User | discord.Member = MISSING,
    ) -> tuple[TradeMenu, TradingUser] | tuple[None, None]:
        """
        Find an ongoing trade for the given interaction.

        Parameters
        ----------
        interaction: discord.Interaction
            The current interaction, used for getting the guild, channel and author.

        Returns
        -------
        tuple[TradeMenu, TradingUser] | tuple[None, None]
            A tuple with the `TradeMenu` and `TradingUser` if found, else `None`.
        """
        guild: discord.Guild
        if interaction:
            guild = cast(discord.Guild, interaction.guild)
            channel = cast(discord.TextChannel, interaction.channel)
            user = interaction.user
        elif channel:
            guild = channel.guild
        else:
            raise TypeError("Missing interaction or channel")

        if guild.id not in self.trades:
            return (None, None)
        if channel.id not in self.trades[guild.id]:
            return (None, None)
        to_remove: list[TradeMenu] = []
        for trade in self.trades[guild.id][channel.id]:
            if (
                trade.current_view.is_finished()
                or trade.trader1.cancelled
                or trade.trader2.cancelled
            ):
                # remove what was supposed to have been removed
                to_remove.append(trade)
                continue
            try:
                trader = trade._get_trader(user)
            except RuntimeError:
                continue
            else:
                break
        else:
            for trade in to_remove:
                self.trades[guild.id][channel.id].remove(trade)
            return (None, None)

        for trade in to_remove:
            self.trades[guild.id][channel.id].remove(trade)
        return (trade, trader)

    @app_commands.command()
    async def begin(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User):
        """
        Begin a trade with the chosen user.

        Parameters
        ----------
        user: discord.User
            The user you want to trade with
        """
        if user.bot:
            await interaction.response.send_message("You cannot trade with bots.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot trade with yourself.", ephemeral=True
            )
            return

        trade1, trader1 = self.get_trade(interaction)
        trade2, trader2 = self.get_trade(channel=interaction.channel, user=user)  # type: ignore
        if trade1 or trader1:
            await interaction.response.send_message(
                "You already have an ongoing trade.", ephemeral=True
            )
            return
        if trade2 or trader2:
            await interaction.response.send_message(
                "The user you are trying to trade with is already in a trade.", ephemeral=True
            )
            return

        player1, _ = await Player.get_or_create(discord_id=interaction.user.id)
        player2, _ = await Player.get_or_create(discord_id=user.id)
        if player2.discord_id in self.bot.blacklist:
            await interaction.response.send_message(
                "You cannot trade with a blacklisted user.", ephemeral=True
            )
            return

        menu = TradeMenu(
            self, interaction, TradingUser(interaction.user, player1), TradingUser(user, player2)
        )
        self.trades[interaction.guild.id][interaction.channel.id].append(menu)  # type: ignore
        await menu.start()
        await interaction.response.send_message("Trade started!", ephemeral=True)

    @app_commands.command(extras={"trade": TradeCommandType.PICK})
    async def add(
        self,
        interaction: discord.Interaction,
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
        shiny: bool | None = None,
    ):
        """
        Add a countryball to the ongoing trade.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to add to your proposal
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        shiny: bool
            Filter the results of autocompletion to shinies. Ignored afterwards.
        """
        if not countryball:
            return
        if not countryball.is_tradeable:
            await interaction.response.send_message(
                "You cannot trade this countryball.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        if countryball.favorite:
            view = ConfirmChoiceView(interaction)
            await interaction.followup.send(
                "This countryball is a favorite, are you sure you want to trade it?",
                view=view,
                ephemeral=True,
            )
            await view.wait()
            if not view.value:
                return

        trade, trader = self.get_trade(interaction)
        if not trade or not trader:
            await interaction.followup.send("You do not have an ongoing trade.", ephemeral=True)
            return
        if trader.locked:
            await interaction.followup.send(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the trade instead.",
                ephemeral=True,
            )
            return
        if countryball in trader.proposal:
            await interaction.followup.send(
                f"You already have this {settings.collectible_name} in your proposal.",
                ephemeral=True,
            )
            return
        if await countryball.is_locked():
            await interaction.followup.send(
                "This countryball is currently in an active trade or donation, "
                "please try again later.",
                ephemeral=True,
            )
            return

        await countryball.lock_for_trade()
        trader.proposal.append(countryball)
        await interaction.followup.send(
            f"{countryball.countryball.country} added.", ephemeral=True
        )

    @app_commands.command(extras={"trade": TradeCommandType.REMOVE})
    async def remove(self, interaction: discord.Interaction, countryball: BallInstanceTransform):
        """
        Remove a countryball from what you proposed in the ongoing trade.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to remove from your proposal
        """
        if not countryball:
            return

        trade, trader = self.get_trade(interaction)
        if not trade or not trader:
            await interaction.response.send_message(
                "You do not have an ongoing trade.", ephemeral=True
            )
            return
        if trader.locked:
            await interaction.response.send_message(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the trade instead.",
                ephemeral=True,
            )
            return
        if countryball not in trader.proposal:
            await interaction.response.send_message(
                f"That {settings.collectible_name} is not in your proposal.", ephemeral=True
            )
            return
        trader.proposal.remove(countryball)
        await interaction.response.send_message(
            f"{countryball.countryball.country} removed.", ephemeral=True
        )
        await countryball.unlock()

    @app_commands.command()
    async def cancel(self, interaction: discord.Interaction):
        """
        Cancel the ongoing trade.
        """
        trade, trader = self.get_trade(interaction)
        if not trade or not trader:
            await interaction.response.send_message(
                "You do not have an ongoing trade.", ephemeral=True
            )
            return

        await trade.user_cancel(trader)
        await interaction.response.send_message("Trade cancelled.", ephemeral=True)

    @app_commands.command()
    @app_commands.choices(
        sorting=[
            app_commands.Choice(name="Most Recent", value="-date"),
            app_commands.Choice(name="Oldest", value="date"),
        ]
    )
    async def history(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        sorting: app_commands.Choice[str],
        trade_user: discord.User | None = None,
        days: Optional[int] = None,
    ):
        """
        Show the history of your trades.

        Parameters
        ----------
        sorting: str
            The sorting order of the trades
        trade_user: discord.User | None
            The user you want to see your trade history with
        days: Optional[int]
            Retrieve trade history from last x days.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        user = interaction.user

        if days is not None and days < 0:
            await interaction.followup.send(
                "Invalid number of days. Please provide a non-negative value.", ephemeral=True
            )
            return

        if trade_user:
            queryset = TradeModel.filter(
                (Q(player1__discord_id=user.id, player2__discord_id=trade_user.id))
                | (Q(player1__discord_id=trade_user.id, player2__discord_id=user.id))
            )
        else:
            queryset = TradeModel.filter(
                Q(player1__discord_id=user.id) | Q(player2__discord_id=user.id)
            )

        if days is not None and days > 0:
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=days)
            queryset = queryset.filter(date__range=(start_date, end_date))

        history = await queryset.order_by(sorting.value).prefetch_related("player1", "player2")

        if not history:
            await interaction.followup.send("No history found.", ephemeral=True)
            return
        source = TradeViewFormat(history, interaction.user.name, self.bot)
        pages = Pages(source=source, interaction=interaction)
        await pages.start()
