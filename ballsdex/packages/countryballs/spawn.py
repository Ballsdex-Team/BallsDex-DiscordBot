import discord
import random
import logging
import asyncio

from typing import cast
from datetime import datetime
from dataclasses import dataclass, field

from ballsdex.packages.countryballs.countryball import CountryBall

log = logging.getLogger("ballsdex.packages.countryballs")

SPAWN_CHANCE_RANGE = (65, 100)


@dataclass
class SpawnCooldown:
    time: datetime
    amount: int = field(default=1)
    chance: int = field(default_factory=lambda: random.randint(*SPAWN_CHANCE_RANGE))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def increase(self) -> bool:
        if self.lock.locked():
            return False
        async with self.lock:
            self.amount += 1
            await asyncio.sleep(4)
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
            log.debug(f"Created cooldown manager for guild {guild.id}")

        delta = (message.created_at - cooldown.time).total_seconds()
        chance = cooldown.chance - (delta // 60)

        # manager cannot be increased more than once per 5 seconds
        if not await cooldown.increase():
            log.debug(f"Handled message {message.id}, skipping due to spam control")
            return

        # normal increase, need to reach goal
        if cooldown.amount <= chance:
            log.debug(f"Handled message {message.id}, count: {cooldown.amount}/{chance}")
            return

        # at this point, the goal is reached
        if delta < 120:
            # wait for at least 2 minutes before spawning
            log.debug(f"Handled message {message.id}, waiting for manager to be 2 mins old")
            return

        # spawn countryball
        del self.cooldowns[guild.id]
        log.debug(f"Handled message {message.id}, spawning ball")
        await self.spawn_countryball(guild)

    async def spawn_countryball(self, guild: discord.Guild):
        channel = guild.get_channel(self.cache[guild.id])
        if not channel:
            log.warning(f"Lost channel {self.cache[guild.id]} for guild {guild.name}.")
            del self.cache[guild.id]
            return
        ball = await CountryBall.get_random()
        await ball.spawn(cast(discord.TextChannel, channel))
