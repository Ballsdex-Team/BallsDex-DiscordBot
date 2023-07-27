from __future__ import annotations

import asyncio
import logging
import math
from typing import cast

import aiohttp
import discord
import discord.gateway
from cachetools import TTLCache
from discord import app_commands
from discord.ext import commands
from rich import print

from ballsdex.core.dev import Dev
from ballsdex.core.metrics import PrometheusServer
from ballsdex.core.models import (
    BlacklistedGuild,
    BlacklistedID,
    Special,
    Ball,
    Regime,
    Economy,
    balls,
    regimes,
    economies,
    specials,
)
from ballsdex.core.commands import Core
from ballsdex.settings import settings

log = logging.getLogger("ballsdex.core.bot")

PACKAGES = ["config", "players", "countryballs", "info", "admin", "trade"]


def owner_check(ctx: commands.Context[BallsDexBot]):
    return ctx.bot.is_owner(ctx.author)


class CommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        bot = cast(BallsDexBot, interaction.client)
        if not bot.is_ready():
            if interaction.type != discord.InteractionType.autocomplete:
                await interaction.response.send_message(
                    "The bot is currently starting, please wait for a few minutes... "
                    f"({round((len(bot.shards)/bot.shard_count)*100)}%)",
                    ephemeral=True,
                )
            return False  # wait for all shards to be connected
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
        intents = discord.Intents(
            guilds=True, guild_messages=True, emojis_and_stickers=True, message_content=True
        )

        super().__init__(command_prefix, intents=intents, tree_cls=CommandTree, **options)

        self.dev = dev
        self.prometheus_server: PrometheusServer | None = None

        self.tree.error(self.on_application_command_error)
        self.add_check(owner_check)  # Only owners are able to use text commands

        self._shutdown = 0
        self.blacklist: set[int] = set()
        self.blacklist_guild: set[int] = set()
        self.locked_balls = TTLCache(maxsize=99999, ttl=60 * 30)

    async def start_prometheus_server(self):
        self.prometheus_server = PrometheusServer(
            self, settings.prometheus_host, settings.prometheus_port
        )
        await self.prometheus_server.run()

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

    async def load_cache(self):
        balls.clear()
        for ball in await Ball.all():
            balls[ball.pk] = ball
        log.info(f"Loaded {len(balls)} balls")

        regimes.clear()
        for regime in await Regime.all():
            regimes[regime.pk] = regime
        log.info(f"Loaded {len(regimes)} regimes")

        economies.clear()
        for economy in await Economy.all():
            economies[economy.pk] = economy
        log.info(f"Loaded {len(economies)} economies")

        specials.clear()
        for special in await Special.all():
            specials[special.pk] = special
        log.info(f"Loaded {len(specials)} specials")

        self.blacklist = set()
        for blacklisted_id in await BlacklistedID.all().only("discord_id"):
            self.blacklist.add(blacklisted_id.discord_id)
        self.blacklist_guild = set()
        for blacklisted_id in await BlacklistedGuild.all().only("discord_id"):
            self.blacklist_guild.add(blacklisted_id.discord_id)

    async def gateway_healthy(self) -> bool:
        """Check whether or not the gateway proxy is ready and healthy."""
        if settings.gateway_url is None:
            raise RuntimeError("This is only available on the production bot instance.")

        try:
            base_url = str(discord.gateway.DiscordWebSocket.DEFAULT_GATEWAY).replace(
                "ws://", "http://"
            )
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/health", timeout=10) as resp:
                    return resp.status == 200
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
            return False

    async def setup_hook(self) -> None:
        log.info("Starting up with %s shards...", self.shard_count)
        if settings.gateway_url is None:
            return

        while True:
            response = await self.gateway_healthy()
            if response is True:
                log.info("Gateway proxy is ready!")
                break

            log.warning("Gateway proxy is not ready yet, waiting 30 more seconds...")
            await asyncio.sleep(30)

    async def on_ready(self):
        assert self.user
        log.info(f"Successfully logged in as {self.user} ({self.user.id})!")

        # set bot owners
        assert self.application
        if self.application.team:
            if settings.team_owners:
                self.owner_ids.update(m.id for m in self.application.team.members)
            else:
                self.owner_ids.add(self.application.team.owner_id)
        else:
            self.owner_ids.add(self.application.owner.id)
        if settings.co_owners:
            self.owner_ids.update(settings.co_owners)
        log.info(
            f"{self.owner_ids} {'are' if len(self.owner_ids) > 1 else 'is'} set as the bot owner."
        )

        await self.load_cache()
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

        if "admin" in PACKAGES:
            for guild_id in settings.admin_guild_ids:
                guild = self.get_guild(guild_id)
                if not guild:
                    continue
                synced_commands = await self.tree.sync(guild=guild)
                log.info(f"Synced {len(synced_commands)} admin commands for guild {guild.id}.")

        if settings.prometheus_enabled:
            try:
                await self.start_prometheus_server()
            except Exception:
                log.exception("Failed to start Prometheus server, stats will be unavailable.")

        print(
            f"\n    [bold][red]{settings.bot_name} bot[/red] [green]"
            "is now operational![/green][/bold]\n"
        )

    async def blacklist_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in self.blacklist:
            await interaction.response.send_message(
                "You are blacklisted from the bot."
                "\nYou can appeal this blacklist in our support server: {}".format(
                    settings.discord_invite
                ),
                ephemeral=True,
            )
            return False
        if interaction.guild_id and interaction.guild_id in self.blacklist_guild:
            await interaction.response.send_message(
                "This server is blacklisted from the bot."
                "\nYou can appeal this blacklist in our support server: {}".format(
                    settings.discord_invite
                ),
                ephemeral=True,
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
            await context.send_help(context.command)
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
        async def send(content: str):
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)

        if isinstance(error, app_commands.CheckFailure):
            if isinstance(error, app_commands.CommandOnCooldown):
                await send(
                    "This command is on cooldown. Please retry "
                    f"in {math.ceil(error.retry_after)} seconds."
                )
                return
            await send("You are not allowed to use that command.")
            return

        if isinstance(error, app_commands.CommandInvokeError):
            assert interaction.command

            if isinstance(error.original, discord.Forbidden):
                await send("The bot does not have the permission to do something.")
                # log to know where permissions are lacking
                log.warning(
                    f"Missing permissions for app command {interaction.command.name}",
                    exc_info=error.original,
                )
                return

            if isinstance(error.original, discord.InteractionResponded):
                # most likely an interaction received twice (happens sometimes),
                # or two instances are running on the same token.
                log.warning(
                    f"Tried invoking command {interaction.command.name}, but the "
                    "interaction was already responded to.",
                    exc_info=error.original,
                )
                # still including traceback because it may be a programming error

            log.error(
                f"Error in slash command {interaction.command.name}", exc_info=error.original
            )
            await send(
                "An error occured when running the command. Contact support if this persists."
            )
            return

        await send("An error occured when running the command. Contact support if this persists.")
        log.error("Unknown error in interaction", exc_info=error)

    async def on_error(self, event_method: str, /, *args, **kwargs):
        formatted_args = ", ".join(args)
        formatted_kwargs = " ".join(f"{x}={y}" for x, y in kwargs.items())
        log.error(
            f"Error in event {event_method}. Args: {formatted_args}. Kwargs: {formatted_kwargs}",
            exc_info=True,
        )
        self.tree.interaction_check
