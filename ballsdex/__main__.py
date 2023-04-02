import os
import sys
import time
import functools
import asyncio
import logging
import logging.handlers
import discord
import argparse

from pathlib import Path
from rich import print
from tortoise import Tortoise
from aerich import Command
from signal import SIGTERM
from discord.utils import setup_logging
from discord.ext.commands import when_mentioned_or

from ballsdex import __version__ as bot_version
from ballsdex.settings import settings, read_settings, write_default_settings
from ballsdex.core.bot import BallsDexBot

discord.voice_client.VoiceClient.warn_nacl = False  # disable PyNACL warning
log = logging.getLogger("ballsdex")

TORTOISE_ORM = {
    "connections": {"default": os.environ.get("BALLSDEXBOT_DB_URL")},
    "apps": {
        "models": {
            "models": ["ballsdex.core.models", "aerich.models"],
            "default_connection": "default",
        },
    },
}


class CLIFlags(argparse.Namespace):
    version: bool
    config_file: Path
    reset_settings: bool
    disable_rich: bool
    debug: bool
    dev: bool


def parse_cli_flags(arguments: list[str]) -> CLIFlags:
    parser = argparse.ArgumentParser(
        prog="BallsDex bot", description="Collect and exchange countryballs on Discord"
    )
    parser.add_argument("--version", "-V", action="store_true", help="Display the bot's version")
    parser.add_argument(
        "--config-file", type=Path, help="Set the path to config.yml", default=Path("./config.yml")
    )
    parser.add_argument(
        "--reset-settings",
        action="store_true",
        help="Reset the config file with the latest default configuration",
    )
    parser.add_argument("--disable-rich", action="store_true", help="Disable rich log format")
    parser.add_argument("--debug", action="store_true", help="Enable debug logs")
    parser.add_argument("--dev", action="store_true", help="Enable developer mode")
    args = parser.parse_args(arguments, namespace=CLIFlags())
    return args


def reset_settings(path: Path):
    write_default_settings(path)
    print(f"[green]A new settings file has been written at [blue]{path}[/blue].[/green]")
    print("[yellow]Configure the [bold]discord-token[/bold] value and restart the bot.[/yellow]")
    sys.exit(0)


def print_welcome():
    print("[green]{0:-^50}[/green]".format(f" {settings.bot_name} bot "))
    print("[green]{0: ^50}[/green]".format(f" Collect {settings.collectible_name}s "))
    print("[blue]{0:^50}[/blue]".format("Discord bot made by El Laggron"))
    print("")
    print(" [red]{0:<20}[/red] [yellow]{1:>10}[/yellow]".format("Bot version:", bot_version))
    print(
        " [red]{0:<20}[/red] [yellow]{1:>10}[/yellow]".format(
            "Discord.py version:", discord.__version__
        )
    )
    print("")


async def shutdown_handler(bot: BallsDexBot, signal_type: str | None = None):
    if signal_type:
        log.info(f"Received {signal_type}, stopping the bot...")
        sys.exit(signal_type)
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


def global_exception_handler(bot: BallsDexBot, loop: asyncio.AbstractEventLoop, context: dict):
    """
    Logs unhandled exceptions in other tasks
    """
    exc = context.get("exception")
    # These will get handled later when it *also* kills loop.run_forever
    if exc is not None and isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return
    log.critical(
        "Caught unhandled exception in %s:\n%s",
        context.get("future", "event loop"),
        context["message"],
        exc_info=exc,
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


def init_logger(disable_rich: bool = False, debug: bool = False):
    formatter = logging.Formatter(
        "[{asctime}] {levelname} {name}: {message}", datefmt="%Y-%m-%d %H:%M:%S", style="{"
    )

    if disable_rich:
        setup_logging(formatter=formatter, level=logging.INFO)
    else:
        setup_logging(level=logging.INFO)

    if debug:
        log.setLevel(logging.DEBUG)

    # file handler
    file_handler = logging.handlers.RotatingFileHandler(
        "ballsdex.log", maxBytes=8**7, backupCount=8
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logging.getLogger().addHandler(file_handler)

    logging.getLogger("aiohttp").setLevel(logging.WARNING)  # don't log each prometheus call


async def init_tortoise(db_url: str):
    log.debug(f"Database URL: {db_url}")
    await Tortoise.init(config=TORTOISE_ORM)

    # migrations
    command = Command(TORTOISE_ORM, app="models")
    await command.init()
    migrations = await command.upgrade()
    if migrations:
        log.info(f"Ran {len(migrations)} migrations: {', '.join(migrations)}")


def main():
    bot = None
    server = None
    cli_flags = parse_cli_flags(sys.argv[1:])
    if cli_flags.version:
        print(f"BallsDex Discord bot - {bot_version}")
        sys.exit(0)
    if cli_flags.reset_settings:
        print("[yellow]Resetting configuration file.[/yellow]")
        reset_settings(cli_flags.config_file)

    try:
        read_settings(cli_flags.config_file)
    except FileNotFoundError:
        print("[yellow]The config file could not be found, generating a default one.[/yellow]")
        reset_settings(cli_flags.config_file)

    print_welcome()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        init_logger(cli_flags.disable_rich, cli_flags.debug)

        token = settings.bot_token
        if not token:
            log.error("Token not found!")
            print("[red]You must provide a token inside the config.yml file.[/red]")
            time.sleep(1)
            sys.exit(0)

        db_url = os.environ.get("BALLSDEXBOT_DB_URL", None)
        if not db_url:
            log.error("Database URL not found!")
            print("[red]You must provide a DB URL with the BALLSDEXBOT_DB_URL env var.[/red]")
            time.sleep(1)
            sys.exit(0)

        prefix = settings.prefix

        try:
            loop.run_until_complete(init_tortoise(db_url))
        except Exception:
            log.exception("Failed to connect to database.")
            return  # will exit with code 1
        log.debug("Tortoise ORM and database ready.")

        bot = BallsDexBot(
            command_prefix=when_mentioned_or(prefix), dev=cli_flags.dev  # type: ignore
        )

        exc_handler = functools.partial(global_exception_handler, bot)
        loop.set_exception_handler(exc_handler)
        loop.add_signal_handler(
            SIGTERM, lambda: loop.create_task(shutdown_handler(bot, "SIGTERM"))
        )

        log.info("Initialized bot, connecting to Discord...")
        future = loop.create_task(bot.start(token))
        bot_exc_handler = functools.partial(bot_exception_handler, bot)
        future.add_done_callback(bot_exc_handler)

        loop.run_forever()
    except KeyboardInterrupt:
        if bot is not None:
            loop.run_until_complete(shutdown_handler(bot, "Ctrl+C"))
    except SystemExit:
        if bot is not None:
            loop.run_until_complete(shutdown_handler(bot))
    except Exception:
        log.critical("Unhandled exception.", exc_info=True)
        if bot is not None:
            loop.run_until_complete(shutdown_handler(bot))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        if server is not None:
            loop.run_until_complete(server.stop())
        if Tortoise._inited:
            loop.run_until_complete(Tortoise.close_connections())
        asyncio.set_event_loop(None)
        loop.stop()
        loop.close()
        sys.exit(bot._shutdown if bot else 1)


if __name__ == "__main__":
    main()
