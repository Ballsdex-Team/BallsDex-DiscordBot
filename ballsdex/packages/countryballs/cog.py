import importlib
import logging
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands
from tortoise.exceptions import DoesNotExist

from ballsdex.core.models import GuildConfig
from ballsdex.packages.countryballs.countryball import BallSpawnView
from ballsdex.packages.countryballs.spawn import BaseSpawnManager
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.countryballs")


class CountryBallsSpawner(commands.Cog):
    spawn_manager: BaseSpawnManager

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.cache: dict[int, int] = {}
        self.countryball_cls = BallSpawnView

        module_path, class_name = settings.spawn_manager.rsplit(".", 1)
        module = importlib.import_module(module_path)
        # force a reload, otherwise cog reloads won't reflect to this class
        importlib.reload(module)
        spawn_manager = getattr(module, class_name)
        self.spawn_manager = spawn_manager(bot)

    async def load_cache(self):
        i = 0
        async for config in GuildConfig.filter(enabled=True, spawn_channel__isnull=False).only(
            "guild_id", "spawn_channel"
        ):
            self.cache[config.guild_id] = config.spawn_channel
            i += 1
        grammar = "" if i == 1 else "s"
        log.info(f"Loaded {i} guild{grammar} in cache.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id is not None:
            return
        guild = message.guild
        if not guild:
            return
        if guild.id not in self.cache:
            return
        if guild.id in self.bot.blacklist_guild:
            return

        result = await self.spawn_manager.handle_message(message)
        if result is False:
            return

        if isinstance(result, tuple):
            result, algo = result
        else:
            algo = settings.spawn_manager

        channel = guild.get_channel(self.cache[guild.id])
        if not channel:
            log.warning(f"Lost channel {self.cache[guild.id]} for guild {guild.name}.")
            del self.cache[guild.id]
            return
        ball = await BallSpawnView.get_random(self.bot)
        ball.algo = algo
        await ball.spawn(cast(discord.TextChannel, channel))

    @commands.Cog.listener()
    async def on_ballsdex_settings_change(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel | None = None,
        enabled: bool | None = None,
    ):
        if guild.id not in self.cache:
            if enabled is False:
                return  # do nothing
            if channel:
                self.cache[guild.id] = channel.id
            else:
                try:
                    config = await GuildConfig.get(guild_id=guild.id)
                except DoesNotExist:
                    return
                else:
                    self.cache[guild.id] = config.spawn_channel
        else:
            if enabled is False:
                del self.cache[guild.id]
            elif channel:
                self.cache[guild.id] = channel.id
