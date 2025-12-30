import asyncio
import functools
import logging
import logging.handlers
import os
import sys
from signal import SIGTERM
from typing import TypedDict, Unpack, cast

import discord
import sentry_sdk
import yarl
from discord.ext.commands import when_mentioned_or
from django.core.management.base import BaseCommand, CommandError, CommandParser
from rich import print
from sentry_sdk.integrations.asyncio import AsyncioIntegration

from ballsdex import __version__ as bot_version
from ballsdex.core.bot import BallsDexBot
from settings.models import load_settings, settings

discord.voice_client.VoiceClient.warn_nacl = False  # disable PyNACL warning
log = logging.getLogger("ballsdex")


class CLIFlags(TypedDict):
    disable_rich: bool
    gateway_url: str | None
    shard_count: int | None
    shard_ids: list[int] | None
    cluster_name: str | None
    cluster_id: int | None
    cluster_count: int | None
    disable_message_content: bool
    disable_time_check: bool
    skip_tree_sync: bool
    debug: bool
    dev: bool


def print_welcome():
    print("[green]{0:-^50}[/green]".format(f" {settings.bot_name} bot "))
    print("[green]{0: ^50}[/green]".format(f" Collect {settings.plural_collectible_name} "))
    print("[blue]{0:^50}[/blue]".format("Discord bot made by El Laggron"))
    print("")
    print(" [red]{0:<20}[/red] [yellow]{1:>10}[/yellow]".format("Bot version:", bot_version))
    print(" [red]{0:<20}[/red] [yellow]{1:>10}[/yellow]".format("Discord.py version:", discord.__version__))
    print("")


def patch_gateway(proxy_url: str):
    """This monkeypatches discord.py in order to be able to use a custom gateway URL.

    Parameters
    ----------
    proxy_url : str
        The URL of the gateway proxy to use.
    """
    import zlib

    class ProductionHTTPClient(discord.http.HTTPClient):  # type: ignore
        async def get_gateway(self, **_):
            return f"{proxy_url}?encoding=json&v=10"

        async def get_bot_gateway(self, **_):
            try:
                data = await self.request(
                    discord.http.Route("GET", "/gateway/bot")  # type: ignore
                )
            except discord.HTTPException as exc:
                raise discord.GatewayNotFound() from exc
            return data["shards"], f"{proxy_url}?encoding=json&v=10"

    class ProductionDiscordWebSocket(discord.gateway.DiscordWebSocket):  # type: ignore
        def is_ratelimited(self):
            return False

        async def debug_send(self, data, /):
            self._dispatch("socket_raw_send", data)
            await self.socket.send_str(data)

        async def send(self, data, /):
            await self.socket.send_str(data)

    class _ZlibDecompressionContext:
        __slots__ = ("context", "buffer")

        COMPRESSION_TYPE: str = "zlib-stream"

        def __init__(self) -> None:
            self.buffer: bytearray = bytearray()
            self.context = zlib.decompressobj()

        def decompress(self, data: bytes, /) -> str | None:
            self.buffer.extend(data)

            # Check whether ending is Z_SYNC_FLUSH
            if len(data) < 4 or data[-4:] != b"\x00\x00\xff\xff":
                return

            msg = self.context.decompress(self.buffer)
            self.buffer = bytearray()

            return msg.decode("utf-8")

    class ProductionReconnectWebSocket(Exception):
        def __init__(self, shard_id: int | None, *, resume: bool = False):
            self.shard_id: int | None = shard_id
            self.resume: bool = False
            self.op: str = "IDENTIFY"

    def is_ws_ratelimited(self):
        return False

    async def before_identify_hook(self, shard_id: int | None, *, initial: bool = False):
        pass

    discord.http.HTTPClient.get_gateway = ProductionHTTPClient.get_gateway  # type: ignore
    discord.http.HTTPClient.get_bot_gateway = ProductionHTTPClient.get_bot_gateway  # type: ignore
    discord.gateway.DiscordWebSocket._keep_alive = None  # type: ignore
    discord.gateway.DiscordWebSocket.is_ratelimited = (  # type: ignore
        ProductionDiscordWebSocket.is_ratelimited
    )
    discord.gateway.DiscordWebSocket.debug_send = (  # type: ignore
        ProductionDiscordWebSocket.debug_send
    )
    discord.gateway.DiscordWebSocket.send = ProductionDiscordWebSocket.send  # type: ignore
    discord.gateway.DiscordWebSocket.DEFAULT_GATEWAY = yarl.URL(proxy_url)  # type: ignore
    discord.gateway.ReconnectWebSocket.__init__ = (  # type: ignore
        ProductionReconnectWebSocket.__init__
    )
    discord.utils._ActiveDecompressionContext = _ZlibDecompressionContext
    BallsDexBot.is_ws_ratelimited = is_ws_ratelimited
    BallsDexBot.before_identify_hook = before_identify_hook


