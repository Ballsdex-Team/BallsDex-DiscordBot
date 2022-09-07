import discord
import logging

from typing import Mapping
from discord.ext import commands

from ballsdex.core.models import GuildConfig
from ballsdex.packages.countryballs.spawn import SpawnManager

log = logging.getLogger("ballsdex.packages.countryballs")


class CountryBallsSpawner(commands.Cog):
    def __init__(self):
        self.cache: Mapping[int, int] = {}
        self.spawn_manager = SpawnManager()
    
    async def load_cache(self):
        i = 0
        async for config in GuildConfig.all():
            if not config.enabled:
                continue
            if not config.spawn_channel:
                continue
            self.cache[config.guild_id] = config.spawn_channel
            i += 1
        log.info(f"Loaded {i} guilds in cache")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        guild = message.guild
        if guild.id not in self.cache:
            return
        if self.cache[guild.id] != message.channel.id:
            return
        await self.spawn_manager.handle_message(message)
