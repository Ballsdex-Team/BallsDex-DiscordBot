import ast
import asyncio
import contextlib
import inspect
import io
import os
import re
import subprocess
import textwrap
import time
import traceback
from contextlib import redirect_stdout
from copy import copy
from io import BytesIO
from typing import TYPE_CHECKING, Iterable

import aiohttp
import discord
from discord.ext import commands
from django.db import connection

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import Menu, TextFormatter, TextSource
from bd_models import models
from bd_models.enums import DonationPolicy, FriendPolicy, MentionPolicy, PrivacyPolicy
from bd_models.models import (
    Ball,
    BallInstance,
    BlacklistedGuild,
    BlacklistedID,
    BlacklistHistory,
    Block,
    Economy,
    Friendship,
    GuildConfig,
    Player,
    Regime,
    Special,
    Trade,
    TradeObject,
)

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

"""
Notice:

Most of this code belongs to Cog-Creators and Danny

https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/core/dev_commands.py
https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/core/utils/chat_formatting.py
https://github.com/Rapptz/RoboDanny/blob/master/cogs/repl.py
"""

ANSI_RED = "\x1b[31m"
ANSI_BOLD = "\x1b[1m"
ANSI_RESET = "\x1b[0m"


def format_duration(time_taken: float) -> str:
    return f"{round(time_taken * 1000)}ms" if time_taken < 1 else f"{round(time_taken, 3)}s"


