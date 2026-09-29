from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, ClassVar, TypeVar

import discord

from ballsdex.core import tracing

if TYPE_CHECKING:
    from discord.ext import commands

    from ballsdex.packages.countryballs.countryball import BallSpawnView
    from ballsdex.packages.trade.trade import TradeInstance, TradingUser
    from bd_models.models import BallInstance, Player, Special, Trade

__all__ = (
    "HOOK_TIMEOUT",
    "HookContext",
    "CancellableContext",
    "SpawnCheckContext",
    "PostSpawnContext",
    "PreCatchContext",
    "CatchRollContext",
    "PostCatchContext",
    "PreTradeContext",
    "PostTradeContext",
    "PreGiveContext",
    "PostGiveContext",
    "HookRegistry",
    "hook",
)

log = logging.getLogger("ballsdex.core.hooks")

# maximum time in seconds a single hook function may take before being skipped
HOOK_TIMEOUT = 3.0

C = TypeVar("C", bound="HookContext")
HookFunc = Callable[[C], Awaitable[Any]]


class HookContext:
    """
    Base class for all hook contexts.

    Attributes
    ----------
    hook_name: ClassVar[str]
        The name of the hook receiving this context.
    """

    hook_name: ClassVar[str]


@dataclass(kw_only=True)
class CancellableContext(HookContext):
    """
    A context that can be cancelled to block the action. Once cancelled, the remaining hooks
    are not called.

    Attributes
    ----------
    cancelled: bool
        Whether a hook cancelled the action.
    reason: str | None
        The user-facing reason given when cancelling, if any.
    """

    cancelled: bool = field(default=False, init=False)
    reason: str | None = field(default=None, init=False)

    def cancel(self, reason: str | None = None):
        """
        Block the action.

        Parameters
        ----------
        reason: str | None
            A message shown to the user. A generic message is shown if omitted.
        """
        self.cancelled = True
        self.reason = reason


@dataclass(kw_only=True)
class SpawnCheckContext(CancellableContext):
    """
    A countryball is about to spawn naturally. Cancelling silently skips this spawn.

    Attributes
    ----------
    guild: discord.Guild
        The guild where the spawn happens.
    channel: discord.TextChannel
        The configured spawn channel.
    message: discord.Message
        The message that triggered the spawn.
    algo: str
        The spawn algorithm that decided to spawn.
    """

    hook_name = "spawn_check"

    guild: discord.Guild
    channel: discord.TextChannel
    message: discord.Message
    algo: str


@dataclass(kw_only=True)
class PostSpawnContext(HookContext):
    """
    A countryball was spawned in a channel. This includes natural spawns, admin spawns and drops.

    Attributes
    ----------
    view: BallSpawnView
        The view attached to the spawn message.
    channel: discord.TextChannel
        The channel the countryball was spawned in.
    """

    hook_name = "post_spawn"

    view: BallSpawnView
    channel: discord.TextChannel


@dataclass(kw_only=True)
class PreCatchContext(CancellableContext):
    """
    A user guessed the name of a countryball correctly and is about to catch it. Cancelling
    prevents the catch, the countryball stays available to others.

    Attributes
    ----------
    view: BallSpawnView
        The view of the spawn being caught.
    interaction: discord.Interaction
        The interaction of the catch prompt, already deferred.
    player: Player
        The player trying to catch.
    guess: str
        The name typed by the user.
    """

    hook_name = "pre_catch"

    view: BallSpawnView
    interaction: discord.Interaction
    player: Player
    guess: str


@dataclass(kw_only=True)
class CatchRollContext(HookContext):
    """
    A new countryball instance is about to be created after a catch. The rolled values can be
    modified. Not called when catching a dropped countryball, since it already exists.

    Attributes
    ----------
    view: BallSpawnView
        The view of the spawn being caught.
    user: discord.User | discord.Member
        The user catching.
    player: Player
        The player catching.
    special: Special | None
        The special event applied. Editable.
    attack_bonus: int
        The attack bonus in percent. Editable.
    health_bonus: int
        The health bonus in percent. Editable.
    """

    hook_name = "catch_roll"

    view: BallSpawnView
    user: discord.User | discord.Member
    player: Player
    special: Special | None
    attack_bonus: int
    health_bonus: int


@dataclass(kw_only=True)
class PostCatchContext(HookContext):
    """
    A countryball was caught, and the catch message is about to be sent.

    Attributes
    ----------
    view: BallSpawnView
        The view of the spawn that was caught.
    interaction: discord.Interaction
        The interaction of the catch prompt.
    player: Player
        The player who caught.
    ball_instance: BallInstance
        The countryball now owned by the player.
    is_new: bool
        Whether this is the first time the player owns this countryball.
    content: str
        The catch message that will be sent. Editable.
    """

    hook_name = "post_catch"

    view: BallSpawnView
    interaction: discord.Interaction
    player: Player
    ball_instance: BallInstance
    is_new: bool
    content: str


@dataclass(kw_only=True)
class PreTradeContext(CancellableContext):
    """
    Both users confirmed a trade and it is about to be saved. Cancelling ends the trade without
    exchanging anything, and the reason is shown on the trade message.

    Attributes
    ----------
    trade: TradeInstance
        The trade view.
    trader1: TradingUser
        The user who started the trade.
    trader2: TradingUser
        The other user of the trade.
    """

    hook_name = "pre_trade"

    trade: TradeInstance
    trader1: TradingUser
    trader2: TradingUser


