from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, AsyncIterator, List, Set, cast

import discord
from discord.ui import Button, View, button
from discord.utils import format_dt, utcnow
from tortoise import transactions

from ballsdex.core.models import BallInstance, Player, Trade, TradeCooldownPolicy, TradeObject
from ballsdex.core.utils import menus
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.paginator import Pages
from ballsdex.core.utils.utils import can_mention
from ballsdex.packages.balls.countryballs_paginator import CountryballsSource, CountryballsViewer
from ballsdex.packages.trade.display import fill_trade_embed_fields
from ballsdex.packages.trade.trade_user import TradingUser
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.packages.trade.cog import Trade as TradeCog

log = logging.getLogger("ballsdex.packages.trade.menu")
TRADE_TIMEOUT = 30


class InvalidTradeOperation(Exception):
    pass


class TradeView(View):
    def __init__(self, trade: TradeMenu):
        super().__init__(timeout=60 * TRADE_TIMEOUT + 1)
        self.trade = trade

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"], /) -> bool:
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
    async def lock(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        trader = self.trade._get_trader(interaction.user)
        if trader.locked:
            await interaction.response.send_message(
                "You have already locked your proposal!", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        await self.trade.lock(trader)
        if self.trade.trader1.locked and self.trade.trader2.locked:
            await interaction.followup.send(
                "Your proposal has been locked. Now confirm again to end the trade.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "Your proposal has been locked. "
                "You can wait for the other user to lock their proposal.",
                ephemeral=True,
            )

    @button(label="Reset", emoji="\N{DASH SYMBOL}", style=discord.ButtonStyle.secondary)
    async def clear(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        trader = self.trade._get_trader(interaction.user)
        await interaction.response.defer(thinking=True, ephemeral=True)

        if trader.locked:
            await interaction.followup.send(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the trade instead.",
                ephemeral=True,
            )
            return

        view = ConfirmChoiceView(
            interaction,
            accept_message="Clearing your proposal...",
            cancel_message="This request has been cancelled.",
        )
        await interaction.followup.send(
            "Are you sure you want to clear your proposal?", view=view, ephemeral=True
        )
        await view.wait()
        if not view.value:
            return

        if trader.locked:
            await interaction.followup.send(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the trade instead.",
                ephemeral=True,
            )
            return

        for countryball in trader.proposal:
            await countryball.unlock()

        trader.proposal.clear()
        await interaction.followup.send("Proposal cleared.", ephemeral=True)

    @button(
        label="Cancel trade",
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.danger,
    )
    async def cancel(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)

        view = ConfirmChoiceView(
            interaction,
            accept_message="Cancelling the trade...",
            cancel_message="This request has been cancelled.",
        )
        await interaction.followup.send(
            "Are you sure you want to cancel this trade?", view=view, ephemeral=True
        )
        await view.wait()
        if not view.value:
            return

        await self.trade.user_cancel(self.trade._get_trader(interaction.user))
        await interaction.followup.send("Trade has been cancelled.", ephemeral=True)


class ConfirmView(View):
    def __init__(self, trade: TradeMenu):
        super().__init__(timeout=60 * 14 + 55)
        self.trade = trade
        self.cooldown_duration = timedelta(seconds=10)

    async def on_timeout(self):
        """
        When the view times out, we cancel the trade.
        """
        if self.trade.task:
            self.trade.task.cancel()
        await self.trade.cancel("The trade has timed out.")

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"], /) -> bool:
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
    async def accept_button(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        trader = self.trade._get_trader(interaction.user)
        if trader.player.trade_cooldown_policy == TradeCooldownPolicy.COOLDOWN:
            if self.trade.cooldown_start_time is None:
                return

            elapsed = datetime.now(timezone.utc) - self.trade.cooldown_start_time
            if elapsed < self.cooldown_duration:
                remaining_time = datetime.now(timezone.utc) + (self.cooldown_duration - elapsed)
                remaining = format_dt(remaining_time, style="R")
                await interaction.response.send_message(
                    f"This trade can only be approved {remaining}, please use this "
                    "time to double check the items to prevent any unwanted trades.",
                    ephemeral=True,
                )
                return
        await interaction.response.defer(ephemeral=True, thinking=True)
        if trader.accepted:
            await interaction.response.send_message(
                "You have already accepted this trade.", ephemeral=True
            )
            return
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
    async def deny_button(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)

        view = ConfirmChoiceView(
            interaction,
            accept_message="Cancelling the trade...",
            cancel_message="This request has been cancelled.",
        )
        await interaction.followup.send(
            "Are you sure you want to cancel this trade?", view=view, ephemeral=True
        )
        await view.wait()
        if not view.value:
            return

        if self.trade.trader1.accepted and self.trade.trader2.accepted:
            await interaction.followup.send(
                "You can't cancel now; the trade has already gone through."
            )
            return

        await self.trade.user_cancel(self.trade._get_trader(interaction.user))
        await interaction.followup.send("Trade has been cancelled.", ephemeral=True)


class TradeMenu:
    def __init__(
        self,
        cog: TradeCog,
        interaction: discord.Interaction["BallsDexBot"],
        trader1: TradingUser,
        trader2: TradingUser,
    ):
        self.cog = cog
        self.bot = interaction.client
        self.channel: discord.TextChannel = cast(discord.TextChannel, interaction.channel)
        self.trader1 = trader1
        self.trader2 = trader2
        self.embed = discord.Embed()
        self.task: asyncio.Task | None = None
        self.current_view: TradeView | ConfirmView = TradeView(self)
        self.message: discord.Message
        self.cooldown_start_time: datetime | None = None

    def _get_trader(self, user: discord.User | discord.Member) -> TradingUser:
        if user.id == self.trader1.user.id:
            return self.trader1
        elif user.id == self.trader2.user.id:
            return self.trader2
        raise RuntimeError(f"User with ID {user.id} cannot be found in the trade")

    def _generate_embed(self):
        add_command = self.cog.add.extras.get("mention", "`/trade add`")
        remove_command = self.cog.remove.extras.get("mention", "`/trade remove`")
        view_command = self.cog.view.extras.get("mention", "`/trade view`")

        self.embed.title = f"{settings.plural_collectible_name.title()} trading"
        self.embed.color = discord.Colour.blurple()
        self.embed.description = (
            f"Add or remove {settings.plural_collectible_name} you want to propose "
            f"to the other player using the {add_command} and {remove_command} commands.\n"
            "Once you're finished, click the lock button below to confirm your proposal.\n"
            "You can also lock with nothing if you're receiving a gift.\n\n"
            "*This trade will timeout "
            f"{format_dt(utcnow() + timedelta(minutes=TRADE_TIMEOUT), style='R')}.*\n\n"
            f"Use the {view_command} command to see the full"
            f" list of {settings.plural_collectible_name}."
        )
        self.embed.set_footer(
            text="This message is updated every 15 seconds, "
            "but you can keep on editing your proposal."
        )

    async def update_message_loop(self):
        """
        A loop task that updates every 15 seconds with the new content.
        """

        assert self.task
        start_time = utcnow()

        while True:
            await asyncio.sleep(15)
            if utcnow() - start_time > timedelta(minutes=TRADE_TIMEOUT):
                self.bot.loop.create_task(self.cancel("The trade timed out"))
                return

            try:
                fill_trade_embed_fields(self.embed, self.bot, self.trader1, self.trader2)
                await self.message.edit(embed=self.embed)
            except Exception:
                log.exception(
                    "Failed to refresh the trade menu "
                    f"guild={self.message.guild.id} "  # type: ignore
                    f"trader1={self.trader1.user.id} trader2={self.trader2.user.id}"
                )
                self.bot.loop.create_task(self.cancel("The trade errored"))
                return

    async def start(self):
        """
        Start the trade by sending the initial message and opening up the proposals.
        """
        self._generate_embed()
        fill_trade_embed_fields(self.embed, self.bot, self.trader1, self.trader2)
        self.message = await self.channel.send(
            content=f"Hey {self.trader2.user.mention}, {self.trader1.user.name} "
            "is proposing a trade with you!",
            embed=self.embed,
            view=self.current_view,
            allowed_mentions=await can_mention([self.trader2.player]),
        )
        self.task = self.bot.loop.create_task(self.update_message_loop())

    async def cancel(self, reason: str = "The trade has been cancelled."):
        """
        Cancel the trade immediately.
        """
        if self.task:
            self.task.cancel()
        self.current_view.stop()

        for countryball in self.trader1.proposal + self.trader2.proposal:
            await countryball.unlock()

        for item in self.current_view.children:
            item.disabled = True  # type: ignore

        fill_trade_embed_fields(self.embed, self.bot, self.trader1, self.trader2)
        self.embed.colour = discord.Colour.dark_red()
        self.embed.description = f"**{reason}**"
        if getattr(self, "message", None):
            await self.message.edit(content=None, embed=self.embed, view=self.current_view)

    async def lock(self, trader: TradingUser):
        """
        Mark a user's proposal as locked, ready for next stage
        """
        trader.locked = True
        if self.trader1.locked and self.trader2.locked:
            if self.task:
                self.task.cancel()
            if not self.trader1.proposal and not self.trader2.proposal:
                await self.cancel("Nothing has been proposed in the trade, it has been cancelled.")
                return
            self.current_view.stop()
            fill_trade_embed_fields(self.embed, self.bot, self.trader1, self.trader2)

            self.embed.colour = discord.Colour.yellow()
            self.embed.description = (
                "Both users locked their propositions! Now confirm to conclude this trade."
            )
            self.cooldown_start_time = datetime.now(timezone.utc)
            self.current_view = ConfirmView(self)
            await self.message.edit(content=None, embed=self.embed, view=self.current_view)

    async def user_cancel(self, trader: TradingUser):
        """
        Register a user request to cancel the trade
        """
        trader.cancelled = True
        await self.cancel()

    @transactions.atomic()
    async def perform_trade(self):
        valid_transferable_countryballs: list[BallInstance] = []
        self.current_view.stop()

        trade = await Trade.create(player1=self.trader1.player, player2=self.trader2.player)

        for countryball in self.trader1.proposal:
            await countryball.refresh_from_db()
            if countryball.player.discord_id != self.trader1.player.discord_id:
                # This is a invalid mutation, the player is not the owner of the countryball
                raise InvalidTradeOperation()
            countryball.player = self.trader2.player
            countryball.trade_player = self.trader1.player
            countryball.favorite = False
            valid_transferable_countryballs.append(countryball)
            await TradeObject.create(
                trade=trade, ballinstance=countryball, player=self.trader1.player
            )

        for countryball in self.trader2.proposal:
            await countryball.refresh_from_db()
            if countryball.player.discord_id != self.trader2.player.discord_id:
                # This is a invalid mutation, the player is not the owner of the countryball
                raise InvalidTradeOperation()
            countryball.player = self.trader1.player
            countryball.trade_player = self.trader2.player
            countryball.favorite = False
            valid_transferable_countryballs.append(countryball)
            await TradeObject.create(
                trade=trade, ballinstance=countryball, player=self.trader2.player
            )

        for countryball in valid_transferable_countryballs:
            await countryball.unlock()
            await countryball.save()

    async def confirm(self, trader: TradingUser) -> bool:
        """
        Mark a user's proposal as accepted. If both user accept, end the trade now

        If the trade is concluded, return True, otherwise if an error occurs, return False
        """
        result = True
        trader.accepted = True
        fill_trade_embed_fields(self.embed, self.bot, self.trader1, self.trader2)
        if self.trader1.accepted and self.trader2.accepted:
            if self.task and not self.task.cancelled():
                # shouldn't happen but just in case
                self.task.cancel()

            self.embed.description = "Trade concluded!"
            self.embed.colour = discord.Colour.green()
            self.current_view.stop()
            for item in self.current_view.children:
                item.disabled = True  # type: ignore

            try:
                await self.perform_trade()
            except InvalidTradeOperation:
                log.warning(f"Illegal trade operation between {self.trader1=} and {self.trader2=}")
                self.embed.description = (
                    f":warning: An attempt to modify the {settings.plural_collectible_name} "
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


class CountryballsSelector(Pages):
    def __init__(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        balls: List[int],
        cog: TradeCog,
    ):
        self.bot = interaction.client
        self.interaction = interaction
        source = CountryballsSource(balls)
        super().__init__(source, interaction=interaction)
        self.add_item(self.select_ball_menu)
        self.add_item(self.confirm_button)
        self.add_item(self.select_all_button)
        self.add_item(self.clear_button)
        self.balls_selected: Set[BallInstance] = set()
        self.cog = cog

    async def set_options(self, balls: AsyncIterator[BallInstance]):
        options: List[discord.SelectOption] = []
        async for ball in balls:
            if ball.is_tradeable is False:
                continue
            emoji = self.bot.get_emoji(int(ball.countryball.emoji_id))
            favorite = f"{settings.favorited_collectible_emoji} " if ball.favorite else ""
            special = ball.special_emoji(self.bot, True)
            options.append(
                discord.SelectOption(
                    label=f"{favorite}{special}#{ball.pk:0X} {ball.countryball.country}",
                    description=f"ATK: {ball.attack_bonus:+d}% • HP: {ball.health_bonus:+d}% • "
                    f"Caught on {ball.catch_date.strftime('%d/%m/%y %H:%M')}",
                    emoji=emoji,
                    value=f"{ball.pk}",
                    default=ball in self.balls_selected,
                )
            )
        self.select_ball_menu.options = options
        self.select_ball_menu.max_values = len(options)

    @discord.ui.select(min_values=1, max_values=25)
    async def select_ball_menu(
        self, interaction: discord.Interaction["BallsDexBot"], item: discord.ui.Select
    ):
        for value in item.values:
            ball_instance = await BallInstance.get(id=int(value)).prefetch_related(
                "ball", "player"
            )
            self.balls_selected.add(ball_instance)
        await interaction.response.defer()

    @discord.ui.button(label="Select Page", style=discord.ButtonStyle.secondary)
    async def select_all_button(
        self, interaction: discord.Interaction["BallsDexBot"], button: Button
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        for ball in self.select_ball_menu.options:
            ball_instance = await BallInstance.get(id=int(ball.value)).prefetch_related(
                "ball", "player"
            )
            if ball_instance not in self.balls_selected:
                self.balls_selected.add(ball_instance)
        await interaction.followup.send(
            (
                f"All {settings.plural_collectible_name} on this page have been selected.\n"
                "Note that the menu may not reflect this change until you change page."
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.primary)
    async def confirm_button(
        self, interaction: discord.Interaction["BallsDexBot"], button: Button
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        trade, trader = self.cog.get_trade(interaction)
        if trade is None or trader is None:
            return await interaction.followup.send(
                "The trade has been cancelled or the user is not part of the trade.",
                ephemeral=True,
            )
        if trader.locked:
            return await interaction.followup.send(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the trade instead.",
                ephemeral=True,
            )
        if any(ball in trader.proposal for ball in self.balls_selected):
            return await interaction.followup.send(
                "You have already added some of the "
                f"{settings.plural_collectible_name} you selected.",
                ephemeral=True,
            )

        if len(self.balls_selected) == 0:
            return await interaction.followup.send(
                f"You have not selected any {settings.plural_collectible_name} "
                "to add to your proposal.",
                ephemeral=True,
            )
        for ball in self.balls_selected:
            if ball.is_tradeable is False:
                return await interaction.followup.send(
                    f"{settings.collectible_name.title()} #{ball.pk:0X} is not tradeable.",
                    ephemeral=True,
                )
            if await ball.is_locked():
                return await interaction.followup.send(
                    f"{settings.collectible_name.title()} #{ball.pk:0X} is locked "
                    "for trade and won't be added to the proposal.",
                    ephemeral=True,
                )
            view = ConfirmChoiceView(interaction)
            if ball.favorite:
                await interaction.followup.send(
                    f"One or more of the {settings.plural_collectible_name} is favorited, "
                    "are you sure you want to add it to the trade?",
                    view=view,
                    ephemeral=True,
                )
                await view.wait()
                if not view.value:
                    return
            trader.proposal.append(ball)
            await ball.lock_for_trade()
        grammar = (
            f"{settings.collectible_name}"
            if len(self.balls_selected) == 1
            else f"{settings.plural_collectible_name}"
        )
        await interaction.followup.send(
            f"{len(self.balls_selected)} {grammar} added to your proposal.", ephemeral=True
        )
        self.balls_selected.clear()

    @discord.ui.button(label="Clear", style=discord.ButtonStyle.danger)
    async def clear_button(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        self.balls_selected.clear()
        await interaction.followup.send(
            f"You have cleared all currently selected {settings.plural_collectible_name}."
            f"This does not affect {settings.plural_collectible_name} within your trade.\n"
            f"There may be an instance where it shows {settings.plural_collectible_name} on the"
            " current page as selected, this is not the case - "
            "changing page will show the correct state.",
            ephemeral=True,
        )


class BulkAddView(CountryballsSelector):
    async def on_timeout(self) -> None:
        return await super().on_timeout()


class TradeViewSource(menus.ListPageSource):
    def __init__(self, entries: List[TradingUser]):
        super().__init__(entries, per_page=25)

    async def format_page(self, menu, players: List[TradingUser]):
        menu.set_options(players)
        return True  # signal to edit the page


class TradeViewMenu(Pages):
    def __init__(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        proposal: List[TradingUser],
        cog: TradeCog,
    ):
        self.bot = interaction.client
        source = TradeViewSource(proposal)
        super().__init__(source, interaction=interaction)
        self.add_item(self.select_player_menu)
        self.cog = cog

    def set_options(self, players: List[TradingUser]):
        options: List[discord.SelectOption] = []
        for player in players:
            user_obj = player.user
            plural_check = (
                f"{settings.collectible_name}"
                if len(player.proposal) == 1
                else f"{settings.plural_collectible_name}"
            )
            options.append(
                discord.SelectOption(
                    label=f"{user_obj.display_name}",
                    description=(f"ID: {user_obj.id} | {len(player.proposal)} {plural_check}"),
                    value=f"{user_obj.id}",
                )
            )
        self.select_player_menu.options = options

    @discord.ui.select()
    async def select_player_menu(
        self, interaction: discord.Interaction["BallsDexBot"], item: discord.ui.Select
    ):
        await interaction.response.defer(thinking=True)
        player = await Player.get(discord_id=int(item.values[0]))
        trade, trader = self.cog.get_trade(interaction)
        if trade is None or trader is None:
            return await interaction.followup.send(
                "The trade has been cancelled or the user is not part of the trade.",
                ephemeral=True,
            )
        trade_player = (
            trade.trader1 if trade.trader1.user.id == player.discord_id else trade.trader2
        )
        ball_instances = trade_player.proposal
        if len(ball_instances) == 0:
            return await interaction.followup.send(
                f"{trade_player.user} has not added any {settings.plural_collectible_name}.",
                ephemeral=True,
            )

        paginator = CountryballsViewer(interaction, [x.pk for x in ball_instances])
        await paginator.start()
