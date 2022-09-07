import discord
import random
import logging

from datetime import datetime
from dataclasses import dataclass, field

from ballsdex.packages.countryballs.countryball import CountryBall

log = logging.getLogger("ballsdex.packages.countryballs")

SPAWN_CHANCE_RANGE = (20, 120)


@dataclass
class SpawnCooldown:
    author: int
    time: float = field(default_factory=lambda: datetime.utcnow().timestamp())
    amount: int = field(default=1)
    chance: int = field(default_factory=lambda: random.randint(*SPAWN_CHANCE_RANGE))


@dataclass
class SpawnManager:
    cooldowns: dict[int, SpawnCooldown] = field(default_factory=dict)

    async def handle_message(self, message: discord.Message):
        guild = message.guild
        if not guild:
            return
        cooldown = self.cooldowns.get(guild.id, None)
        if not cooldown:
            cooldown = SpawnCooldown(message.author.id)
            self.cooldowns[guild.id] = cooldown
            log.debug(f"Created cooldown manager for guild {guild.id}")
        delta = datetime.utcnow().timestamp() - cooldown.time
        if cooldown.author == message.author.id:
            if delta < 10:
                log.debug(f"Handled message {message.id}, cooldown ignore")
                return
        chance = cooldown.chance - (delta // 30)
        cooldown.amount += 1
        if cooldown.amount <= chance:
            log.debug(f"Handled message {message.id}, count: {cooldown.amount}/{chance}")
            return
        # spawn countryball
        del self.cooldowns[guild.id]
        log.debug(f"Handled message {message.id}, spawning ball")
        await self.spawn_countryball(message.channel)

    async def spawn_countryball(self, channel: discord.abc.Messageable):
        ball = await CountryBall.get_random()
        await ball.spawn(channel)
