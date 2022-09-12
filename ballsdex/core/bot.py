import discord
import logging

from rich import print

from discord.ext import commands

from ballsdex.core.dev import Dev
from ballsdex.core.commands import Core

log = logging.getLogger("ballsdex.core.bot")

PACKAGES = ["config", "players", "countryballs"]


class BallsDexBot(commands.Bot):
    """
    BallsDex Discord bot
    """

    def __init__(self, command_prefix: str, dev: bool = False, **options):
        intents = discord.Intents(guilds=True, guild_messages=True, message_content=True)
        super().__init__(command_prefix, intents=intents, **options)
        self._shutdown = 0
        self.dev = dev

    async def on_shard_ready(self, shard_id: int):
        log.debug(f"Connected to shard #{shard_id}")

    async def on_ready(self):
        log.info(f"Successfully logged in as {self.user} ({self.user.id})!")
        log.info("Loading packages...")
        await self.add_cog(Core(self))
        if self.dev:
            await self.add_cog(Dev())
        loaded_packages = []
        for package in PACKAGES:
            try:
                await self.load_extension("ballsdex.packages." + package)
            except Exception:
                log.error(f"Failed to load package {package}", exc_info=True)
            else:
                loaded_packages.append(package)
        if loaded_packages:
            log.info(f"Packages loaded: {', '.join(loaded_packages)}")
        else:
            log.info("No package loaded.")
        synced_commands = await self.tree.sync()
        if synced_commands:
            log.info(f"Synced {len(synced_commands)} commands.")
        else:
            log.info("No command to sync.")
        print("\n    [bold][red]BallsDex bot[/red] [green]is now operational![/green][/bold]\n")

    async def on_command_error(
        self, context: commands.Context, exception: commands.errors.CommandError
    ):
        if isinstance(exception, commands.CommandNotFound):
            return
        log.error(f"Error in text command {context.command.name}", exc_info=exception)
