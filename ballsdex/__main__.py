import os
import sys
import time
import functools
import asyncio
import logging
import discord
import argparse
import uvicorn
import aioredis

from rich import print
from tortoise import Tortoise
from aerich import Command
from signal import SIGTERM

from fastapi import FastAPI
from fastapi_admin.app import app as admin_app
from fastapi_admin.exceptions import (
    forbidden_error_exception,
    not_found_error_exception,
    server_error_exception,
    unauthorized_error_exception,
)
from fastapi_admin.providers.login import UsernamePasswordProvider
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from uvicorn.server import HANDLED_SIGNALS

from ballsdex import __version__ as bot_version
from ballsdex.loggers import init_logger
from ballsdex.core.bot import BallsDexBot
from ballsdex.core.admin.resources import User

BASE_DIR = os.path.dirname(os.path.abspath(os.path.join(__file__, os.path.pardir)))
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
    disable_rich: bool
    debug: bool
    dev: bool


def parse_cli_flags(arguments: list[str]) -> CLIFlags:
    parser = argparse.ArgumentParser(
        prog="BallsDex bot", description="Collect and exchange countryballs on Discord"
    )
    parser.add_argument("--version", "-V", action="store_true", help="Display the bot's version")
    parser.add_argument("--disable-rich", action="store_true", help="Disable rich log format")
    parser.add_argument("--debug", action="store_true", help="Enable debug logs")
    parser.add_argument("--dev", action="store_true", help="Enable developer mode")
    args = parser.parse_args(arguments, namespace=CLIFlags())
    return args


def print_welcome():
    print("[green]{0:-^50}[/green]".format(" BallsDex bot "))
    print("[green]{0: ^50}[/green]".format(" Collect countryballs "))
    print("[blue]{0:^50}[/blue]".format("Discord bot made by El Laggron"))
    print("")
    print(" [red]{0:<20}[/red] [yellow]{1:>10}[/yellow]".format("Bot version:", bot_version))
    print(
        " [red]{0:<20}[/red] [yellow]{1:>10}[/yellow]".format(
            "Discord.py version:", discord.__version__
        )
    )
    print("")


async def shutdown_handler(bot: BallsDexBot, signal_type: str = None):
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


async def init_tortoise(db_url: str):
    log.debug(f"Database URL: {db_url}")
    await Tortoise.init(config=TORTOISE_ORM)

    # migrations
    command = Command(TORTOISE_ORM, app="models")
    await command.init()
    migrations = await command.upgrade()
    if migrations:
        log.info(f"Ran {len(migrations)} migrations: {', '.join(migrations)}")


def init_fastapi_app() -> FastAPI:
    app = FastAPI()
    app.mount(
        "/static",
        StaticFiles(directory=os.path.join(BASE_DIR, "static")),
        name="static",
    )

    @app.get("/")
    async def index():
        return RedirectResponse(url="/admin")

    admin_app.add_exception_handler(HTTP_500_INTERNAL_SERVER_ERROR, server_error_exception)
    admin_app.add_exception_handler(HTTP_404_NOT_FOUND, not_found_error_exception)
    admin_app.add_exception_handler(HTTP_403_FORBIDDEN, forbidden_error_exception)
    admin_app.add_exception_handler(HTTP_401_UNAUTHORIZED, unauthorized_error_exception)

    @app.on_event("startup")
    async def startup():
        redis = aioredis.from_url(
            os.environ.get("BALLSDEXBOT_REDIS_URL"), decode_responses=True, encoding="utf8"
        )
        await admin_app.configure(
            logo_url="https://preview.tabler.io/static/logo-white.svg",
            template_folders=[os.path.join(BASE_DIR, "ballsdex", "templates")],
            favicon_url="https://raw.githubusercontent.com/fastapi-admin/"
            "fastapi-admin/dev/images/favicon.png",
            providers=[
                UsernamePasswordProvider(
                    login_logo_url="https://preview.tabler.io/static/logo.svg",
                    admin_model=User,
                )
            ],
            redis=redis,
        )

    app.mount("/admin", admin_app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    # register_tortoise(
    #     app,
    #     config={
    #         "connections": {"default": "sqlite://db.sqlite3"},
    #         "apps": {
    #             "models": {
    #                 "models": ["examples.models"],
    #                 "default_connection": "default",
    #             }
    #         },
    #     },
    #     generate_schemas=True,
    # )

    # @app.on_event("shutdown")
    # async def on_shutdown():
    return app


_app = init_fastapi_app()


async def start_fastapi(loop: asyncio.BaseEventLoop):
    config = uvicorn.Config(
        "ballsdex.__main__:_app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        debug=True,
        loop=loop,
        log_config=None,
    )
    server = uvicorn.Server(config)

    async def remove_signal_handlers():
        await asyncio.sleep(0.5)
        for signal in HANDLED_SIGNALS:
            loop.remove_signal_handler(signal)

    loop.create_task(remove_signal_handlers())

    try:
        await server.serve()
    except asyncio.CancelledError:
        try:
            await asyncio.wait_for(server.shutdown(), timeout=1.0)
        except asyncio.TimeoutError:
            log.error("Timed out cancelling FastAPI server.")


def main():
    bot = None
    cli_flags = parse_cli_flags(sys.argv[1:])
    if cli_flags.version:
        print(f"BallsDex Discord bot - {bot_version}")
        sys.exit(0)

    print_welcome()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        init_logger(cli_flags.disable_rich, cli_flags.debug)

        token = os.environ.get("BALLSDEXBOT_TOKEN", None)
        if not token:
            log.error("Token not found!")
            print("[yellow]You must provide a token with the BALLSDEXBOT_TOKEN env var.[/yellow]")
            time.sleep(1)
            sys.exit(0)

        db_url = os.environ.get("BALLSDEXBOT_DB_URL", None)
        if not db_url:
            log.error("Database URL not found!")
            print(
                "[yellow]You must provide a DB URL with the BALLSDEXBOT_DB_URL env var.[/yellow]"
            )
            time.sleep(1)
            sys.exit(0)

        if not os.environ.get("BALLSDEXBOT_REDIS_URL", None):
            log.error("Redis URL not found!")
            print(
                "[yellow]You must provide a Redis URL with "
                "the BALLSDEXBOT_REDIS_URL env var.[/yellow]"
            )
            time.sleep(1)
            sys.exit(0)

        loop.run_until_complete(init_tortoise(db_url))
        log.debug("Tortoise ORM and database ready.")

        bot = BallsDexBot(command_prefix="!?", dev=cli_flags.dev)
        bot.owner_id = 348415857728159745

        exc_handler = functools.partial(global_exception_handler, bot)
        loop.set_exception_handler(exc_handler)
        loop.add_signal_handler(
            SIGTERM, lambda: loop.create_task(shutdown_handler(bot, "SIGTERM"))
        )

        log.info("Initialized bot, connecting to Discord...")
        future = loop.create_task(bot.start(token))
        bot_exc_handler = functools.partial(bot_exception_handler, bot)
        future.add_done_callback(bot_exc_handler)

        loop.create_task(start_fastapi(loop))
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
        if Tortoise._inited:
            loop.run_until_complete(Tortoise.close_connections())
        asyncio.set_event_loop(None)
        loop.stop()
        loop.close()
        sys.exit(bot._shutdown if bot else 1)


if __name__ == "__main__":
    main()
