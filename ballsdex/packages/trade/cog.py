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
    BallEnabledTransform,
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

    coins = app_commands.Group(
        name=settings.currency_name, description="Trade with other players using coins"
    )

    def get_trade(
        self,
        interaction: discord.Interaction | None = None,
        *,
        channel: discord.TextChannel | None = None,
        user: discord.User | discord.Member = MISSING,
    ) -> tuple[TradeMenu, TradingUser] | tuple[None, None]:
        """
        Find an ongoing trade for the given interaction.
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
            return None, None
        if channel.id not in self.trades[guild.id]:
            return None, None
        to_remove: list[TradeMenu] = []
        for trade in self.trades[guild.id][channel.id]:
            if (
                trade.current_view.is_finished()
                or trade.trader1.cancelled
                or trade.trader2.cancelled
            ):
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
            return None, None

        for trade in to_remove:
            self.trades[guild.id][channel.id].remove(trade)
        return trade, trader

    async def check_trade_errors(
        self, interaction: discord.Interaction, amount: Optional[int] = None
    ) -> tuple[Optional[TradeMenu], Optional[TradingUser]]:
        """
        Helper function to check for trade errors.
        """
        trade, trader = self.get_trade(interaction)

        if trader is None:
            await interaction.response.send_message(
                "Unable to find ongoing trade.", ephemeral=True
            )
            return None, None

        if trader.locked:
            await interaction.response.send_message(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the trade instead.",
                ephemeral=True,
            )
            return None, None

        if amount is not None and amount <= 0:
            await interaction.response.send_message("The amount must be positive.", ephemeral=True)
            return None, None

        return trade, trader

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
        """
        if not countryball:
            return
        if not countryball.is_tradeable:
            await interaction.response.send_message(
                f"You cannot trade this {settings.collectible_name}.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        if countryball.favorite:
            view = ConfirmChoiceView(interaction)
            await interaction.followup.send(
                f"This {settings.collectible_name} is a favorite, "
                "are you sure you want to trade it?",
                view=view,
                ephemeral=True,
            )
            await view.wait()
            if not view.value:
                return

        trade, trader = await self.check_trade_errors(interaction)
        if not trade or not trader:
            return

        if countryball in trader.proposal:
            await interaction.followup.send(
                f"You already have this {settings.collectible_name} in your proposal.",
                ephemeral=True,
            )
            return
        if await countryball.is_locked():
            await interaction.followup.send(
                f"This {settings.collectible_name} is currently in an active trade or donation, "
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
    async def remove(
        self,
        interaction: discord.Interaction,
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
        shiny: bool | None = None,
    ):
        """
        Remove a countryball from the ongoing trade.
        """
        if not countryball:
            return

        trade, trader = await self.check_trade_errors(interaction)
        if not trade or not trader:
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
        trade, trader = await self.check_trade_errors(interaction)
        if not trade or not trader:
            return

        await trade.user_cancel(trader)
        await interaction.response.send_message("Trade cancelled.", ephemeral=True)

    @app_commands.command()
    async def history(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        sorting: app_commands.Choice[str],
        trade_user: discord.User | None = None,
        days: Optional[int] = None,
        countryball: BallEnabledTransform | None = None,
    ):
        """
        Show the history of your trades.
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

        if countryball:
            queryset = queryset.filter(
                Q(player1__tradeobjects__ballinstance__ball=countryball)
                | Q(player2__tradeobjects__ballinstance__ball=countryball)
            ).distinct()  # for some reason, this query creates a lot of duplicate rows?

        history = await queryset.order_by(sorting.value).prefetch_related("player1", "player2")

        if not history:
            await interaction.followup.send("No history found.", ephemeral=True)
            return
        source = TradeViewFormat(history, interaction.user.name, self.bot)
        pages = Pages(source=source, interaction=interaction)
        await pages.start()

    @coins.command(name="add")
    async def coins_add(self, interaction: discord.Interaction, amount: int):
        """
        Add coins to your trade proposal
        """
        trade, trader = await self.check_trade_errors(interaction)
        if not trade or not trader:
            return

        if trade:
            if amount > await trader.fetch_player_coins():
                await interaction.response.send_message(
                    f"You don't have enough {settings.currency_name} to add that amount."
                )
            else:
                await trader.add_coins(amount)
                await interaction.response.send_message(
                    f"Added {amount} {settings.currency_name} to your proposal."
                    f"Total in proposal: {trader.coins} {settings.currency_name}.",
                    ephemeral=True,
                )

    @coins.command(name="remove")
    async def coins_remove(self, interaction: discord.Interaction, amount: int):
        """
        Remove coins from your trade proposal
        """
        trade, trader = await self.check_trade_errors(interaction)
        if not trade or not trader:
            return

        if trader.locked:
            await interaction.response.send_message(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the trade instead.",
                ephemeral=True,
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "The amount to remove must be positive.", ephemeral=True
            )
            return
        if trade and trader:
            if amount > trader.coins:
                await interaction.response.send_message(
                    f"You can't remove more {settings.currency_name} than are in your proposal.",
                    ephemeral=True,
                )
                return
            await trader.remove_coins(amount)
            await interaction.response.send_message(
                f"Removed {amount} {settings.currency_name} from your proposal. "
                f"Remaining in proposal: {trader.coins} {settings.currency_name}.",
                ephemeral=True,
            )
