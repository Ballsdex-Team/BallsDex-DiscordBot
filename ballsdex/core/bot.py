from __future__ import annotations

import asyncio
import inspect
import logging
import math
import time
import types
from datetime import datetime
from typing import TYPE_CHECKING, Self, Sequence

import aiohttp
import discord
import discord.gateway
from aiohttp import ClientTimeout
from cachetools import TTLCache
from discord import app_commands
from discord.app_commands.translator import TranslationContextLocation, TranslationContextTypes, locale_str
from discord.enums import Locale
from discord.ext import commands
from discord.utils import MISSING
from django.apps import apps
from prometheus_client import Histogram
from rich import box, print
from rich.console import Console
from rich.table import Table

from ballsdex.core.commands import Core
from ballsdex.core.dev import Dev
from ballsdex.core.help import HelpCommand
from ballsdex.core.metrics import PrometheusServer
from ballsdex.core.utils.checks import check_perms
from bd_models.models import (
    Ball,
    BlacklistedGuild,
    BlacklistedID,
    Economy,
    Regime,
    Special,
    balls,
    economies,
    regimes,
    specials,
)
from settings.models import settings

if TYPE_CHECKING:
    from discord.ext.commands.bot import PrefixType

log = logging.getLogger("ballsdex.core.bot")
http_counter = Histogram("discord_http_requests", "HTTP requests", ["key", "code"])
impersonations: dict[int, discord.Member] = {}

DEFAULT_PACKAGES = (
    ("admin", "ballsdex.packages.admin"),
    ("balls", "ballsdex.packages.balls"),
    ("guildconfig", "ballsdex.packages.guildconfig"),
    ("countryballs", "ballsdex.packages.countryballs"),
    ("info", "ballsdex.packages.info"),
    ("players", "ballsdex.packages.players"),
    ("trade", "ballsdex.packages.trade"),
)


def owner_check(ctx: commands.Context[BallsDexBot]):
    return ctx.bot.is_owner(ctx.author)


class Translator(app_commands.Translator):
    async def translate(self, string: locale_str, locale: Locale, context: TranslationContextTypes) -> str | None:
        text = (
            string.message.replace("countryballs", settings.plural_collectible_name)
            .replace("countryball", settings.collectible_name)
            .replace("/balls", f"/{settings.balls_slash_name}")
            .replace("BallsDex", settings.bot_name)
        )
        if context.location in (TranslationContextLocation.command_name, TranslationContextLocation.group_name):
            text = text.replace(" ", "-").lower()

        return text


# observing the duration and status code of HTTP requests through aiohttp TraceConfig
async def on_request_start(
    session: aiohttp.ClientSession, trace_ctx: types.SimpleNamespace, params: aiohttp.TraceRequestStartParams
):
    # register t1 before sending request
    trace_ctx.start = session.loop.time()


async def on_request_end(
    session: aiohttp.ClientSession, trace_ctx: types.SimpleNamespace, params: aiohttp.TraceRequestEndParams
):
    time = session.loop.time() - trace_ctx.start

    # to categorize HTTP calls per path, we need to access the corresponding discord.http.Route
    # object, which is not available in the context of an aiohttp TraceConfig, therefore it's
    # obtained by accessing the locals() from the calling function HTTPConfig.request
    # "params.url.path" is not usable as it contains raw IDs and tokens, breaking categories
    frame = inspect.currentframe()
    _locals = frame.f_back.f_back.f_back.f_back.f_back.f_locals  # type: ignore
    if route := _locals.get("route"):
        route_key = route.key
    else:
        # calling function is HTTPConfig.static_login which has no Route object
        route_key = f"{params.response.method} {params.url.path}"

    http_counter.labels(route_key, params.response.status).observe(time)


