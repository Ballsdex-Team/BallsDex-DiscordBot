import discord
import logging

from rich import print

from discord import app_commands
from discord.ext import commands

from ballsdex.core.dev import Dev
from ballsdex.core.commands import Core

log = logging.getLogger("ballsdex.core.bot")

PACKAGES = ["config", "players", "countryballs", "info"]


class BallsDexBot(commands.Bot):
    """
    BallsDex Discord bot
    """

    def __init__(self, command_prefix: str, dev: bool = False, **options):
        intents = discord.Intents(guilds=True, guild_messages=True, message_content=True)
        super().__init__(command_prefix, intents=intents, **options)
        self._shutdown = 0
        self.dev = dev
        self.tree.error(self.on_application_command_error)

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
        assert context.command
        if isinstance(
            exception, (commands.CommandNotFound, commands.CheckFailure, commands.DisabledCommand)
        ):
            return

        if isinstance(exception, (commands.ConversionError, commands.UserInputError)):
            # in case we need to know what happened
            log.debug("Silenced command exception", exc_info=exception)
            await context.send_help()
            return

        if isinstance(exception, commands.MissingRequiredAttachment):
            await context.send("An attachment is missing.")
            return

        if isinstance(exception, commands.CommandInvokeError):

            if isinstance(exception.original, discord.Forbidden):
                await context.send("The bot does not have the permission to do something.")
                # log to know where permissions are lacking
                log.warning(
                    f"Missing permissions for text command {context.command.name}",
                    exc_info=exception.original,
                )
                return

            log.error(f"Error in text command {context.command.name}", exc_info=exception.original)
            await context.send(
                "An error occured when running the command. Contact support if this persists."
            )
            return

        await context.send(
            "An error occured when running the command. Contact support if this persists."
        )
        log.error(f"Unknown error in text command {context.command.name}", exc_info=exception)

    async def on_application_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        assert interaction.command

        async def send(content: str):
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)

        if isinstance(error, app_commands.CheckFailure):
            await send("You are not allowed to use that command.")
            return

        if isinstance(error, app_commands.CommandInvokeError):

            if isinstance(error.original, discord.Forbidden):
                await send("The bot does not have the permission to do something.")
                # log to know where permissions are lacking
                log.warning(
                    f"Missing permissions for app command {interaction.command.name}",
                    exc_info=error.original,
                )
                return

            log.error(f"Error in text command {interaction.command.name}", exc_info=error.original)
            await send(
                "An error occured when running the command. Contact support if this persists."
            )
            return

        await send("An error occured when running the command. Contact support if this persists.")
        log.error(f"Unknown error in text command {interaction.command.name}", exc_info=error)

    async def on_error(self, event_method: str, /, *args, **kwargs):
        formatted_args = ", ".join(args)
        formatted_kwargs = " ".join(f"{x}={y}" for x, y in kwargs.items())
        log.error(
            f"Error in event {event_method}. Args: {formatted_args}. Kwargs: {formatted_kwargs}",
            exc_info=True,
        )