async def shutdown_handler(bot: BallsDexBot, signal_type: str | None = None):
    if signal_type:
        log.info(f"Received {signal_type}, stopping the bot...")
    else:
        log.info("Shutting down the bot...")
    try:
        await asyncio.wait_for(bot.close(), timeout=10)
    finally:
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in pending]
        try:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=5)
        except asyncio.TimeoutError:
            log.error(
                f"Timed out cancelling tasks. {len([t for t in pending if not t.cancelled])}/"
                f"{len(pending)} tasks are still pending!"
            )
        sys.exit(0 if signal_type else 1)


def global_exception_handler(bot: BallsDexBot, loop: asyncio.AbstractEventLoop, context: dict):
    """
    Logs unhandled exceptions in other tasks
    """
    exc = context.get("exception")
    # These will get handled later when it *also* kills loop.run_forever
    if exc is not None and isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return
    log.critical(
        "Caught unhandled exception in %s:\n%s", context.get("future", "event loop"), context["message"], exc_info=exc
    )


def bot_exception_handler(bot: BallsDexBot, bot_task: asyncio.Future):
    """
    This is set as a done callback for the bot

    Must be used with functools.partial

    If the main bot.run dies for some reason,
    we don't want to swallow the exception and hang.
    """
    try:
        bot_task.result()
    except (SystemExit, KeyboardInterrupt, asyncio.CancelledError):
        pass  # Handled by the global_exception_handler, or cancellation
    except Exception as exc:
        log.critical("The main bot task didn't handle an exception and has crashed", exc_info=exc)
        log.warning("Attempting to die as gracefully as possible...")
        asyncio.create_task(shutdown_handler(bot))


async def init_sentry():
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_env,
            release=bot_version,
            integrations=[AsyncioIntegration()],
        )  # TODO: Add breadcrumbs for clustering
        log.info("Sentry initialized.")


class RemoveWSBehindMsg(logging.Filter):
    """Filter used when gateway proxy is set, the "behind" message is meaningless in this case."""

    def __init__(self):
        super().__init__(name="discord.gateway")

    def filter(self, record):
        if record.levelname == "WARNING" and "Can't keep up" in record.msg:
            return False

        return True


