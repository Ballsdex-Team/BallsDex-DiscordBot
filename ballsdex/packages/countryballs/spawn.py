import asyncio
import logging
import random
from collections import deque, namedtuple
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

import discord

from ballsdex.packages.countryballs.countryball import CountryBall

log = logging.getLogger("ballsdex.packages.countryballs")

SPAWN_CHANCE_RANGE = (40, 55)

CachedMessage = namedtuple("CachedMessage", ["content", "author_id"])


@dataclass
class SpawnCooldown:
    """
    Represents the spawn internal system per guild. Contains the counters that will determine
    if a countryball should be spawned next or not.

    Attributes
    ----------
    time: datetime
        Time when the object was initialized. Block spawning when it's been less than two minutes
    amount: float
        A number starting at 0, incrementing with the messages until reaching `chance`. At this
        point, a ball will be spawned next.
    chance: int
        The number `amount` has to reach for spawn. Determined randomly with `SPAWN_CHANCE_RANGE`
    lock: asyncio.Lock
        Used to ratelimit messages and ignore fast spam
    message_cache: ~collections.deque[CachedMessage]
        A list of recent messages used to reduce the spawn chance when too few different chatters
        are present. Limited to the 100 most recent messages in the guild.
    """

    time: datetime
    # initialize partially started, to reduce the dead time after starting the bot
    amount: float = field(default=SPAWN_CHANCE_RANGE[0] // 2)
    chance: int = field(default_factory=lambda: random.randint(*SPAWN_CHANCE_RANGE))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    message_cache: deque[CachedMessage] = field(default_factory=lambda: deque(maxlen=100))

    def reset(self, time: datetime):
        self.amount = 1.0
        self.chance = random.randint(*SPAWN_CHANCE_RANGE)
        try:
            self.lock.release()
        except RuntimeError:  # lock is not acquired
            pass
        self.time = time

    async def increase(self, message: discord.Message) -> bool:
        # this is a deque, not a list
        # its property is that, once the max length is reached (100 for us),
        # the oldest element is removed, thus we only have the last 100 messages in memory
        self.message_cache.append(
            CachedMessage(content=message.content, author_id=message.author.id)
        )

        if self.lock.locked():
            return False

        async with self.lock:
            amount = 1
            if message.guild.member_count < 5 or message.guild.member_count > 1000:  # type: ignore
                amount /= 2
            if message._state.intents.message_content and len(message.content) < 5:
                amount /= 2
            if len(set(x.author_id for x in self.message_cache)) < 4 or (
                len(list(filter(lambda x: x.author_id == message.author.id, self.message_cache)))
                / self.message_cache.maxlen  # type: ignore
                > 0.4
            ):
                amount /= 2
            self.amount += amount
            await asyncio.sleep(10)
        return True


@dataclass
class SpawnManager:
    cooldowns: dict[int, SpawnCooldown] = field(default_factory=dict)
    cache: dict[int, int] = field(default_factory=dict)

    async def handle_message(self, message: discord.Message):
        guild = message.guild
        if not guild:
            return

        cooldown = self.cooldowns.get(guild.id, None)
        if not cooldown:
            cooldown = SpawnCooldown(message.created_at)
            self.cooldowns[guild.id] = cooldown

        delta = (message.created_at - cooldown.time).total_seconds()
        # change how the threshold varies according to the member count, while nuking farm servers
        if not guild.member_count:
            return
        elif guild.member_count < 5:
            multiplier = 0.1
        elif guild.member_count < 100:
            multiplier = 0.8
        elif guild.member_count < 1000:
            multiplier = 0.5
        else:
            multiplier = 0.2
        chance = cooldown.chance - multiplier * (delta // 60)

        # manager cannot be increased more than once per 5 seconds
        if not await cooldown.increase(message):
            return

        # normal increase, need to reach goal
        if cooldown.amount <= chance:
            return

        # at this point, the goal is reached
        if delta < 600:
            # wait for at least 10 minutes before spawning
            return

        # spawn countryball
        cooldown.reset(message.created_at)
        await self.spawn_countryball(guild)

    async def spawn_countryball(self, guild: discord.Guild):
        channel = guild.get_channel(self.cache[guild.id])
        if not channel:
            log.warning(f"Lost channel {self.cache[guild.id]} for guild {guild.name}.")
            del self.cache[guild.id]
            return
        ball = await CountryBall.get_random()
        await ball.spawn(cast(discord.TextChannel, channel))
