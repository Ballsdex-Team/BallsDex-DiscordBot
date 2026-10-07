# Events and hooks

BallsDex gives your package two ways to react to what happens in the bot, without modifying
its code:

- **[Events](#events)** are notifications. They are sent once an action has completed, run in the
  background, and cannot change anything. Use them for logging, statistics, quests, webhooks...
- **[Hooks](#hooks)** are awaited by the bot before an action happens. They run in order, and can
  block the action or modify its outcome. Use them for custom rules, anti-cheat, boosts...

| | Events | Hooks |
|---|---|---|
| Declared with | `@commands.Cog.listener()` | `@hook("name")` |
| Awaited by the bot | No | Yes, one after another |
| Can block the action | No | `pre_*` and `spawn_check` hooks |
| Can modify the outcome | No | `catch_roll` and `catch_message` hooks |
| Ordering | None | By `priority` |

There are no hooks running after an action: once it's done, use events. A slow listener will
never delay the bot.

Both examples below assume you already have a
[discord.py extension](custom-package.md#adding-a-discordpy-extension) with a cog.

## Events

Events are dispatched with discord.py's own event system, so you listen to them like any other
discord.py event: add `on_` in front of the event name.

| Listener | Payload | When |
|---|---|---|
| `on_ballsdex_ball_spawned` | [`BallSpawnedEvent`][ballsdex.core.events.BallSpawnedEvent] | A countryball spawned (natural spawn, admin spawn or drop) |
| `on_ballsdex_ball_caught` | [`BallCaughtEvent`][ballsdex.core.events.BallCaughtEvent] | A spawned countryball was caught |
| `on_ballsdex_trade_completed` | [`TradeCompletedEvent`][ballsdex.core.events.TradeCompletedEvent] | A trade was confirmed and saved |
| `on_ballsdex_ball_given` | [`BallGivenEvent`][ballsdex.core.events.BallGivenEvent] | Countryballs were given or a donation was accepted |
| `on_ballsdex_settings_change` | `guild, channel=None, enabled=None` | A server's spawn settings changed |

!!! note
    `ballsdex_settings_change` predates the other events and uses positional arguments instead
    of a payload object.

Payloads are read-only. An exception raised in a listener is logged and does not affect the bot.

### Announcing special catches

```py
from discord.ext import commands

from ballsdex.core.events import BallCaughtEvent

LOG_CHANNEL_ID = 1234567890


class Announcer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ballsdex_ball_caught(self, event: BallCaughtEvent):
        special = event.ball_instance.specialcard
        if special is None or event.dropped:
            return
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send(
                f"{event.user.mention} just caught a **{special.name}** "
                f"{event.ball_instance.countryball.country}!"
            )
```

!!! warning
    You are in an async context, so accessing a foreign key such as `ball_instance.special` or
    `ball_instance.ball` would raise `SynchronousOnlyOperation`. Use the cached properties
    `specialcard` and `countryball` instead, or fetch the related objects with an async query.

### Tracking trades

The trade payload does not contain the countryballs exchanged, query them from the trade entry:

```py
from discord.ext import commands

from ballsdex.core.events import TradeCompletedEvent
from bd_models.models import TradeObject


class TradeStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.traded = 0

    @commands.Cog.listener()
    async def on_ballsdex_trade_completed(self, event: TradeCompletedEvent):
        self.traded += await TradeObject.objects.filter(trade=event.trade).acount()
```

### Reacting to spawns

```py
from discord.ext import commands

from ballsdex.core.events import BallSpawnedEvent


class SpawnReactions(commands.Cog):
    @commands.Cog.listener()
    async def on_ballsdex_ball_spawned(self, event: BallSpawnedEvent):
        if event.ball.rarity < 0.1:
            await event.message.add_reaction("\N{EYES}")
```

## Hooks

A hook is an async function receiving a context object. Decorate a cog method with
[`hook`][ballsdex.core.hooks.hook], and it is registered when the cog is added to the bot, then
unregistered when the cog is removed (including on reload).

| Hook | Context | When | Can |
|---|---|---|---|
| `spawn_check` | [`SpawnCheckContext`][ballsdex.core.hooks.SpawnCheckContext] | Before a natural spawn | Cancel |
| `pre_catch` | [`PreCatchContext`][ballsdex.core.hooks.PreCatchContext] | After a correct guess, before catching | Cancel |
| `catch_roll` | [`CatchRollContext`][ballsdex.core.hooks.CatchRollContext] | Before a new countryball is created | Edit `special`, `attack_bonus`, `health_bonus` |
| `catch_message` | [`CatchMessageContext`][ballsdex.core.hooks.CatchMessageContext] | Before the catch message is sent | Edit `content` |
| `pre_trade` | [`PreTradeContext`][ballsdex.core.hooks.PreTradeContext] | Both users confirmed, before saving | Cancel |
| `pre_give` | [`PreGiveContext`][ballsdex.core.hooks.PreGiveContext] | Before a give or donation request | Cancel |

A few rules to keep in mind:

- Hooks run one after another, highest `priority` first (default `0`).
- Calling `ctx.cancel(reason)` blocks the action and skips the remaining hooks. The reason is
  shown to the user, a generic message is used if you omit it.
- A hook raising an exception, or taking longer than 3 seconds, is logged and skipped. The
  action continues as if the hook wasn't there.
- The user is waiting on your hook: keep it fast, and move slow work to an [event](#events) listener.

### Catch cooldown

```py
import time

from discord.ext import commands

from ballsdex.core.hooks import PreCatchContext, hook

COOLDOWN = 60


class CatchCooldown(commands.Cog):
    def __init__(self):
        self.last_catch: dict[int, float] = {}

    @hook("pre_catch")
    async def cooldown(self, ctx: PreCatchContext):
        now = time.monotonic()
        last = self.last_catch.get(ctx.player.discord_id, 0)
        if now - last < COOLDOWN:
            ctx.cancel(f"You can only catch once every {COOLDOWN} seconds.")
            return
        self.last_catch[ctx.player.discord_id] = now
```

### Quiet hours

```py
from datetime import datetime, timezone

from discord.ext import commands

from ballsdex.core.hooks import SpawnCheckContext, hook


class QuietHours(commands.Cog):
    @hook("spawn_check")
    async def no_night_spawns(self, ctx: SpawnCheckContext):
        if 2 <= datetime.now(timezone.utc).hour < 6:
            ctx.cancel()
```

### Weekend stat boost

```py
from datetime import datetime

from discord.ext import commands

from ballsdex.core.hooks import CatchRollContext, hook
from settings.models import settings


class WeekendBoost(commands.Cog):
    @hook("catch_roll")
    async def boost(self, ctx: CatchRollContext):
        if datetime.now().weekday() >= 5:
            ctx.attack_bonus = min(ctx.attack_bonus + 5, settings.max_attack_bonus)
            ctx.health_bonus = min(ctx.health_bonus + 5, settings.max_health_bonus)
```

### Extra catch message and reward

Players earn money for a new countryball, and the catch message tells them about it:

```py
from discord.ext import commands

from ballsdex.core.hooks import CatchMessageContext, hook
from settings.models import settings

REWARD = 50


class CatchRewards(commands.Cog):
    @hook("catch_message")
    async def reward(self, ctx: CatchMessageContext):
        if not ctx.is_new:
            return
        await ctx.player.add_money(REWARD)
        ctx.content += f"\nYou earned {REWARD} {settings.currency_name} for this new catch!"
```

### Blocking trades of fresh catches

```py
from datetime import timedelta

from django.utils import timezone
from discord.ext import commands

from ballsdex.core.hooks import PreTradeContext, hook
from bd_models.models import BallInstance


class TradeRules(commands.Cog):
    @hook("pre_trade")
    async def no_fresh_catches(self, ctx: PreTradeContext):
        ids = ctx.trader1.proposal | ctx.trader2.proposal
        recent = timezone.now() - timedelta(hours=1)
        if await BallInstance.objects.filter(id__in=ids, catch_date__gt=recent).aexists():
            ctx.cancel("Countryballs caught less than an hour ago cannot be traded.")
```

### Daily donation limit

Hooks and events pair well together: the `pre_give` hook blocks donations over the limit, while
a listener counts what was actually given.

```py
from collections import Counter

from discord.ext import commands, tasks

from ballsdex.core.events import BallGivenEvent
from ballsdex.core.hooks import PreGiveContext, hook

DAILY_LIMIT = 20


class DonationLimit(commands.Cog):
    def __init__(self):
        self.given: Counter[int] = Counter()
        self.reset.start()

    async def cog_unload(self):
        self.reset.cancel()

    @tasks.loop(hours=24)
    async def reset(self):
        self.given.clear()

    @hook("pre_give")
    async def check_limit(self, ctx: PreGiveContext):
        if self.given[ctx.sender.pk] >= DAILY_LIMIT:
            ctx.cancel(f"You can only give {DAILY_LIMIT} countryballs per day.")

    @commands.Cog.listener()
    async def on_ballsdex_ball_given(self, event: BallGivenEvent):
        self.given[event.sender.pk] += len(event.ball_instances)
```

### Registering without a cog

Hooks can also be registered manually on `bot.hooks`, a
[`HookRegistry`][ballsdex.core.hooks.HookRegistry]. In that case, you are responsible for
unregistering them.

```py
from ballsdex.core.hooks import SpawnCheckContext

BLOCKED_GUILDS = {1234567890}


async def block_guilds(ctx: SpawnCheckContext):
    if ctx.guild.id in BLOCKED_GUILDS:
        ctx.cancel()


async def setup(bot):
    bot.hooks.register("spawn_check", block_guilds, priority=5)


async def teardown(bot):
    bot.hooks.unregister("spawn_check", block_guilds)
```
