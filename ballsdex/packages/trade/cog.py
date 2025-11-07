from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.utils.transformers import BallInstanceTransform
from bd_models.models import BallInstance, Player

from .errors import TradeError
from .trade import TradeInstance, TradingUser

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

type Interaction = discord.Interaction["BallsDexBot"]


class Trade(commands.GroupCog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.lockdown: str | None = None
        self.trades: dict[int, TradeInstance] = {}

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
        if self.get_trade(interaction.user) is not None:
            await interaction.response.send_message("You already have an active trade.", ephemeral=True)
            return
        if self.get_trade(user) is not None:
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