class Command(BaseCommand):
    help = (
        "Generate a local preview of a card. This will use the system's image viewer "
        "or print to stdout if the output is being piped."
    )

    def add_arguments(self, parser: CommandParser):
        parser.add_argument("--disable-rich", action="store_true", help="Disable rich log format")
        parser.add_argument("--gateway-url", type=str, help="Define a gateway proxy")
        parser.add_argument("--shard-count", type=int, help="Enforce a specific number of shards to open")
        parser.add_argument(
            "--shard-ids", type=int, nargs="+", help="Enforce list of shard IDs to connect to, delimited by space"
        )
        parser.add_argument("--cluster-name", type=str, help="Name of this cluster")
        parser.add_argument("--cluster-id", type=int, help="ID of this cluster")
        parser.add_argument("--cluster-count", type=int, help="Total number of clusters")
        parser.add_argument(
            "--disable-message-content",
            action="store_true",
            help="Disable usage of message content intent through the bot",
        )
        parser.add_argument(
            "--disable-time-check",
            action="store_true",
            help="Disables the 3 seconds delay check on interactions. Use this if you're getting "
            "a lot of skipped interactions warning due to your PC's internal clock.",
        )
        parser.add_argument(
            "--skip-tree-sync",
            action="store_true",
            help="Does not sync application commands to Discord. Significant startup speedup and "
            "avoids ratelimits, but risks of having desynced commands after updates. This is "
            "always enabled with clustering.",
        )
        parser.add_argument("--debug", action="store_true", help="Enable debug logs")
        parser.add_argument("--dev", action="store_true", help="Enable developer mode")

    def handle(self, *args, **options: Unpack[CLIFlags]):
        bot = None
        server = None

        load_settings()
        if not settings.bot_token:
            self.stderr.write(
                self.style.ERROR(
                    "You have not configured bot settings yet! Open the admin panel and write a settings entry."
                )
            )
            sys.exit(1)

        print_welcome()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            token = settings.bot_token
            if not token:
                log.error("Token not found!")
                raise CommandError("You must provide a token inside the config.yml file.")

            db_url = os.environ.get("BALLSDEXBOT_DB_URL", None)
            if not db_url:
                log.error("Database URL not found!")
                raise CommandError("You must provide a DB URL with the BALLSDEXBOT_DB_URL env var.")

            clustering_args = [
                bool(x)
                for x in (
                    options["shard_ids"],
                    options["cluster_id"],
                    options["cluster_name"],
                    options["cluster_count"],
                )
            ]
            if any(clustering_args) and not all(clustering_args):
                raise CommandError(
                    "If you are running in clustering mode, you must provide all flags: "
                    "--shard-ids --cluster-id --cluster-name --cluster-count"
                )

            if options["gateway_url"] is not None:
                log.info("Using custom gateway URL: %s", options["gateway_url"])
                patch_gateway(options["gateway_url"])
                logging.getLogger("discord.gateway").addFilter(RemoveWSBehindMsg())

            prefix = settings.prefix

            bot = BallsDexBot(
                command_prefix=when_mentioned_or(prefix),
                dev=options["dev"],  # type: ignore
                shard_count=options["shard_count"],
                shard_ids=options["shard_ids"],
                cluster_id=options["cluster_id"],
                cluster_name=options["cluster_name"],
                cluster_count=options["cluster_count"],
                gateway_url=options["gateway_url"],
                disable_message_content=options["disable_message_content"],
                disable_time_check=options["disable_time_check"],
                skip_tree_sync=options["skip_tree_sync"],
            )

            loop.run_until_complete(init_sentry())
            exc_handler = functools.partial(global_exception_handler, bot)
            loop.set_exception_handler(exc_handler)
            try:
                loop.add_signal_handler(SIGTERM, lambda: loop.create_task(shutdown_handler(bot, "SIGTERM")))
            except NotImplementedError:
                log.warning("Cannot add signal handler for SIGTERM.")

            log.info("Initialized bot, connecting to Discord...")
            future = loop.create_task(bot.start(token))
            bot_exc_handler = functools.partial(bot_exception_handler, bot)
            future.add_done_callback(bot_exc_handler)

            loop.run_forever()
        except KeyboardInterrupt:
            if bot is not None:
                loop.run_until_complete(shutdown_handler(bot, "Ctrl+C"))
        except CommandError:
            raise
        except Exception:
            log.critical("Unhandled exception.", exc_info=True)
            if bot is not None:
                loop.run_until_complete(shutdown_handler(bot))
        finally:
            if queue := cast(logging.handlers.QueueHandler | None, logging.getHandlerByName("queue")):
                if queue.listener:
                    queue.listener.stop()
            loop.run_until_complete(loop.shutdown_asyncgens())
            if server is not None:
                loop.run_until_complete(server.stop())
            asyncio.set_event_loop(None)
            loop.stop()
            loop.close()
            sys.exit(bot._shutdown if bot else 1)
