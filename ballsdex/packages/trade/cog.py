import discord

from discord import app_commands
from discord.ext import commands

from typing import TYPE_CHECKING
from collections import defaultdict

from ballsdex.settings import settings
from ballsdex.core.models import Player
from ballsdex.core.utils.transformers import BallInstanceTransform
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.packages.trade.menu import TradeMenu, TradingUser

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Trade(commands.GroupCog):
    """
    Trade countryballs with other playersa
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.trades: dict[int, dict[int, list[TradeMenu]]] = defaultdict(lambda: defaultdict(list))

    def get_trade(
        self,
        interaction: discord.Interaction | None = None,
        *,
        channel: discord.TextChannel | None = None,
        user: discord.User | discord.Member | None = None,
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
            guild = interaction.guild
            channel = interaction.channel
            user = interaction.user
        else:
            guild = channel.guild

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
    async def begin(self, interaction: discord.Interaction, user: discord.User):
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
        trade2, trader2 = self.get_trade(channel=interaction.channel, user=user)
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
        menu = TradeMenu(
            self, interaction, TradingUser(interaction.user, player1), TradingUser(user, player2)
        )
        self.trades[interaction.guild.id][interaction.channel.id].append(menu)
        await menu.start()
        await interaction.response.send_message("Trade started!", ephemeral=True)

    @app_commands.command()
    async def add(self, interaction: discord.Interaction, countryball: BallInstanceTransform):
        """
        Add a countryball to the ongoing trade.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to add to your proposal
        """
        if not countryball:
            return
        if not countryball.countryball.tradeable:
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
        if countryball.id in self.bot.locked_balls:
            await interaction.followup.send(
                "This countryball is currently in an active trade or donation, "
                "please try again later.",
                ephemeral=True,
            )
            return

        self.bot.locked_balls[countryball.id] = None
        trader.proposal.append(countryball)
        await interaction.followup.send(
            f"{countryball.countryball.country} added.", ephemeral=True
        )

    @app_commands.command()
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
        del self.bot.locked_balls[countryball.id]