def box(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text}\n```"


def text_to_file(
    text: str, filename: str = "file.txt", *, spoiler: bool = False, encoding: str = "utf-8"
) -> discord.File:
    file = BytesIO(text.encode(encoding))
    return discord.File(file, filename, spoiler=spoiler)


def format_exception(text: str) -> str:
    """
    Formats the last line of an exception.

    Parameters
    ----------
    text: str
        The text you want to format.

    Returns
    -------
    str
        The formatted text.
    """
    lines = text.splitlines()

    if lines:
        lines[-1] = f"{ANSI_RED}{ANSI_BOLD}{lines[-1]}{ANSI_RESET}"

    return "\n".join(lines)


async def send_interactive(
    ctx: commands.Context["BallsDexBot"],
    messages: Iterable[str],
    *,
    timeout: int = 15,
    time_taken: float | None = None,
    block: str | None = "py",
) -> list[discord.Message]:
    """
    Send multiple messages interactively.

    The user will be prompted for whether or not they would like to view
    the next message, one at a time. They will also be notified of how
    many messages are remaining on each prompt.

    Parameters
    ----------
    ctx : discord.ext.commands.Context
        The context to send the messages to.
    messages : `iterable` of `str`
        The messages to send.
    timeout : int
        How long the user has to respond to the prompt before it times out.
        After timing out, the bot deletes its prompt message.
    time_taken: float | None
        The time (in seconds) taken to complete the evaluation.

    Returns
    -------
    list[discord.Message]
        A list of sent messages.
    """
    result = 0

    def predicate(m: discord.Message):
        nonlocal result
        if (ctx.author.id != m.author.id) or ctx.channel.id != m.channel.id:
            return False
        try:
            result = ("more", "file").index(m.content.lower())
        except ValueError:
            return False
        else:
            return True

    messages = tuple(messages)
    ret = []

    for idx, page in enumerate(messages, 1):
        if block:
            text = box(page, lang=block)
        else:
            text = page
        if time_taken and idx == len(messages):
            text += f"\n-# Took {format_duration(time_taken)}"
        msg = await ctx.channel.send(text)
        ret.append(msg)
        n_remaining = len(messages) - idx
        if n_remaining > 0:
            if n_remaining == 1:
                prompt_text = (
                    "There is still one message remaining. Type {command_1} to continue"
                    " or {command_2} to upload all contents as a file."
                )
            else:
                prompt_text = (
                    "There are still {count} messages remaining. Type {command_1} to continue"
                    " or {command_2} to upload all contents as a file."
                )
            query = await ctx.channel.send(
                prompt_text.format(count=n_remaining, command_1="`more`", command_2="`file`")
            )
            try:
                resp = await ctx.bot.wait_for("message", check=predicate, timeout=timeout)
            except asyncio.TimeoutError:
                with contextlib.suppress(discord.HTTPException):
                    await query.delete()
                break
            else:
                try:
                    await ctx.channel.delete_messages((query, resp))  # type: ignore
                except (discord.HTTPException, AttributeError):
                    # In case the bot can't delete other users' messages,
                    # or is not a bot account
                    # or channel is a DM
                    with contextlib.suppress(discord.HTTPException):
                        await query.delete()
                if result == 1:
                    ret.append(await ctx.channel.send(file=text_to_file("".join(messages))))
                    break
    return ret


class FileRow(discord.ui.ActionRow):
    """
    File row displayed in eval responses that uploads the specified content as a file.

    Parameters
    ----------
    content: str
        The content that will be exported as a file.
    """

    def __init__(self, content: str):
        super().__init__()
        self.content = content

    @discord.ui.button(label="File")
    async def file_button(self, interaction: discord.Interaction["BallsDexBot"], _):
        await interaction.response.send_message(file=text_to_file(self.content))


async def build_eval_response(
    ctx: commands.Context["BallsDexBot"], content: str, *, time_taken: float, error: bool = False
) -> LayoutView:
    """
    Creates a view with a paginator menu and a button to send the specified content as a file.

    Parameters
    ----------
    content: str
        The content that will be displayed.
    time_taken: float
        The amount of time taken in milliseconds for the code to execute.
    error: bool
        Whether ansi formatting will be enabled.

    Returns
    -------
    LayoutView
        The created view.
    """
    code_prefix = "ansi" if error else "py"
    formatted_content = format_exception(content) if error else content

    text_display = discord.ui.TextDisplay("")

    view = LayoutView()
    view.add_item(text_display)
    view.add_item(discord.ui.TextDisplay(f"-# Took {format_duration(time_taken)}"))
    view.restrict_author(ctx.author.id)

    menu = Menu(
        ctx.bot,
        view,
        TextSource(formatted_content, prefix=f"```{code_prefix}\n", suffix="\n```"),
        TextFormatter(text_display),
    )
    await menu.init()

    if menu.source.get_max_pages() > 1:
        menu.view.add_item(FileRow(content))

    return view


START_CODE_BLOCK_RE = re.compile(r"^((```(py(thon)?|sql))(?=\s)|(```))")


class Dev(commands.Cog):
    """Various development focused utilities."""

    def __init__(self):
        super().__init__()
        self._last_result = None
        self.sessions = {}
        self.env_extensions = {}

    @staticmethod
    def async_compile(source, filename, mode):
        return compile(source, filename, mode, flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, optimize=0)

    @staticmethod
    async def maybe_await(coro):
        for i in range(2):
            if inspect.isawaitable(coro):
                coro = await coro
            else:
                return coro
        return coro

    @staticmethod
    def cleanup_code(content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            return START_CODE_BLOCK_RE.sub("", content)[:-3]

        # remove `foo`
        return content.strip("` \n")

    @classmethod
    def get_syntax_error(cls, e) -> str:
        """Format a syntax error to send to the user.

        Returns a string representation of the error formatted as a codeblock.
        """
        if e.text is None:
            return "{0.__class__.__name__}: {0}".format(e)

        return "{0.text}\n{1:>{0.offset}}\n{2}: {0}".format(e, "^", type(e).__name__)

    @staticmethod
    def sanitize_output(ctx: commands.Context, input_: str) -> str:
        """Hides the bot's token from a string."""
        token = ctx.bot.http.token
        return re.sub(re.escape(token), "[EXPUNGED]", input_, re.I)

    def get_environment(self, ctx: commands.Context) -> dict:
        env = {
            "bot": ctx.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "asyncio": asyncio,
            "aiohttp": aiohttp,
            "discord": discord,
            "commands": commands,
            "models": models,
            "Ball": Ball,
            "BallInstance": BallInstance,
            "Player": Player,
            "GuildConfig": GuildConfig,
            "BlacklistedID": BlacklistedID,
            "BlacklistedGuild": BlacklistedGuild,
            "Special": Special,
            "Trade": Trade,
            "TradeObject": TradeObject,
            "Regime": Regime,
            "Economy": Economy,
            "DonationPolicy": DonationPolicy,
            "PrivacyPolicy": PrivacyPolicy,
            "MentionPolicy": MentionPolicy,
            "FriendPolicy": FriendPolicy,
            "BlacklistHistory": BlacklistHistory,
            "Friendship": Friendship,
            "Block": Block,
            "text_to_file": text_to_file,
            "_": self._last_result,
            "__name__": "__main__",
        }
        for name, value in self.env_extensions.items():
            try:
                env[name] = value(ctx)
            except Exception as e:
                traceback.clear_frames(e.__traceback__)
                env[name] = e
        return env

    @commands.command()
    @commands.is_owner()
    async def debug(self, ctx: commands.Context, *, code):
        """Evaluate a statement of python code.

        The bot will always respond with the return value of the code.
        If the return value of the code is a coroutine, it will be awaited,
        and the result of that will be the bot's response.

        Note: Only one statement may be evaluated. Using certain restricted
        keywords, e.g. yield, will result in a syntax error. For multiple
        lines or asynchronous code, see [p]repl or [p]eval.

        Environment Variables:
            ctx      - command invocation context
            bot      - bot object
            channel  - the current channel object
            author   - command author's member object
            message  - the command's message object
            discord  - discord.py library
            commands - redbot.core.commands
            _        - The result of the last dev command.
        """
        env = self.get_environment(ctx)
        code = self.cleanup_code(code)

        t1 = time.time()
        try:
            compiled = self.async_compile(code, "<string>", "eval")
            result = await self.maybe_await(eval(compiled, env))
        except SyntaxError as e:
            t2 = time.time()
            view = await build_eval_response(ctx, self.get_syntax_error(e), time_taken=t2 - t1, error=True)
            await ctx.send(view=view)
            return
        except Exception as e:
            t2 = time.time()
            view = await build_eval_response(
                ctx, "{}: {!s}".format(type(e).__name__, e), time_taken=t2 - t1, error=True
            )
            await ctx.send(view=view)
            return
        t2 = time.time()

        self._last_result = result
        result = self.sanitize_output(ctx, str(result))

        await ctx.message.add_reaction("✅")

        view = await build_eval_response(ctx, result, time_taken=t2 - t1)
        await ctx.send(view=view)

    @commands.command(name="eval")
    @commands.is_owner()
    async def _eval(self, ctx: commands.Context, *, body: str):
        """Execute asynchronous code.

        This command wraps code into the body of an async function and then
        calls and awaits it. The bot will respond with anything printed to
        stdout, as well as the return value of the function.

        The code can be within a codeblock, inline code or neither, as long
        as they are not mixed and they are formatted correctly.

        Environment Variables:
            ctx      - command invocation context
            bot      - bot object
            channel  - the current channel object
            author   - command author's member object
            message  - the command's message object
            discord  - discord.py library
            commands - redbot.core.commands
            _        - The result of the last dev command.
        """
        env = self.get_environment(ctx)
        body = self.cleanup_code(body)
        stdout = io.StringIO()

        to_compile = "async def func():\n%s" % textwrap.indent(body, "  ")

        t1 = time.time()
        try:
            compiled = self.async_compile(to_compile, "<string>", "exec")
            exec(compiled, env)
        except SyntaxError as e:
            t2 = time.time()
            view = await build_eval_response(ctx, self.get_syntax_error(e), time_taken=t2 - t1, error=True)
            await ctx.send(view=view)
            return
        except Exception as e:
            t2 = time.time()
            view = await build_eval_response(
                ctx, "{}: {!s}".format(type(e).__name__, e), time_taken=t2 - t1, error=True
            )
            await ctx.send(view=view)
            return

        func = env["func"]
        result = None
        errored = False
        try:
            with redirect_stdout(stdout):
                result = await func()
        except Exception:
            t2 = time.time()
            printed = "{}{}".format(stdout.getvalue(), traceback.format_exc())
            errored = True
        else:
            t2 = time.time()
            printed = stdout.getvalue()
            await ctx.message.add_reaction("✅")

        if result is not None:
            self._last_result = result
            msg = "{}{}".format(printed, result)
        else:
            msg = printed
        msg = self.sanitize_output(ctx, msg)

        view = await build_eval_response(ctx, msg, time_taken=t2 - t1, error=errored)
        await ctx.send(view=view)

    @commands.command()
    @commands.is_owner()
    async def dbeval(self, ctx: commands.Context, *, content: str):
        """
        Execute the given SQL query and return the result.
        """
        body = self.cleanup_code(content)

        try:
            params = connection.get_connection_params()
            cmd = [
                "psql",
                "--file=-",
                f"--dbname={params['dbname']}",
                f"--host={params['host']}",
                f"--port={params['port']}",
                f"--username={params['user']}",
                "--no-password",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env={**os.environ, "PGPASSWORD": params["password"]},
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            async with ctx.typing():
                stdout, _ = await asyncio.wait_for(proc.communicate(f"\\timing on\n{body}".encode()), timeout=300)
            stdout = stdout.removeprefix(b"Timing is on.\n")
        except asyncio.TimeoutError:
            await ctx.reply("Timed out waiting for response (5 mins).")
        except FileNotFoundError:
            await ctx.send("`psql` was not found on the host, unable to use this command.")
        else:
            # always send the result as a file to allow horizontal scrolling in Discord
            # using a code block creates wrapping, which looks horrible on psql output
            text = None
            if proc.returncode != 0:
                text = f"Exit code: {proc.returncode}"
            await ctx.reply(text, file=discord.File(io.BytesIO(stdout), filename="output.txt"))

    @commands.command()
    @commands.is_owner()
    async def mock(self, ctx: commands.Context, user: discord.Member, *, command):
        """Mock another user invoking a command.

        The prefix must not be entered.
        """
        msg = copy(ctx.message)
        msg.author = user
        msg.content = ctx.prefix + command

        ctx.bot.dispatch("message", msg)

    @commands.command(name="mockmsg")
    @commands.is_owner()
    async def mock_msg(self, ctx: commands.Context, user: discord.Member, *, content: str):
        """Dispatch a message event as if it were sent by a different user.

        Only reads the raw content of the message. Attachments, embeds etc. are
        ignored.
        """
        old_author = ctx.author
        old_content = ctx.message.content
        ctx.message.author = user
        ctx.message.content = content

        ctx.bot.dispatch("message", ctx.message)

        # If we change the author and content back too quickly,
        # the bot won't process the mocked message in time.
        await asyncio.sleep(2)
        ctx.message.author = old_author
        ctx.message.content = old_content
