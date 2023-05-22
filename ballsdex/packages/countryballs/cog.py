import discord
import logging

from typing import Optional
from tortoise.exceptions import DoesNotExist
from discord.ext import commands

from ballsdex.core.models import GuildConfig
from ballsdex.packages.countryballs.spawn import SpawnManager

log = logging.getLogger("ballsdex.packages.countryballs")


class CountryBallsSpawner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.spawn_manager = SpawnManager()
        self.bot: commands.Bot = bot

    async def load_cache(self):
        i = 0
        async for config in GuildConfig.all():
            if not config.enabled:
                continue
            if not config.spawn_channel:
                continue
            self.spawn_manager.cache[config.guild_id] = config.spawn_channel
            i += 1
        log.info(f"Loaded {i} guilds in cache")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        guild = message.guild
        if not guild:
            return
        if guild.id not in self.spawn_manager.cache:
            return
        if guild.id in self.bot.blacklist_guild:
            return
        await self.spawn_manager.handle_message(message)

    @commands.Cog.listener()
    async def on_ballsdex_settings_change(
        self,
        guild: discord.Guild,
        channel: Optional[discord.TextChannel] = None,
        enabled: Optional[bool] = None,
    ):
        if guild.id not in self.spawn_manager.cache:
            if enabled is False:
                return  # do nothing
            if channel:
                self.spawn_manager.cache[guild.id] = channel.id
            else:
                try:
                    config = await GuildConfig.get(guild_id=guild.id)
                except DoesNotExist:
                    return
                else:
                    self.spawn_manager.cache[guild.id] = config.spawn_channel
        else:
            if enabled is False:
                del self.spawn_manager.cache[guild.id]
            elif channel:
                self.spawn_manager.cache[guild.id] = channel.id
