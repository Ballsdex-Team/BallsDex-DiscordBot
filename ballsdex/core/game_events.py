"""
The game event bus: what players do, dispatched once and delivered to every system that rewards them for it.

Code doing something a player can be rewarded for dispatches an event:

    from ballsdex.core.game_events import Event, EventContext, bus

    await bus.dispatch(player, Event.AUCTION_WON, context=EventContext(price=amount), channel_id=channel_id)

Systems listening (the achievement engine, the event pass engine) subscribe when their package is loaded:

    bus.subscribe("achievements", engine.handle_event)

Nobody dispatching an event knows who listens to it. A package that isn't installed never subscribes: its events
are simply dropped, the code dispatching them doesn't change and nothing breaks. A subscriber raising an exception
is logged and never prevents the others from receiving the event.

Events are only delivered inside the bot process: actions made from the admin panel or a management command reward
nobody, exactly like before.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from cachetools import TTLCache

from ballsdex.core.utils.background import run_on_bot_loop

if TYPE_CHECKING:
    import discord
    from discord import app_commands

    from bd_models.models import BallInstance, Player

__all__ = ("ACTIVITY_EVENTS", "Event", "EventContext", "bus", "normalize_command")

log = logging.getLogger("ballsdex.core.game_events")


# key under which a command leaves its outcome on the interaction, read when the event is built
COMMAND_WORKED = "ballsdex_command_worked"


def command_did_nothing(interaction) -> None:
    """
    Mark a command as having had no effect: a daily still on cooldown, a shop with nothing left, a purchase
    the player could not afford.

    Quests can then ask to count only the commands that did something, instead of rewarding the player for
    running a command that told them to come back tomorrow.
    """
    interaction.extras[COMMAND_WORKED] = False


def command_worked(interaction) -> None:
    """
    Mark a command as having done what it promised. Only needed where the same command can also do nothing.
    """
    interaction.extras[COMMAND_WORKED] = True


def normalize_command(name: str) -> str:
    """
    "/Treasures  List" and "treasures list" are the same command.
    """
    return " ".join(name.lstrip("/").lower().split())


class Event(StrEnum):
    # -- treasures
    CATCH = "catch"  # a player caught a spawned treasure
    OBTAIN = "obtain"  # a player got treasures in any other way (trade, pack, claim, giveaway...)
    FAVORITE = "favorite"  # a player set a favorite treasure

    # -- players
    TRADE = "trade"  # a trade was completed
    GIFT = "gift"  # a player gave treasures away with the give command
    FRIEND = "friend"  # a player became friends with someone
    BATTLE_WIN = "battle_win"  # a player won a battle
    COMMAND = "command"  # a player used a slash command

    # -- berries
    CURRENCY_RECEIVED = "currency_received"  # a player received berries from someone, a player or an admin
    CURRENCY_SENT = "currency_sent"  # a player gave berries to someone
    CATCH_REWARD = "catch_reward"  # a player earned berries by catching a spawn
    ECONOMY = "economy"  # any berry movement, carrying its ledger reason: the catch-all of berry based goals
    CURRENCY_STREAK = "currency_streak"  # a player claimed their daily berries, carrying the streak they are on

    # -- shops and crafting
    PACK_BUY = "pack_buy"  # a player bought a pack
    PACK_STREAK = "pack_streak"  # a player claimed their daily pack, carrying the streak they are on
    MERCHANT_BUY = "merchant_buy"  # a player bought an item from the merchant
    SHOP_BUY = "shop_buy"  # a player bought a treasure from Buggy's shop
    SELL = "sell"  # a player sold a treasure to Buggy
    CRAFT = "craft"  # a player claimed a collector card (a craft, an elemental...)

    # -- auction house
    AUCTION_CREATE = "auction_create"  # a player listed a treasure
    AUCTION_BID = "auction_bid"  # a player placed a bid that went through
    AUCTION_WON = "auction_won"  # a player won a listing they bid on

    # -- meta
    ACTIVITY = "activity"  # a player did something, for goals that only need to know they are still playing
    SYNC = "sync"  # a player asked to refresh their progress, every goal based on a state is checked


# Everything meaning "this player is playing right now". ECONOMY is left out on purpose: it is dispatched for
# every single berry movement, including the ones already covered by a more precise event.
ACTIVITY_EVENTS = frozenset(Event) - {Event.ECONOMY}


@dataclass
class EventContext:
    """
    What happened, in as much detail as the dispatching code can give. Every field is optional: a listener reading
    a field that an event never fills simply never matches.
    """

    # treasures caught or obtained, the treasures received in a trade, the treasures given, bought, sold or crafted
    instances: list[BallInstance] = field(default_factory=list)
    # trades, gifts, friendships: the other player, or the admin giving berries
    partner_discord_id: int | None = None
    received_currency: int = 0
    # trades only: what the player gave in exchange
    given_count: int = 0
    given_currency: int = 0
    # commands only, like "treasures list"
    command_name: str = ""
    # whether the command actually did something: False for a /daily on cooldown, a sold out shop, a buy the
    # player could not afford. None when the command never said, which is most of them.
    command_worked: bool | None = None
    # streaks: how many days in a row the player has claimed, as it stands after this claim
    streak: int = 0
    # berries moved by the action and, for ECONOMY, the BerryTransaction reason behind it. Signed like the ledger:
    # negative when the player paid, positive when they were credited.
    amount: int = 0
    reason: str = ""
    # price paid or received, for purchases, sales, bids and auctions
    price: int = 0
    # the pack (currency_app.Item) or the merchant item bought
    item_id: int | None = None
    merchant_item_id: int | None = None
    # crafting: the collector claimed and the tier level it belongs to ("Craft", "Elemental", "Tier 1"...)
    collector_id: int | None = None
    tier_level_id: int | None = None
    # where the action happened, for goals limited to the main server
    server_id: int | None = None


Handler = Callable[[int, Event, "EventContext", "int | None"], Awaitable[object]]
CommandInterest = Callable[[str], Awaitable[bool]]


class GameEventBus:
    """
    Fans every event out to the systems listening to it. Subscribers are named, so a package registering its
    listener again (a reload) never ends up subscribed twice.
    """

    SIGNAL_UID = "game_event_bus"
    # how long a player stays known as "playing" before their next command counts as activity again
    ACTIVITY_TTL = 60 * 60

    def __init__(self):
        self._subscribers: dict[str, Handler] = {}
        self._command_interests: dict[str, CommandInterest] = {}
        self._recent_activity: TTLCache[int, bool] = TTLCache(maxsize=100_000, ttl=self.ACTIVITY_TTL)
        self._signal_connected = False

    @property
    def subscribers(self) -> tuple[str, ...]:
        return tuple(self._subscribers)

    def subscribe(self, name: str, handler: Handler, *, listens_to_command: CommandInterest | None = None):
        """
        Register a listener, replacing the one registered under the same name. The first subscriber also starts
        listening to treasure ownership changes, which is what turns catches and gifts into events.

        Parameters
        ----------
        listens_to_command: CommandInterest | None
            Asked whether a slash command is worth an event before one is dispatched. Commands are used constantly,
            so a subscriber only gets `Event.COMMAND` for the ones it answers `True` for.
        """
        self._subscribers[name] = handler
        if listens_to_command is not None:
            self._command_interests[name] = listens_to_command
        self._connect_ownership_signal()
        log.debug("Subscribed %s to the game event bus", name)

    def unsubscribe(self, name: str):
        self._command_interests.pop(name, None)
        if self._subscribers.pop(name, None) is None:
            return
        log.debug("Unsubscribed %s from the game event bus", name)
        if not self._subscribers:
            self._disconnect_ownership_signal()

    async def dispatch(
        self, player: Player | int, event: Event, *, context: EventContext | None = None, channel_id: int | None = None
    ):
        """
        Deliver an event to every subscriber, at the same time.

        Parameters
        ----------
        player: Player | int
            The player (or their primary key) who did something.
        event: Event
            What the player did.
        context: EventContext | None
            The details of the action.
        channel_id: int | None
            Where it happened, so the player can be told there.
        """
        if not self._subscribers:
            return
        player_id = player if isinstance(player, int) else player.pk
        context = context or EventContext()
        names = tuple(self._subscribers)
        results = await asyncio.gather(
            *(self._subscribers[name](player_id, event, context, channel_id) for name in names), return_exceptions=True
        )
        for name, result in zip(names, results, strict=True):
            if isinstance(result, BaseException):
                log.error("%s failed to handle %s of player %s", name, event, player_id, exc_info=result)

    def dispatch_soon(
        self, player: Player | int, event: Event, *, context: EventContext | None = None, channel_id: int | None = None
    ):
        """
        Thread-safe version of `dispatch` that doesn't wait for the result, usable from synchronous code such as a
        Django signal receiver. Nothing is scheduled outside of the bot process.
        """
        if not self._subscribers:
            return
        player_id = player if isinstance(player, int) else player.pk
        run_on_bot_loop(lambda: self.dispatch(player_id, event, context=context, channel_id=channel_id))

    # -- slash commands --------------------------------------------------------------------------------------------

    async def on_command_completed(
        self, interaction: discord.Interaction, command: app_commands.Command | app_commands.ContextMenu
    ):
        """
        Turn a completed slash command into an event, called by the bot for every command.

        Commands are used constantly, so `Event.COMMAND` is only dispatched for the commands a subscriber asked
        about. Everything else becomes `Event.ACTIVITY`, at most once an hour per player, which is enough for goals
        that only need to know the player is still around.
        """
        if not self._subscribers:
            return
        from bd_models.models import Player

        name = normalize_command(command.qualified_name)
        listened = await self._listened_command(name)
        if not listened and interaction.user.id in self._recent_activity:
            return
        self._recent_activity[interaction.user.id] = True
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        if player is None:
            return
        context = EventContext(
            command_name=name, server_id=interaction.guild_id, command_worked=interaction.extras.get(COMMAND_WORKED)
        )
        event = Event.COMMAND if listened else Event.ACTIVITY
        await self.dispatch(player, event, context=context, channel_id=interaction.channel_id)

    async def _listened_command(self, name: str) -> bool:
        for subscriber, interest in tuple(self._command_interests.items()):
            try:
                if await interest(name):
                    return True
            except Exception:
                log.exception("%s failed to tell whether it listens to the command %s", subscriber, name)
        return False

    # -- treasure ownership ------------------------------------------------------------------------------------------

    def _connect_ownership_signal(self):
        if self._signal_connected:
            return
        from bd_models.signals import ownership_changed

        ownership_changed.connect(self._on_ownership_changed, dispatch_uid=self.SIGNAL_UID)
        self._signal_connected = True

    def _disconnect_ownership_signal(self):
        if not self._signal_connected:
            return
        from bd_models.signals import ownership_changed

        ownership_changed.disconnect(dispatch_uid=self.SIGNAL_UID)
        self._signal_connected = False

    def _on_ownership_changed(
        self, sender, gained: dict[int, list[BallInstance]], created: set[int] | None = None, **kwargs
    ):
        """
        Receiver of `bd_models.signals.ownership_changed`: catches and treasures obtained in any other way.
        """
        created = created or set()
        for player_id, instances in gained.items():
            # the countryball spawn sets this attribute on the treasures it creates
            caught = [x for x in instances if x.pk in created and getattr(x, "_catch_channel_id", None)]
            obtained = [x for x in instances if x not in caught]
            if caught:
                channel_id = getattr(caught[0], "_catch_channel_id")
                self.dispatch_soon(
                    player_id, Event.CATCH, context=EventContext(instances=caught), channel_id=channel_id
                )
            if obtained:
                # a treasure given by someone else carries the channel of the gift, to congratulate the
                # recipient where it happened instead of where they last played
                channel_id = next(
                    (channel for x in obtained if (channel := getattr(x, "_notify_channel_id", None))), None
                )
                self.dispatch_soon(
                    player_id, Event.OBTAIN, context=EventContext(instances=obtained), channel_id=channel_id
                )


bus = GameEventBus()