@dataclass(kw_only=True)
class PostTradeContext(HookContext):
    """
    A trade was saved. The countryballs exchanged can be fetched with
    `TradeObject.objects.filter(trade=ctx.trade)`.

    Attributes
    ----------
    view: TradeInstance
        The trade view.
    trade: Trade
        The trade entry saved.
    trader1: TradingUser
        The user who started the trade.
    trader2: TradingUser
        The other user of the trade.
    """

    hook_name = "post_trade"

    view: TradeInstance
    trade: Trade
    trader1: TradingUser
    trader2: TradingUser


@dataclass(kw_only=True)
class PreGiveContext(CancellableContext):
    """
    A player is about to give countryballs to another, or send them a donation request.
    Cancelling blocks the donation, and the reason is shown to the sender.

    Attributes
    ----------
    sender: Player
        The player giving.
    recipient: Player
        The player receiving.
    """

    hook_name = "pre_give"

    sender: Player
    recipient: Player


@dataclass(kw_only=True)
class PostGiveContext(HookContext):
    """
    Countryballs were given from a player to another.

    Attributes
    ----------
    sender: Player
        The player who gave.
    recipient: Player
        The player who received.
    ball_instances: list[BallInstance]
        The countryballs given.
    trade: Trade
        The trade entry registered for this donation.
    """

    hook_name = "post_give"

    sender: Player
    recipient: Player
    ball_instances: list[BallInstance]
    trade: Trade


HOOK_NAMES: frozenset[str] = frozenset(
    cls.hook_name
    for cls in (
        SpawnCheckContext,
        PostSpawnContext,
        PreCatchContext,
        CatchRollContext,
        PostCatchContext,
        PreTradeContext,
        PostTradeContext,
        PreGiveContext,
        PostGiveContext,
    )
)


@dataclass(frozen=True, slots=True)
class _RegisteredHook:
    func: HookFunc
    priority: int
    owner: object | None


def hook(name: str, *, priority: int = 0):
    """
    Mark a cog method as a hook. It is registered when the cog is added to the bot.

    Parameters
    ----------
    name: str
        The name of the hook.
    priority: int
        Hooks with a higher priority run first. Defaults to 0.
    """
    if name not in HOOK_NAMES:
        raise ValueError(f"Unknown hook {name!r}")

    def decorator(func):
        func.__ballsdex_hook__ = (name, priority)
        return func

    return decorator


class HookRegistry:
    """
    Holds all registered hooks. Available as `bot.hooks`.
    """

    def __init__(self):
        self._hooks: defaultdict[str, list[_RegisteredHook]] = defaultdict(list)

    def register(self, name: str, func: HookFunc, *, priority: int = 0, owner: object | None = None):
        """
        Register a hook function.

        Parameters
        ----------
        name: str
            The name of the hook.
        func: Callable[[HookContext], Awaitable[Any]]
            The async function to call with the context.
        priority: int
            Hooks with a higher priority run first. Defaults to 0.
        owner: object | None
            The object owning this hook, used to unregister all its hooks at once.
        """
        if name not in HOOK_NAMES:
            raise ValueError(f"Unknown hook {name!r}")
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Hook functions must be coroutines")
        hooks = self._hooks[name]
        hooks.append(_RegisteredHook(func, priority, owner))
        hooks.sort(key=lambda h: h.priority, reverse=True)

    def unregister(self, name: str, func: HookFunc):
        """
        Unregister a hook function. Does nothing if it wasn't registered.
        """
        self._hooks[name] = [h for h in self._hooks[name] if h.func != func]

    def unregister_owner(self, owner: object):
        """
        Unregister all hook functions registered with this owner.
        """
        for name, hooks in self._hooks.items():
            self._hooks[name] = [h for h in hooks if h.owner is not owner]

    def add_cog(self, cog: commands.Cog):
        """
        Register all methods of a cog decorated with [`hook`][ballsdex.core.hooks.hook].
        """
        seen: set[str] = set()
        for base in type(cog).__mro__:
            for attr, value in base.__dict__.items():
                if attr in seen:
                    continue
                seen.add(attr)
                if marker := getattr(value, "__ballsdex_hook__", None):
                    name, priority = marker
                    self.register(name, getattr(cog, attr), priority=priority, owner=cog)

    def remove_cog(self, cog: commands.Cog):
        """
        Unregister all hooks of a cog.
        """
        self.unregister_owner(cog)

    def has(self, name: str) -> bool:
        """
        Whether any function is registered for this hook.
        """
        return bool(self._hooks.get(name))

    async def run(self, ctx: C) -> C:
        """
        Run all functions registered for the hook of this context, and return the context.

        Parameters
        ----------
        ctx: HookContext
            The context passed to each hook function.
        """
        hooks = self._hooks.get(ctx.hook_name)
        if not hooks:
            return ctx
        with tracing.span("hooks.run", resource=ctx.hook_name):
            for registered in list(hooks):
                try:
                    await asyncio.wait_for(registered.func(ctx), timeout=HOOK_TIMEOUT)
                except asyncio.TimeoutError:
                    log.warning(f"Hook {registered.func!r} for {ctx.hook_name} timed out, skipping.")
                except Exception:
                    log.exception(f"Hook {registered.func!r} for {ctx.hook_name} raised an error, skipping.")
                if isinstance(ctx, CancellableContext) and ctx.cancelled:
                    tracing.set_tag("hooks.cancelled", True)
                    break
        return ctx
