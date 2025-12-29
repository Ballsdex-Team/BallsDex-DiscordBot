"""
This file contains most of the logic behind trading. It is composed of two main classes: `TradingUser` and
`TradeInstance`. They act as data models, contain API functions, and also work as components to be directly displayed
on Discord.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

import discord
from asgiref.sync import sync_to_async
from discord.ui import ActionRow, Button, Item, Section, Select, Separator, TextDisplay, TextInput, Thumbnail
from discord.utils import format_dt
from django.db import transaction
from django.utils import timezone

from ballsdex.core.discord import UNKNOWN_INTERACTION, Container, LayoutView, Modal
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.menus import CountryballFormatter, Menu, ModelSource, TextFormatter, TextSource
from bd_models.models import BallInstance, Player, Trade, TradeObject
from settings.models import settings
from settings.utils import format_currency

from .errors import (
    AlreadyLockedError,
    CancelledError,
    IntegrityError,
    LockedError,
    NotProposedError,
    NotTradeableError,
    OwnershipError,
    SynchronizationError,
    TradeError,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot

    from .cog import Trade as TradeCog

type Interaction = discord.Interaction[BallsDexBot]

log = logging.getLogger(__name__)

TRADE_TIMEOUT = 60 * 30


class SetMoneyModal(Modal, title="Set money offering"):
    proposal = TextInput(label=f"How much {settings.currency_name} to propose?", style=discord.TextStyle.short)

    def __init__(self, trading_user: TradingUser):
        super().__init__()
        self.trading_user = trading_user

    async def interaction_check(self, interaction: Interaction) -> bool:
        if not interaction.user.id == self.trading_user.user.id:
            await interaction.response.send_message(
                "You are not allowed to do this, edit your own trade.", ephemeral=True
            )
            return False
        return await super().interaction_check(interaction)

    async def on_submit(self, interaction: Interaction):
        if self.trading_user.locked:
            await interaction.response.send_message("You have already locked your proposal!", ephemeral=True)
            return
        try:
            proposal_amount = int(self.proposal.value.strip())
        except ValueError:
            await interaction.response.send_message("This number could not be parsed.", ephemeral=True)
            return
        await self.trading_user.player.arefresh_from_db(fields=["money"])
        if not self.trading_user.player.can_afford(proposal_amount):
            await interaction.response.send_message("You cannot afford that amount.", ephemeral=True)
            return
        await interaction.response.defer()
        self.trading_user.money = proposal_amount
        await self.trading_user.view.edit_message(interaction)


class TradingUser(Container):
    """
    Represent one user part of a trade.

    Parameters
    ----------
    trade: TradeInstance
        The trade instance attached to this user.
    player: Player
        The fetched player model of the user.
    user: discord.abc.User
        The Discord user model.

    Attributes
    ----------
    proposal: set[int]
        The set of countryball IDs in the user's proposal.
    locked: bool
        `True` if the user locked their proposal.
    cancelled: bool
        `True` if the user cancelled the trade.
    confirmed: bool
        `True` if the user confirmed the trade.
    menu: Menu[QuerySet[BallInstance]] | Menu[str]
        The pagination menu for this user. This is a Select paginator before locking, and a Text source after locking.
    """

    def __init__(self, trade: TradeInstance, player: Player, user: discord.abc.User):
        super().__init__()
        self.trade = trade
        self.cog = trade.cog
        self.player = player
        self.user = user
        self.proposal: set[int] = set()
        self.money = 0
        self.locked: bool = False
        self.cancelled: bool = False
        self.confirmed: bool = False

        self.menu = Menu(
            self.cog.bot, trade, ModelSource(self.get_queryset()), CountryballFormatter(self.select_menu, max_values=25)
        )

        self.view: TradeInstance

    def __repr__(self) -> str:
        return f"<TradingUser player_id={self.player.pk} discord_id={self.user.id}>"

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id not in (self.trade.trader1.user.id, self.trade.trader2.user.id):
            await interaction.response.send_message("You are not part of this trade!", ephemeral=True)
            return False
        return True

    # ==== Utils ====
    def get_queryset(self) -> "QuerySet[BallInstance]":
        """
        Get a prepared queryset with the countryballs proposed by this user.
        """
        if not self.proposal:
            return BallInstance.objects.none()
        return BallInstance.objects.filter(id__in=self.proposal)

    # ==== Container items ====

    proposal_list = TextDisplay("")
    buttons = ActionRow()

    async def set_currency(self, interaction: Interaction):
        modal = SetMoneyModal(self)
        await interaction.response.send_modal(modal)
        await modal.wait()

    @buttons.button(label="Lock proposal", emoji="\N{LOCK}", style=discord.ButtonStyle.primary)
    async def lock_button(self, interaction: Interaction, button: Button):
        if not interaction.user.id == self.user.id:
            await interaction.response.send_message(
                "You are not allowed to do this, edit your own trade.", ephemeral=True
            )
            return
        if self.locked:
            await interaction.response.send_message("You have already locked your proposal!", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            await self.lock()
        except TradeError as e:
            await interaction.followup.send(e.error_message, ephemeral=True)
        else:
            await self.view.edit_message(interaction)

    @buttons.button(label="Reset", emoji="\N{DASH SYMBOL}", style=discord.ButtonStyle.secondary)
    async def clear_button(self, interaction: Interaction, button: Button):
        if not interaction.user.id == self.user.id:
            await interaction.response.send_message(
                "You are not allowed to do this, edit your own trade.", ephemeral=True
            )
            return
        if self.locked:
            await interaction.response.send_message("You have already locked your proposal!", ephemeral=True)
            return
        view = ConfirmChoiceView(interaction, accept_message="Clearing your proposal...")
        await interaction.response.send_message(
            "Are you sure you want to clear your proposal?", view=view, ephemeral=True
        )
        await view.wait()
        if not view.value:
            return

        try:
            await self.clear()
        except TradeError as e:
            await interaction.followup.send(e.error_message, ephemeral=True)
        else:
            await self.view.edit_message(interaction)

    @buttons.button(
        label="Cancel trade",
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.danger,
    )
    async def cancel_button(self, interaction: Interaction, button: Button):
        if not interaction.user.id == self.user.id:
            await interaction.response.send_message(
                "You are not allowed to do this, click your own button.", ephemeral=True
            )
            return
        view = ConfirmChoiceView(
            interaction, accept_message="Cancelling the trade...", cancel_message="This request has been cancelled."
        )
        await interaction.response.send_message(
            "Are you sure you want to cancel this trade?", view=view, ephemeral=True
        )
        await view.wait()
        if not view.value:
            return

        try:
            await self.cancel()
        except TradeError as e:
            await interaction.followup.send(e.error_message, ephemeral=True)
        else:
            await self.view.edit_message(None)

    @buttons.button(
        label="Confirm", emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.success
    )
    async def confirm_button(self, interaction: Interaction, button: Button):
        if not interaction.user.id == self.user.id:
            await interaction.response.send_message(
                "You are not allowed to do this, click your own button.", ephemeral=True
            )
            return
        await interaction.response.defer()
        try:
            await self.confirm()
        except TradeError as e:
            await interaction.followup.send(e.error_message, ephemeral=True)
        else:
            await self.view.edit_message(interaction)

    select_row = ActionRow()

    @select_row.select(placeholder="Click to remove an item", min_values=1)
    async def select_menu(self, interaction: Interaction, select: Select):
        if not interaction.user.id == self.user.id:
            await interaction.response.send_message(
                "You are not allowed to do this, edit your own trade.", ephemeral=True
            )
            return
        await interaction.response.defer()
        try:
            await self.remove_from_proposal(BallInstance.objects.filter(id__in=(int(x) for x in select.values)))
        except TradeError as e:
            await interaction.followup.send(e.error_message, ephemeral=True)
        else:
            await self.view.edit_message(interaction)

    # ==== Display helpers ====

    async def refresh_container(self):
        """
        Rebuild this container's items with the current state.
        """
        self.clear_items()

        section = Section(
            TextDisplay(f"## {self.user.display_name}'s proposal"), accessory=Thumbnail(self.user.display_avatar.url)
        )
        if self.view.cancelled:
            if self.cancelled:
                self.accent_colour = discord.Colour.red()
                section.add_item(TextDisplay("You have cancelled the trade."))
            else:
                section.add_item(TextDisplay("The trade has been cancelled."))
        elif self.confirmed:
            self.accent_colour = discord.Colour.green()
            section.add_item(TextDisplay("You have confirmed your trade proposal."))
        elif self.view.confirmation_phase:
            self.accent_colour = discord.Colour.gold()
            section.add_item(TextDisplay("You have both locked your proposals, review and confirm the trade."))
        elif self.locked:
            self.accent_colour = discord.Colour.yellow()
            section.add_item(
                TextDisplay(
                    "You have locked your proposal. "
                    "Wait for the other player to lock his proposal before finishing the trade."
                )
            )
        else:
            self.accent_colour = discord.Colour.blue()
            add_cmd = self.cog.add.extras.get("mention", "`/trade add`")
            del_cmd = self.cog.remove.extras.get("mention", "`/trade remove`")
            section.add_item(TextDisplay(f"You can edit your proposal with {add_cmd} and {del_cmd}."))

        self.add_item(section)
        self.add_item(Separator())

        # update disabled states
        self.lock_button.disabled = self.clear_button.disabled = self.select_menu.disabled = (
            self.locked or self.trade.cancelled
        )
        self.cancel_button.disabled = self.trade.cancelled

        if settings.currency_enabled:
            button = Button(label="Change", style=discord.ButtonStyle.primary)
            button.callback = self.set_currency
            currency_section = Section(
                TextDisplay(f"{settings.currency_name} proposed: {format_currency(self.money)}"), accessory=button
            )
            self.add_item(currency_section)

        if not self.locked:
            self.select_menu.options.clear()  # pyright: ignore[reportAttributeAccessIssue]
            self.add_item(self.select_row)
            # refresh the source data
            if self.proposal:
                cast(ModelSource, self.menu.source).queryset = self.get_queryset().order_by("locked")
                # this will insert the controls right beneath the select menu
                await self.menu.init(container=self)
            else:
                self.select_menu.add_option(label="Nothing yet")
                self.select_menu.disabled = True
                self.select_menu.max_values = 1
        else:
            self.add_item(self.proposal_list)
            if self.proposal:
                await self.menu.init(container=self)

        self.buttons.clear_items()
        if self.view.confirmation_phase:
            self.buttons.add_item(self.confirm_button)
        else:
            self.buttons.add_item(self.lock_button)
            self.buttons.add_item(self.clear_button)
        self.buttons.add_item(self.cancel_button)
        self.add_item(self.buttons)

    # ==== API functions ====

    async def add_to_proposal(self, queryset: "QuerySet[BallInstance]"):
        """
        Add countryballs to a trader's proposal.

        If an error is raised, the state of the given countryballs will not be edited.

        Parameters
        ----------
        queryset: QuerySet[BallInstance]
            The queryset of countryballs being added. This must not be a list of already fetched objects.

        Raises
        ------
        LockedError
            The proposal is locked
        OwnershipError
            One of the countryballs is not owned by the trading user
        AlreadyLockedError
            One of the countryballs is locked in a different trade
        NotTradeableError
            One of the countryballs is not tradeable
        """
        if self.locked:
            raise LockedError()
        if self.view.cancelled:
            raise CancelledError()
        proposal: set[int] = set()
        async for ball in queryset.only(
            "id", "locked", "player_id", "tradeable", "ball__tradeable", "special__tradeable"
        ):
            if ball.player_id != self.player.pk:
                raise OwnershipError()
            if await ball.is_locked(refresh=False):
                raise AlreadyLockedError()
            if not ball.is_tradeable:
                raise NotTradeableError()
            proposal.add(ball.pk)
        await queryset.aupdate(locked=timezone.now())
        self.proposal.update(proposal)

    async def remove_from_proposal(self, queryset: "QuerySet[BallInstance]"):
        """
        Remove the given countryball from the trader's proposal.

        Parameters
        ----------
        queryset: QuerySet[BallInstance]
            The queryset of countryballs being removed. This must not be a list of already fetched objects.

        Raises
        ------
        LockedError
            The proposal is locked
        NotProposedError
            One or more countryballs were not listed in this proposal
        """
        if self.locked:
            raise LockedError()
        if self.view.cancelled:
            raise CancelledError()
        ids: set[int] = {x.pk async for x in queryset.only("pk")}
        if not ids.issubset(self.proposal):
            raise NotProposedError()
        self.proposal.difference_update(ids)
        await queryset.aupdate(locked=None)

    async def lock(self):
        """
        Lock the proposal, preventing items from being added or removed.

        Raises
        ------
        LockedError
            The trade is already locked
        CancelledError
            The trade is cancelled
        """
        if self.locked:
            raise LockedError()
        if self.view.cancelled:
            raise CancelledError()
        self.locked = True

        if not self.proposal:
            self.proposal_list.content = "Nothing proposed"
            return

        # replace the select menu with immutable text
        text = ""
        async for ball in self.get_queryset().prefetch_related("special"):
            text += f"- {ball.description(include_emoji=True, bot=self.cog.bot, is_trade=True)}\n"
        self.menu = Menu(self.cog.bot, self.view, TextSource(text, page_length=1800), TextFormatter(self.proposal_list))

    async def clear(self):
        """
        Remove all items from the proposal.

        Raises
        ------
        LockedError
            The trade is already locked
        CancelledError
            The trade is cancelled
        """
        if self.locked:
            raise AlreadyLockedError()
        if self.view.cancelled:
            raise CancelledError()
        await self.get_queryset().aupdate(locked=False)
        self.proposal.clear()

    async def cancel(self):
        """
        Cancel the trade.
        """
        self.cancelled = True
        self.view.stop()
        await self.view.cleanup()

    async def confirm(self):
        """
        Confirm the trade for this user. If the other user confirmed, this triggers the end of the trade.

        Raises
        ------
        SynchronizationError
            The trade is already being finished or has finished. This happens when duplicated calls are received.
        AssertError
            The state does not allow the trade to be finished (cancelled, not locked on both sides). This should not
            happen in a normal UI path.
        IntegrityError
            The trade is being finished, but a mutation has been detected and the trade will be cancelled. This usually
            happens if a proposed countryball is found out to not belong to the original user at this time.
        """
        # this should not be false, but it's safer to crash if that happens
        assert self.view.confirmation_phase is True
        self.confirmed = True
        if self.view.trader1.confirmed and self.view.trader2.confirmed:
            await self.view.finish_trade()


class TradeInstance(LayoutView):
    """
    A trade instance. This doubles as a [`LayoutView`][discord.ui.LayoutView].

    Attributes
    ----------
    trader1: TradingUser
        The first trading user, also a [`Container`][discord.ui.Container].
    trader2: TradingUser
        The second trading user, also a [`Container`][discord.ui.Container].
    message: discord.Message
        The message that was sent with this view. This must be set immediately after sending. Not compatible with a
        webhook response.
    """

    def __init__(self, cog: "TradeCog"):
        super().__init__(timeout=TRADE_TIMEOUT)
        self.cog = cog
        self.trader1: TradingUser
        self.trader2: TradingUser
        self.message: discord.Message

        self.confirmation_lock = asyncio.Lock()
        self.edit_lock = asyncio.Lock()
        self.next_edit_interaction: Interaction | None = None

        self.timeout_task = asyncio.create_task(self._timeout(), name=f"trade-timeout-{id(self)}")

    async def on_error(self, interaction: Interaction, error: Exception, item: Item) -> None:
        if isinstance(error, discord.NotFound) and error.code in UNKNOWN_INTERACTION:
            log.warning("Expired interaction", exc_info=error)
            return
        log.exception(f"Error in trade between {self.trader1} and {self.trader2}", exc_info=error)
        await self.cleanup()
        send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await send("An error occured, the trade will be cancelled.", ephemeral=True)
        self.add_item(
            TextDisplay("An error occured and the trade has been cancelled! Contact support if this persists.")
        )
        await self.message.edit(view=self)

    async def _timeout(self):
        await asyncio.sleep(TRADE_TIMEOUT)
        if self.active:
            await self._cleanup()

    @classmethod
    def configure(
        cls, cog: "TradeCog", trader1: tuple[Player, discord.abc.User], trader2: tuple[Player, discord.abc.User]
    ):
        trade = cls(cog)
        trade.trader1 = TradingUser(trade, *trader1)
        trade.trader2 = TradingUser(trade, *trader2)
        trade.add_item(TextDisplay(f"Hey {trader2[1].mention}, {trader1[1].mention} is proposing a trade!"))
        trade.add_item(trade.trader1)
        trade.add_item(trade.trader2)
        timeout = datetime.now() + timedelta(seconds=TRADE_TIMEOUT)
        trade.add_item(TextDisplay(f"-# This trade will timeout {format_dt(timeout, style='R')}."))
        return trade

    @property
    def cancelled(self):
        """
        `True` if any of the users cancelled.
        """
        return self.trader1.cancelled or self.trader2.cancelled

    @property
    def active(self):
        """
        `True` if the trade is still active and hasn't timed out.
        """
        return not self.is_finished() and not self.cancelled

    @property
    def confirmation_phase(self):
        """
        `True` if both users have locked and haven't cancelled.
        """
        return self.trader1.locked and self.trader2.locked and not self.cancelled

    async def edit_message(self, interaction: Interaction | None):
        """
        A helper function to edit the main message while avoiding ratelimits.

        If an edit request is made while we're already waiting for an edit response, then the request
        is queued for later. If another request comes shortly after, then the first request is discarded.

        This can also be represented as a LIFO queue of size 1.

        Example
        -------
        --> R1 (request 1) arrives
        --> HTTP call for R1 is made
        --> R2 arrives
        --> R3 arrives
        <-- R1 finished
        --> HTTP call for R3 is made
        In this example, request R2 has been discarded since we have received another edit request before R1 finished.
        """
        if interaction is not None:
            self.next_edit_interaction = interaction
        if self.edit_lock.locked():
            return
        async with self.edit_lock:
            if self.next_edit_interaction is None:
                # this is a situation where we need to edit the message but without an interaction that owns it
                # (when using slash commands instead of buttons), so we fall back on a different endpoint
                await asyncio.sleep(0.5)
                await self.trader1.refresh_container()
                await self.trader2.refresh_container()
                await self.message.edit(view=self)
                return
            while self.next_edit_interaction is not None:
                inter = self.next_edit_interaction
                self.next_edit_interaction = None
                await asyncio.sleep(0.5)
                await self.trader1.refresh_container()
                await self.trader2.refresh_container()
                if self.is_finished():  # trade completed or timed out
                    for children in self.walk_children():
                        if hasattr(children, "disabled"):
                            children.disabled = True  # type: ignore
                await inter.edit_original_response(view=self)
                if self.is_finished():
                    break

    @transaction.atomic()
    def perform_trade_operation(self) -> Trade:
        # this is synchronous to allow an atomic transaction
        # https://code.djangoproject.com/ticket/33882

        assert self.confirmation_phase
        assert self.trader1.confirmed and self.trader2.confirmed
        trade_objects: list[TradeObject] = []
        balls: list[BallInstance] = []
        trade = Trade.objects.create(player1=self.trader1.player, player2=self.trader2.player)

        def money_check(trader: TradingUser) -> Player:
            player = Player.objects.select_for_update(nowait=True).get(id=trader.player.pk)
            if not player.can_afford(trader.money):
                raise IntegrityError()
            return player

        def queryset_for_update(trader: TradingUser):
            return trader.get_queryset().select_for_update(nowait=True, of=("self",)).only("player__discord_id")

        for countryball in queryset_for_update(self.trader1):
            if countryball.player.discord_id != self.trader1.player.discord_id:
                # This is a invalid mutation, the player is not the owner of the countryball
                raise IntegrityError()
            countryball.player = self.trader2.player
            countryball.trade_player = self.trader1.player
            countryball.favorite = False
            countryball.locked = None
            balls.append(countryball)
            trade_objects.append(TradeObject(trade=trade, ballinstance=countryball, player=self.trader1.player))

        for countryball in queryset_for_update(self.trader2):
            if countryball.player.discord_id != self.trader2.player.discord_id:
                # This is a invalid mutation, the player is not the owner of the countryball
                raise IntegrityError()
            countryball.player = self.trader1.player
            countryball.trade_player = self.trader2.player
            countryball.favorite = False
            countryball.locked = None
            balls.append(countryball)
            trade_objects.append(TradeObject(trade=trade, ballinstance=countryball, player=self.trader2.player))

        if self.trader1.money or self.trader2.money:
            player1 = money_check(self.trader1)
            player2 = money_check(self.trader2)
            player1.money += self.trader2.money - self.trader1.money
            player2.money += self.trader1.money - self.trader2.money
            player1.save(update_fields=("money",))
            player2.save(update_fields=("money",))

        BallInstance.objects.bulk_update(balls, fields=("player", "trade_player", "favorite", "locked"))
        TradeObject.objects.bulk_create(trade_objects)
        return trade

    async def finish_trade(self):
        if self.confirmation_lock.locked():
            raise SynchronizationError()
        await self.confirmation_lock.acquire()
        self.timeout_task.cancel()
        trade = await sync_to_async(self.perform_trade_operation)()
        self.stop()
        # edition of the message will be triggered by the caller
        self.add_item(TextDisplay(f"## The trade has been completed!\n-# ID: `#{trade.pk:0X}`"))

    async def _cleanup(self):
        self.stop()
        await BallInstance.objects.filter(id__in=self.trader1.proposal | self.trader2.proposal).aupdate(locked=None)

    async def cleanup(self):
        self.timeout_task.cancel()
        await self._cleanup()

    async def admin_cancel(self, reason: str):
        await self.cleanup()
        self.clear_items()
        self.add_item(
            TextDisplay(f"Trading has been globally disabled by administrators for the following reason: {reason}")
        )
        await self.message.edit(view=self)