class CommandTree[Bot: BallsDexBot](app_commands.CommandTree[Bot]):
    disable_time_check: bool = False

    async def interaction_check(self, interaction: discord.Interaction[Bot], /) -> bool:
        # checking if the moment we receive this interaction isn't too late already
        # there is a 3 seconds limit for initial response, taking a little margin into account
        # https://discord.com/developers/docs/interactions/receiving-and-responding#responding-to-an-interaction
        if not self.disable_time_check:
            delta = datetime.now(tz=interaction.created_at.tzinfo) - interaction.created_at
            if delta.total_seconds() >= 2.8:
                log.warning(f"Skipping interaction {interaction.id}, running {delta.total_seconds()}s late.")
                return False

        bot = interaction.client
        if not bot.is_ready():
            if interaction.type != discord.InteractionType.autocomplete:
                try:
                    await interaction.response.send_message(
                        "The bot is currently starting, please wait for a few minutes... "
                        f"({round((len(bot.shards) / bot.shard_count) * 100)}%)",
                        ephemeral=True,
                    )
                except discord.NotFound:
                    pass
            return False  # wait for all shards to be connected

        if impersonated := impersonations.get(interaction.user.id, None):
            interaction.user = impersonated
            interaction._permissions = impersonated._permissions or 0
        return await bot.blacklist_check(interaction)

    async def load_command_mentions(
        self, app_commands: list[app_commands.AppCommand] | None = None, *, cog: commands.Cog | None = None
    ):
        if app_commands is None:
            cmds = {x.name: x.id for x in await self.fetch_commands()}
        else:
            cmds = {x.name: x.id for x in app_commands}

        for cmd in (cog or self).walk_commands():
            cmd_id = cmds.get(cmd.root_parent.name if cmd.root_parent else cmd.name, None)
            if not cmd_id:
                continue
            cmd.extras["mention"] = f"</{cmd.qualified_name}:{cmd_id}>"

    async def sync(self, *, guild: discord.abc.Snowflake | None = None) -> list[app_commands.AppCommand]:
        app_commands = await super().sync(guild=guild)
        if not guild:
            # assign the mentions
            await self.load_command_mentions(app_commands)
            return app_commands

        return app_commands


