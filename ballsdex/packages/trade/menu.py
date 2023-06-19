from __future__ import annotations

import discord
import asyncio
import logging

from typing import TYPE_CHECKING, cast
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from discord.ui import View, button, Button

from ballsdex.settings import settings
from ballsdex.core.models import Player, BallInstance

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.packages.trade.cog import Trade as TradeCog

log = logging.getLogger("ballsdex.packages.trade.menu")


class InvalidTradeOperation(Exception):
    pass


@dataclass(slots=True)
class TradingUser:
    user: discord.User | discord.Member
    player: Player
    proposal: list[BallInstance] = field(default_factory=list)
    locked: bool = False
    cancelled: bool = False
    accepted: bool = False


class TradeView(View):
    def __init__(self, trade: TradeMenu):
        super().__init__(timeout=900)
        self.trade = trade

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        try:
            self.trade._get_trader(interaction.user)
        except RuntimeError:
            await interaction.response.send_message(
                "You are not allowed to interact with this trade.", ephemeral=True
            )
            return False
        else:
            return True

    @button(label="Lock proposal", emoji="\N{LOCK}", style=discord.ButtonStyle.primary)
    async def lock(self, interaction: discord.Interaction, button: Button):
        trader = self.trade._get_trader(interaction.user)
        if trader.locked:
            await interaction.response.send_message(
                "You have already locked your proposal!", ephemeral=True
            )
            return
        await self.trade.lock(trader)
        if self.trade.trader1.locked and self.trade.trader2.locked:
            await interaction.response.send_message(
                "Your proposal has been locked. Now confirm again to end the trade.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Your proposal has been locked. "
                "You can wait for the other user to lock their proposal.",
                ephemeral=True,
            )

    @button(label="Reset", emoji="\N{DASH SYMBOL}", style=discord.ButtonStyle.secondary)
    async def clear(self, interaction: discord.Interaction, button: Button):
        trader = self.trade._get_trader(interaction.user)
        if trader.locked:
            await interaction.response.send_message(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the trade instead.",
                ephemeral=True,
            )
        else:
            trader.proposal.clear()
            await interaction.response.send_message("Proposal cleared.", ephemeral=True)

    @button(
        label="Cancel trade",
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.danger,
    )
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await self.trade.user_cancel(self.trade._get_trader(interaction.user))
        await interaction.response.send_message("Trade has been cancelled.", ephemeral=True)


