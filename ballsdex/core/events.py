from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import discord

if TYPE_CHECKING:
    from ballsdex.packages.countryballs.countryball import BallSpawnView
    from ballsdex.packages.trade.trade import TradingUser
    from bd_models.models import Ball, BallInstance, Player, Trade

__all__ = ("BallsDexEvent", "BallSpawnedEvent", "BallCaughtEvent", "TradeCompletedEvent", "BallGivenEvent", "dispatch")


class BallsDexEvent:
    """
    Base class for all event payloads.

    Attributes
    ----------
    event_name: ClassVar[str]
        The name passed to `bot.dispatch`. Listen to it with `on_<event_name>`.
    """

    event_name: ClassVar[str]


@dataclass(frozen=True, slots=True)
class BallSpawnedEvent(BallsDexEvent):
    """
    A countryball was spawned in a channel. This includes natural spawns, admin spawns and dropped
    countryballs.

    Listener: `on_ballsdex_ball_spawned(event)`

    Attributes
    ----------
    view: BallSpawnView
        The view attached to the spawn message.
    channel: discord.TextChannel
        The channel the countryball was spawned in.
    """

    event_name = "ballsdex_ball_spawned"

    view: BallSpawnView
    channel: discord.TextChannel

    @property
    def ball(self) -> Ball:
        """
        The countryball that spawned.
        """
        return self.view.model

    @property
    def message(self) -> discord.Message:
        """
        The spawn message.
        """
        return self.view.message

    @property
    def dropped(self) -> bool:
        """
        Whether this is an existing countryball dropped by a player rather than a new spawn.
        """
        return self.view.ballinstance is not None


@dataclass(frozen=True, slots=True)
class BallCaughtEvent(BallsDexEvent):
    """
    A spawned countryball was caught.

    Listener: `on_ballsdex_ball_caught(event)`

    Attributes
    ----------
    view: BallSpawnView
        The view of the spawn that was caught.
    user: discord.User | discord.Member
        The user who caught the countryball.
    player: Player
        The player who caught the countryball.
    guild: discord.Guild | None
        The guild the countryball was caught in.
    ball_instance: BallInstance
        The countryball now owned by the player. This is a new instance, unless `dropped` is set.
    is_new: bool
        Whether this is the first time the player owns this countryball.
    """

    event_name = "ballsdex_ball_caught"

    view: BallSpawnView
    user: discord.User | discord.Member
    player: Player
    guild: discord.Guild | None
    ball_instance: BallInstance
    is_new: bool

    @property
    def dropped(self) -> bool:
        """
        Whether this was an existing countryball dropped by a player. The ownership was transferred
        to the catcher, unless the owner caught it back.
        """
        return self.view.ballinstance is not None


@dataclass(frozen=True, slots=True)
class TradeCompletedEvent(BallsDexEvent):
    """
    A trade between two players was confirmed and saved.

    The countryballs exchanged can be fetched with `TradeObject.objects.filter(trade=event.trade)`.

    Listener: `on_ballsdex_trade_completed(event)`

    Attributes
    ----------
    trade: Trade
        The trade entry that was saved.
    trader1: TradingUser
        The user who started the trade.
    trader2: TradingUser
        The other user of the trade.
    """

    event_name = "ballsdex_trade_completed"

    trade: Trade
    trader1: TradingUser
    trader2: TradingUser


@dataclass(frozen=True, slots=True)
class BallGivenEvent(BallsDexEvent):
    """
    One or more countryballs were given by a player to another, with `/balls give`, `/balls bulk_give` or
    an accepted donation request.

    Listener: `on_ballsdex_ball_given(event)`

    Attributes
    ----------
    sender: Player
        The player who gave the countryballs.
    recipient: Player
        The player who received the countryballs.
    ball_instances: list[BallInstance]
        The countryballs given.
    trade: Trade
        The trade entry registered for this donation.
    """

    event_name = "ballsdex_ball_given"

    sender: Player
    recipient: Player
    ball_instances: list[BallInstance]
    trade: Trade


def dispatch(bot: discord.Client, event: BallsDexEvent):
    """
    Dispatch an event to all listeners.

    Parameters
    ----------
    bot: discord.Client
        The bot instance.
    event: BallsDexEvent
        The event payload to send.
    """
    bot.dispatch(event.event_name, event)