class BallsDexBot(commands.AutoShardedBot):
    """
    BallsDex Discord bot
    """

    def __init__(
        self,
        command_prefix: PrefixType[BallsDexBot],
        disable_message_content: bool = False,
        disable_time_check: bool = False,
        skip_tree_sync: bool = False,
        gateway_url: str | None = None,
        dev: bool = False,
        **options,
    ):
        # An explaination for the used intents
        # guilds: needed for basically anything, the bot needs to know what guilds it has
        # and accordingly enable automatic spawning in the enabled ones
        # guild_messages: spawning is based on messages sent, content is not necessary
        # emojis_and_stickers: DB holds emoji IDs for the balls which are fetched from 3 servers
        intents = discord.Intents(
            guilds=True, guild_messages=True, emojis_and_stickers=True, message_content=not disable_message_content
        )
        if disable_message_content:
            log.warning("Message content disabled, this will make spam detection harder")

        if settings.prometheus_enabled:
            trace = aiohttp.TraceConfig()
            trace.on_request_start.append(on_request_start)
            trace.on_request_end.append(on_request_end)
            options["http_trace"] = trace

        super().__init__(
            command_prefix, intents=intents, tree_cls=CommandTree, help_command=HelpCommand(width=100), **options
        )
        self.tree: CommandTree[Self]
        self.tree.disable_time_check = disable_time_check
        self.skip_tree_sync = skip_tree_sync
        self.gateway_url = gateway_url

        self.dev = dev
        self.prometheus_server: PrometheusServer | None = None

        self.tree.error(self.on_application_command_error)

        self._shutdown = 0
        self.startup_time: datetime | None = None
        self.application_emojis: dict[int, discord.Emoji] = {}
        self.blacklist: set[int] = set()
        self.blacklist_guild: set[int] = set()
        self.catch_log: set[int] = set()
        self.command_log: set[int] = set()
        self.locked_balls = TTLCache(maxsize=99999, ttl=60 * 30)

        self.owner_ids: set[int]

    async def start_prometheus_server(self):
        self.prometheus_server = PrometheusServer(self, settings.prometheus_host, settings.prometheus_port)
        await self.prometheus_server.run()

    def get_emoji(self, id: int) -> discord.Emoji | None:
        return self.application_emojis.get(id) or super().get_emoji(id)

    async def load_cache(self):
        table = Table(box=box.SIMPLE)
        table.add_column("Model", style="cyan")
        table.add_column("Count", justify="right", style="green")

        self.application_emojis.clear()
        for emoji in await self.fetch_application_emojis():
            self.application_emojis[emoji.id] = emoji

        balls.clear()
        async for ball in Ball.objects.all():
            balls[ball.pk] = ball
        table.add_row(settings.collectible_name.title() + "s", str(len(balls)))

        regimes.clear()
        async for regime in Regime.objects.all():
            regimes[regime.pk] = regime
        table.add_row("Regimes", str(len(regimes)))

        economies.clear()
        async for economy in Economy.objects.all():
            economies[economy.pk] = economy
        table.add_row("Economies", str(len(economies)))

        specials.clear()
        async for special in Special.objects.all():
            specials[special.pk] = special
        table.add_row("Special events", str(len(specials)))

        self.blacklist = set()
        async for blacklisted_id in BlacklistedID.objects.all().only("discord_id"):
            self.blacklist.add(blacklisted_id.discord_id)
        table.add_row("Blacklisted users", str(len(self.blacklist)))

        self.blacklist_guild = set()
        async for blacklisted_id in BlacklistedGuild.objects.all().only("discord_id"):
            self.blacklist_guild.add(blacklisted_id.discord_id)
        table.add_row("Blacklisted guilds", str(len(self.blacklist_guild)))

        log.info("Cache loaded, summary displayed below:")
        console = Console()
        console.print(table)

    async def gateway_healthy(self) -> bool:
        """Check whether or not the gateway proxy is ready and healthy."""
        if self.gateway_url is None:
            raise RuntimeError("This is only available on the production bot instance.")

        try:
            base_url = str(discord.gateway.DiscordWebSocket.DEFAULT_GATEWAY).replace("ws://", "http://")
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/health", timeout=ClientTimeout(total=10)) as resp:
                    return resp.status == 200
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
            return False

    async def setup_hook(self) -> None:
        await self.tree.set_translator(Translator())
        log.info("Starting up with %s shards...", self.shard_count)
        if self.gateway_url is None:
            return

        while True:
            response = await self.gateway_healthy()
            if response is True:
                log.info("Gateway proxy is ready!")
                break

            log.warning("Gateway proxy is not ready yet, waiting 30 more seconds...")
            await asyncio.sleep(30)

    # override cog reload to reconfigure app command mentions
    async def add_cog(
        self,
        cog: commands.Cog,
        /,
        *,
        override: bool = False,
        guild: discord.abc.Snowflake | None = MISSING,
        guilds: Sequence[discord.abc.Snowflake] = MISSING,
    ) -> None:
        # hook that will check before loading a cog that Django permission checks are valid
        await check_perms()
        await super().add_cog(cog, override=override, guild=guild, guilds=guilds)
        if self.is_ready():
            await self.tree.load_command_mentions(cog=cog)
        # otherwise, bot is still starting, that will be done with the sync

    async def on_ready(self):
        if self.cogs != {}:
            return  # bot is reconnecting, no need to setup again

        if self.startup_time is None:
            self.startup_time = datetime.now()

        assert self.user
        log.info(f"Successfully logged in as {self.user} ({self.user.id})!")

        # set bot owners
        assert self.application
        if self.application.team:
            if settings.team_owners:
                self.owner_ids.update(m.id for m in self.application.team.members)
            else:
                self.owner_ids.add(self.application.team.owner_id)  # type: ignore
        else:
            self.owner_ids.add(self.application.owner.id)
        if settings.co_owners:
            self.owner_ids.update(settings.co_owners)
        if len(self.owner_ids) > 1:
            log.info(f"{len(self.owner_ids)} users are set as bot owner.")
        else:
            log.info(f"{await self.fetch_user(next(iter(self.owner_ids)))} is the owner of this bot.")

        await self.load_cache()
        grammar = "" if len(self.blacklist) == 1 else "s"
        if self.blacklist:
            log.info(f"{len(self.blacklist)} blacklisted user{grammar}.")

        log.info("Loading packages...")
        await self.add_cog(Core(self))
        if self.dev:
            await self.add_cog(Dev())

        loaded_packages = []
        packages = list(DEFAULT_PACKAGES)
        for app in apps.get_app_configs():
            if dpy_package := getattr(app, "dpy_package", None):
                packages.append((app.label, dpy_package))

        for package_name, path in packages:
            try:
                await self.load_extension(path)
            except Exception:
                log.error(f"Failed to load package {package_name}", exc_info=True)
            else:
                loaded_packages.append(package_name)
        if loaded_packages:
            log.info(f"Packages loaded: {', '.join(loaded_packages)}")
        else:
            log.info("No package loaded.")

        if not self.skip_tree_sync:
            log.info("Syncing global commands...")
            synced_commands = await self.tree.sync()
            log.info(f"Synced {len(synced_commands)} global commands.")
        else:
            log.warning("Skipping command synchronization.")

        if settings.prometheus_enabled:
            try:
                await self.start_prometheus_server()
            except Exception:
                log.exception("Failed to start Prometheus server, stats will be unavailable.")

        print(f"\n    [bold][red]{settings.bot_name} bot[/red] [green]is now operational![/green][/bold]\n")

    async def blacklist_check(self, source: discord.Interaction[Self] | commands.Context[Self]) -> bool:
        if isinstance(source, discord.Interaction):
            user = source.user
            guild_id = source.guild_id
            if source.type != discord.InteractionType.autocomplete:
                send_func = source.response.send_message
            else:
                # empty awaitable function
                send_func = lambda *ar, **kw: asyncio.sleep(0)  # noqa: E731
        else:
            user = source.author
            guild_id = source.guild.id if source.guild else None
            send_func = source.send
        if user.id in self.blacklist:
            await send_func(
                "You are blacklisted from the bot.\nYou can appeal this blacklist in our support server: {}".format(
                    settings.discord_invite
                ),
                ephemeral=True,
            )
            return False
        if guild_id and guild_id in self.blacklist_guild:
            await send_func(
                "This server is blacklisted from the bot."
                "\nYou can appeal this blacklist in our support server: {}".format(settings.discord_invite),
                ephemeral=True,
            )
            return False
        if source.command and user.id in self.command_log:
            log.info(f'{user} ({user.id}) used "{source.command.qualified_name}" in {source.guild} ({guild_id})')
        return True

    async def on_command_error(
        self, context: commands.Context, exception: commands.errors.CommandError | app_commands.AppCommandError
    ):
        if isinstance(exception, (commands.CommandNotFound, commands.DisabledCommand)):
            return

        assert context.command
        match exception:
            case commands.BadArgument():
                await context.send(exception.args[0])

            case commands.ConversionError() | commands.UserInputError():
                # in case we need to know what happened
                log.debug("Silenced command exception", exc_info=exception)
                await context.send_help(context.command)

            case commands.MissingRequiredAttachment():
                await context.send("An attachment is missing.", ephemeral=True)

            case app_commands.CommandOnCooldown() | commands.CommandOnCooldown():
                await context.send(
                    "This command is on cooldown. Please retry "
                    f"<t:{math.ceil(time.time() + exception.retry_after)}:R>.",
                    ephemeral=True,
                )

            case app_commands.TransformerError():
                await context.send("One of the arguments provided cannot be parsed.", ephemeral=True)
                log.debug("Failed running converter", exc_info=exception)

            case commands.CheckFailure() | app_commands.CheckFailure():
                match exception:
                    case commands.BotMissingPermissions() | app_commands.BotMissingPermissions():
                        missing_perms = ", ".join(exception.missing_permissions)
                        await context.send(
                            f"The bot is missing the permissions: `{missing_perms}`."
                            " Give the bot those permissions for the command to work as expected.",
                            ephemeral=True,
                        )

                    case commands.MissingPermissions() | app_commands.MissingPermissions():
                        missing_perms = ", ".join(exception.missing_permissions)
                        await context.send(
                            f"You are missing the following permissions: `{missing_perms}`."
                            " You need those permissions to run this command.",
                            ephemeral=True,
                        )

                    case _:
                        await context.send("You are not allowed to use this command.", ephemeral=True)

            case app_commands.CommandInvokeError() | commands.CommandInvokeError():
                match exception.original:
                    case discord.Forbidden():
                        await context.send("The bot does not have the permission to do something.", ephemeral=True)
                        # log to know where permissions are lacking
                        log.warning(
                            f"Missing permissions for command {context.command.qualified_name}",
                            exc_info=exception.original,
                        )

                    case discord.InteractionResponded():
                        # most likely an interaction received twice (happens sometimes),
                        # or two instances are running on the same token.
                        log.warning(
                            f"Tried invoking command {context.command.qualified_name}, but the "
                            "interaction was already responded to.",
                            exc_info=exception.original,
                        )

                    case discord.NotFound(code=10062) | discord.NotFound(code=10015):
                        log.warning("Expired interaction", exc_info=exception.original)

                    case _:
                        # still including traceback because it may be a programming error
                        await context.send(
                            "An error occured when running the command. Contact support if this persists.",
                            ephemeral=True,
                        )
                        log.error(
                            f"Unknown error in {'slash' if context.interaction else 'text'} command "
                            f"{context.command.qualified_name}",
                            exc_info=exception.original,
                        )

            case _:
                await context.send("An unknown error occured, contact support if this persists.")
                log.error("Unknown exception", exc_info=exception)

    async def on_application_command_error(
        self, interaction: discord.Interaction[Self], error: app_commands.AppCommandError
    ):
        if isinstance(error, (app_commands.CommandNotFound, app_commands.CommandSignatureMismatch)):
            if not self.is_ready():
                log.warning("Command not found, but the bot hasn't started yet.")
                return
            if interaction.type == discord.InteractionType.autocomplete:
                return
            send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
            try:
                await send("Commands desynchronized, contact support to fix this.")
            except discord.NotFound:
                pass
            log.error(error.args[0])
            return

        await self.on_command_error(await commands.Context.from_interaction(interaction), error)

    async def on_error(self, event_method: str, /, *args, **kwargs):
        formatted_args = ", ".join((repr(x) for x in args))
        formatted_kwargs = " ".join(f"{x}={y:r}" for x, y in kwargs.items())
        log.error(f"Error in event {event_method}. Args: {formatted_args}. Kwargs: {formatted_kwargs}", exc_info=True)