class ConfirmView(View):
    def __init__(self, trade: TradeMenu):
        super().__init__(timeout=90)
        self.trade = trade

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        try:
            self.trade._get_trader(interaction.user)
        except RuntimeError:
            await interaction.response.send_message(
                "You are not allowed to interact with this trade.", ephemeral=True
            )
            return False
        else:
            return True

    @discord.ui.button(
        style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}"
    )
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        trader = self.trade._get_trader(interaction.user)
        if trader.accepted:
            await interaction.response.send_message(
                "You have already accepted this trade.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.trade.confirm(trader)
        if self.trade.trader1.accepted and self.trade.trader2.accepted:
            if result:
                await interaction.followup.send("The trade is now concluded.", ephemeral=True)
            else:
                await interaction.followup.send(
                    ":warning: An error occurred while concluding the trade.", ephemeral=True
                )
        else:
            await interaction.followup.send(
                "You have accepted the trade, waiting for the other user...", ephemeral=True
            )

    @discord.ui.button(
        style=discord.ButtonStyle.danger,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
    )
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        await self.trade.user_cancel(self.trade._get_trader(interaction.user))
        await interaction.response.send_message("Trade has been cancelled.", ephemeral=True)


class TradeMenu:
    def __init__(
        self,
        cog: TradeCog,
        interaction: discord.Interaction,
        trader1: TradingUser,
        trader2: TradingUser,
    ):
        self.cog = cog
        self.bot = cast("BallsDexBot", interaction.client)
        self.channel: discord.TextChannel = interaction.channel
        self.trader1 = trader1
        self.trader2 = trader2
        self.embed = discord.Embed()
        self.task: asyncio.Task | None = None
        self.current_view: TradeView | ConfirmView = TradeView(self)
        self.message: discord.Message

    def _get_trader(self, user: discord.User | discord.Member) -> TradingUser:
        if user.id == self.trader1.user.id:
            return self.trader1
        elif user.id == self.trader2.user.id:
            return self.trader2
        raise RuntimeError(f"User with ID {user.id} cannot be found in the trade")

    def _generate_embed(self):
        add_command = self.cog.add.extras.get("mention", "`/trade add`")
        remove_command = self.cog.remove.extras.get("mention", "`/trade remove`")

        self.embed.title = f"{settings.collectible_name.title()}s trading"
        self.embed.color = discord.Colour.blurple()
        self.embed.description = (
            f"Add or remove {settings.collectible_name}s you want to propose to the other player "
            f"using the {add_command} and {remove_command} commands.\n"
            "Once you're finished, click the lock button below to confirm your proposal.\n"
            "You can also lock with nothing if you're receiving a gift.\n\n"
            "*You have 15 minutes before this interaction ends.*"
        )
        self.embed.set_footer(
            text="This message is updated every 15 seconds, "
            "but you can keep on editing your proposal."
        )

    def _get_prefix_emote(self, trader: TradingUser) -> str:
        if trader.cancelled:
            return "\N{NO ENTRY SIGN}"
        elif trader.accepted:
            return "\N{WHITE HEAVY CHECK MARK}"
        elif trader.locked:
            return "\N{LOCK}"
        else:
            return ""

    def _build_list_of_strings(self, trader: TradingUser, short: bool = False) -> list[str]:
        # this builds a list of strings always lower than 1024 characters
        # while not cutting in the middle of a line
        proposal: list[str] = [""]
        i = 0

        for countryball in trader.proposal:
            cb_text = countryball.description(short=short, include_emoji=True, bot=self.bot)
            if trader.locked:
                text = f"- *{cb_text}*\n"
            else:
                text = f"- {cb_text}\n"
            if trader.cancelled:
                text = f"~~{text}~~"

            if len(text) + len(proposal[i]) > 1024:
                # move to a new list element
                i += 1
                proposal.append("")
            proposal[i] += text

        if not proposal[0]:
            proposal[0] = "*Empty*"

        return proposal

    def update_proposals(self, compact: bool = False):
        """
        Update the fields in the embed according to their current proposals.

        Parameters
        ----------
        compact: bool
            If `True`, display countryballs in a compact way.
        """
        self.embed.clear_fields()

        # first, build embed strings
        # to play around the limit of 1024 characters per field, we'll be using multiple fields
        # these vars are list of fields, being a list of lines to include
        trader1_proposal = self._build_list_of_strings(self.trader1, compact)
        trader2_proposal = self._build_list_of_strings(self.trader2, compact)

        # then display the text. first page is easy
        self.embed.add_field(
            name=f"{self._get_prefix_emote(self.trader1)} {self.trader1.user.name}",
            value=trader1_proposal[0],
            inline=True,
        )
        self.embed.add_field(
            name=f"{self._get_prefix_emote(self.trader2)} {self.trader2.user.name}",
            value=trader2_proposal[0],
            inline=True,
        )

        if len(trader1_proposal) > 1 or len(trader2_proposal) > 1:
            # we'll have to trick for displaying the other pages
            # fields have to stack themselves vertically
            # to do this, we add a 3rd empty field on each line (since 3 fields per line)
            i = 1
            while i < len(trader1_proposal) or i < len(trader2_proposal):
                self.embed.add_field(name="\u200B", value="\u200B", inline=True)  # empty

                if i < len(trader1_proposal):
                    self.embed.add_field(name="\u200B", value=trader1_proposal[i], inline=True)
                else:
                    self.embed.add_field(name="\u200B", value="\u200B", inline=True)

                if i < len(trader2_proposal):
                    self.embed.add_field(name="\u200B", value=trader2_proposal[i], inline=True)
                else:
                    self.embed.add_field(name="\u200B", value="\u200B", inline=True)
                # always add an empty field at the end, otherwise the alignment is off
                self.embed.add_field(name="\u200B", value="\u200B", inline=True)
                i += 1

        if len(self.embed) > 6000 and not compact:
            self.update_proposals(compact=True)

    async def update_message_loop(self):
        """
        A loop task that updates each 5 second the menu with the new content.
        """

        assert self.task
        start_time = datetime.utcnow()

        while True:
            await asyncio.sleep(15)
            if datetime.utcnow() - start_time > timedelta(minutes=15):
                self.embed.colour = discord.Colour.dark_red()
                await self.cancel("The trade timed out")
                return

            try:
                self.update_proposals()
                await self.message.edit(embed=self.embed)
            except Exception:
                log.exception(
                    f"Failed to refresh the trade menu guild={self.message.guild.id} "
                    f"trader1={self.trader1.user.id} trader2={self.trader2.user.id}"
                )
                self.embed.colour = discord.Colour.dark_red()
                await self.cancel("The trade timed out")
                return

    async def start(self):
        """
        Start the trade by sending the initial message and opening up the proposals.
        """
        self._generate_embed()
        self.update_proposals()
        self.message = await self.channel.send(
            content=f"Hey {self.trader2.user.mention}, {self.trader1.user.name} "
            "is proposing a trade with you!",
            embed=self.embed,
            view=self.current_view,
        )
        self.task = self.bot.loop.create_task(self.update_message_loop())

    async def cancel(self, reason: str = "The trade has been cancelled."):
        """
        Cancel the trade immediately.
        """
        if self.task:
            self.task.cancel()

        for countryball in self.trader1.proposal + self.trader2.proposal:
            del self.bot.locked_balls[countryball.id]

        self.current_view.stop()
        for item in self.current_view.children:
            item.disabled = True

        self.update_proposals()
        self.embed.description = f"**{reason}**"
        await self.message.edit(content=None, embed=self.embed, view=self.current_view)

    async def lock(self, trader: TradingUser):
        """
        Mark a user's proposal as locked, ready for next stage
        """
        trader.locked = True
        if self.trader1.locked and self.trader2.locked:
            if self.task:
                self.task.cancel()
            self.current_view.stop()
            self.update_proposals()

            self.embed.colour = discord.Colour.yellow()
            self.embed.description = (
                "Both users locked their propositions! Now confirm to conclude this trade."
            )
            self.current_view = ConfirmView(self)
            await self.message.edit(content=None, embed=self.embed, view=self.current_view)

    async def user_cancel(self, trader: TradingUser):
        """
        Register a user request to cancel the trade
        """
        trader.cancelled = True
        self.embed.colour = discord.Colour.red()
        await self.cancel()

    async def perform_trade(self):
        valid_transferable_countryballs: list[BallInstance] = []

        for countryball in self.trader1.proposal:
            await countryball.refresh_from_db()
            if countryball.player.discord_id != self.trader1.player.discord_id:
                # This is a invalid mutation, the player is not the owner of the countryball
                raise InvalidTradeOperation()
            countryball.player = self.trader2.player
            countryball.trade_player = self.trader1.player
            countryball.favorite = False
            valid_transferable_countryballs.append(countryball)

        for countryball in self.trader2.proposal:
            if countryball.player.discord_id != self.trader2.player.discord_id:
                # This is a invalid mutation, the player is not the owner of the countryball
                raise InvalidTradeOperation()
            countryball.player = self.trader1.player
            countryball.trade_player = self.trader2.player
            countryball.favorite = False
            valid_transferable_countryballs.append(countryball)

        for countryball in valid_transferable_countryballs:
            await countryball.save()
            del self.bot.locked_balls[countryball.id]

    async def confirm(self, trader: TradingUser) -> bool:
        """
        Mark a user's proposal as accepted. If both user accept, end the trade now

        If the trade is concluded, return True, otherwise if an error occurs, return False
        """
        result = True
        trader.accepted = True
        self.update_proposals()
        if self.trader1.accepted and self.trader2.accepted:
            if self.task and not self.task.cancelled():
                # shouldn't happen but just in case
                self.task.cancel()

            self.embed.description = "Trade concluded!"
            self.embed.colour = discord.Colour.green()
            self.current_view.stop()
            for item in self.current_view.children:
                item.disabled = True

            try:
                await self.perform_trade()
            except InvalidTradeOperation:
                log.warning(f"Illegal trade operation between {self.trader1=} and {self.trader2=}")
                self.embed.description = (
                    f":warning: An attempt to modify the {settings.collectible_name}s "
                    "during the trade was detected and the trade was cancelled."
                )
                self.embed.colour = discord.Colour.red()
                result = False
            except Exception:
                log.exception(f"Failed to conclude trade {self.trader1=} {self.trader2=}")
                self.embed.description = "An error occured when concluding the trade."
                self.embed.colour = discord.Colour.red()
                result = False

        await self.message.edit(content=None, embed=self.embed, view=self.current_view)
        return result
