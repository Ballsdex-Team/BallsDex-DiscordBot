from __future__ import annotations

import discord
import logging

from rich import print
from typing import cast
from datetime import datetime

from discord import app_commands
from discord.ext import commands

from ballsdex.core.dev import Dev
from ballsdex.core.models import BlacklistedID, Special
from ballsdex.core.commands import Core

log = logging.getLogger("ballsdex.core.bot")

PACKAGES = ["config", "players", "countryballs", "info"]


class CommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        bot = cast(BallsDexBot, interaction.client)
        return await bot.blacklist_check(interaction)


class BallsDexBot(commands.AutoShardedBot):
    """
    BallsDex Discord bot
    """

    def __init__(self, command_prefix: str, dev: bool = False, **options):
        # An explaination for the used intents
        # guilds: needed for basically anything, the bot needs to know what guilds it has
        # and accordingly enable automatic spawning in the enabled ones
        # guild_messages: spawning is based on messages sent, content is not necessary
        # emojis_and_stickers: DB holds emoji IDs for the balls which are fetched from 3 servers
        intents = discord.Intents(guilds=True, guild_messages=True, emojis_and_stickers=True)

        super().__init__(command_prefix, intents=intents, tree_cls=CommandTree, **options)
        self._shutdown = 0
        self.dev = dev
        self.tree.error(self.on_application_command_error)
        self.blacklist: list[int] = []
        self.special_cache: list[Special] = []

    async def on_shard_ready(self, shard_id: int):
        log.debug(f"Connected to shard #{shard_id}")

    def assign_ids_to_app_groups(
        self, group: app_commands.Group, synced_commands: list[app_commands.AppCommandGroup]
    ):
        for synced_command in synced_commands:
            bot_command = group.get_command(synced_command.name)
            if not bot_command:
                continue
            bot_command.extras["mention"] = synced_command.mention
            if isinstance(bot_command, app_commands.Group) and bot_command.commands:
                self.assign_ids_to_app_groups(
                    bot_command, cast(list[app_commands.AppCommandGroup], synced_command.options)
                )

    def assign_ids_to_app_commands(self, synced_commands: list[app_commands.AppCommand]):
        for synced_command in synced_commands:
            bot_command = self.tree.get_command(synced_command.name, type=synced_command.type)
            if not bot_command:
                continue
            bot_command.extras["mention"] = synced_command.mention
            if isinstance(bot_command, app_commands.Group) and bot_command.commands:
                self.assign_ids_to_app_groups(
                    bot_command, cast(list[app_commands.AppCommandGroup], synced_command.options)
                )

    async def load_blacklist(self):
        self.blacklist = (
            await BlacklistedID.all().only("discord_id").values_list("discord_id", flat=True)
        )  # type: ignore

    async def load_special_cache(self):
        now = datetime.now()
        self.special_cache = await Special.filter(start_date__lte=now, end_date__gt=now)

    async def on_ready(self):
        assert self.user
        log.info(f"Successfully logged in as {self.user} ({self.user.id})!")

        await self.load_blacklist()
        await self.load_special_cache()
        if self.blacklist:
            log.info(f"{len(self.blacklist)} blacklisted users.")

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
            try:
                self.assign_ids_to_app_commands(synced_commands)
            except Exception:
                log.error("Failed to assign IDs to app commands", exc_info=True)
        else:
            log.info("No command to sync.")
        print("\n    [bold][red]BallsDex bot[/red] [green]is now operational![/green][/bold]\n")

    async def blacklist_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in self.blacklist:
            await interaction.response.send_message(
                "You are blacklisted from the bot.", ephemeral=True
            )
            return False
        return True

    async def on_command_error(
        self, context: commands.Context, exception: commands.errors.CommandError
    ):
        if isinstance(
            exception, (commands.CommandNotFound, commands.CheckFailure, commands.DisabledCommand)
        ):
            return

        assert context.command
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
        self.tree.interaction_check
