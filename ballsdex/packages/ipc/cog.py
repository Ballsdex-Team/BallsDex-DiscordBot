import asyncio
import contextlib
import io
import json
from logging import getLogger
import textwrap
import traceback
from uuid import uuid4
from typing import TYPE_CHECKING, Iterable, Iterator, Sequence

import discord
from discord.ext import commands
if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

from ballsdex.core.models import BlacklistedGuild, BlacklistedID
from ballsdex.settings import settings

log = getLogger("ballsdex.packages.ipc.cog")

def escape(text: str, *, mass_mentions: bool = False, formatting: bool = False) -> str:
    if mass_mentions:
        text = text.replace("@everyone", "@\u200beveryone")
        text = text.replace("@here", "@\u200bhere")
    if formatting:
        text = discord.utils.escape_markdown(text)
    return text

def pagify(
    text: str,
    delims: Sequence[str] = ["\n"],
    *,
    priority: bool = False,
    escape_mass_mentions: bool = True,
    shorten_by: int = 8,
    page_length: int = 2000,
) -> Iterator[str]:
    in_text = text
    page_length -= shorten_by
    while len(in_text) > page_length:
        this_page_len = page_length
        if escape_mass_mentions:
            this_page_len -= in_text.count("@here", 0, page_length) + in_text.count(
                "@everyone", 0, page_length
            )
        closest_delim = (in_text.rfind(d, 1, this_page_len) for d in delims)
        if priority:
            closest_delim = next((x for x in closest_delim if x > 0), -1)
        else:
            closest_delim = max(closest_delim)
        closest_delim = closest_delim if closest_delim != -1 else this_page_len
        if escape_mass_mentions:
            to_send = escape(in_text[:closest_delim], mass_mentions=True)
        else:
            to_send = in_text[:closest_delim]
        if len(to_send.strip()) > 0:
            yield to_send
        in_text = in_text[closest_delim:]

    if len(in_text.strip()) > 0:
        if escape_mass_mentions:
            yield escape(in_text, mass_mentions=True)
        else:
            yield in_text


def box(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text}\n```"


def text_to_file(
    text: str, filename: str = "file.txt", *, spoiler: bool = False, encoding: str = "utf-8"
) -> discord.File:
    file = io.BytesIO(text.encode(encoding))
    return discord.File(file, filename, spoiler=spoiler)
async def send_interactive(
    ctx: commands.Context["BallsDexBot"],
    messages: Iterable[str],
    *,
    timeout: int = 15,
) -> list[discord.Message]:
    """
    Send multiple messages interactively.

    The user will be prompted for whether or not they would like to view
    the next message, one at a time. They will also be notified of how
    many messages are remaining on each prompt.

    Parameters
    ----------
    channel : discord.abc.Messageable
        The channel to send the messages to.
    messages : `iterable` of `str`
        The messages to send.
    user : discord.User
        The user that can respond to the prompt.
        When this is ``None``, any user can respond.
    box_lang : Optional[str]
        If specified, each message will be contained within a code block of
        this language.
    timeout : int
        How long the user has to respond to the prompt before it times out.
        After timing out, the bot deletes its prompt message.
    join_character : str
        The character used to join all the messages when the file output
        is selected.

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
        msg = await ctx.channel.send(box(page, lang="py"))
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
                resp = await ctx.bot.wait_for(
                    "message",
                    check=predicate,
                    timeout=15,
                )
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

class IPC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.router = None
        self.pubsub = self.bot.redis.pubsub()
        asyncio.create_task(self.register_sub())
        self._messages = dict()

    def cog_unload(self):
        asyncio.create_task(self.unregister_sub())

    async def register_sub(self):
        await self.pubsub.subscribe(settings.redis_db)
        self.router = asyncio.create_task(self.event_handler())

    async def unregister_sub(self):
        if self.router and not self.router.cancelled:
            self.router.cancel()
        await self.pubsub.unsubscribe(settings.redis_db)

    async def event_handler(self):
        async for message in self.pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                payload = json.loads(message["data"])
            except json.JSONDecodeError:
                continue
            if payload.get("action") and hasattr(self, payload.get("action")):
                if payload.get("scope") != "bot":
                    continue
                if payload.get("args"):
                    asyncio.create_task(
                        getattr(self, payload["action"])(
                            **payload["args"],
                            command_id=payload["command_id"],
                        )
                    )
                else:
                    asyncio.create_task(
                        getattr(self, payload["action"])(command_id=payload["command_id"])
                    )
            if payload.get("output") and payload.get("command_id") in self._messages:
                for fut in self._messages[payload["command_id"]]:
                    if not fut.done():
                        fut.set_result(payload["output"])
                        break

    async def guild_count(self, command_id: str):
        payload = {"output": len(self.bot.guilds), "command_id": command_id}
        await self.bot.redis.execute_command(
            "PUBLISH",
            settings.redis_db,
            json.dumps(payload),
        )

    async def shard_count(self, command_id: str):
        payload = {
            "output": {
                f"{self.bot.cluster_id}": [
                    self.bot.cluster_name,
                    self.bot.shard_ids,
                ]
            },
            "command_id": command_id,
        }
        await self.bot.redis.execute_command(
            "PUBLISH",
            settings.redis_db,
            json.dumps(payload),
        )

    async def evaluate(self, code, command_id: str):
        cog = self.bot.get_cog("Dev")
        if not cog:
            return
        env = cog.get_environment(None)
        code = cog.cleanup_code(code)
        stdout = io.StringIO()
        to_compile = "async def func():\n%s" % textwrap.indent(code, "  ")
        msg = None
        try:
            compiled = cog.async_compile(to_compile, "<string>", "exec")
            exec(compiled, env)
            # result = cog.sanitize_output(result)
        except SyntaxError as e:
            msg = self.get_syntax_error(e)
        if not msg:
            func = env["func"]
            result = None
            try:
                with contextlib.redirect_stdout(stdout):
                    result = await func()
            except Exception as e:
                printed = "{}{}".format(stdout.getvalue(), traceback.format_exc())
            else:
                printed = stdout.getvalue()
            if result is not None:
                msg = result
            if printed:
                msg = f"{printed}{result}"

        result = f"[Cluster #{self.bot.cluster_id}]: {msg}"
        payload = {"output": result, "command_id": command_id}
        await self.bot.redis.execute_command(
            "PUBLISH",
            settings.redis_db,
            json.dumps(payload),
        )

    @classmethod
    def get_syntax_error(cls, e):
        """Format a syntax error to send to the user.

        Returns a string representation of the error formatted as a codeblock.
        """
        if e.text is None:
            return "{0.__class__.__name__}: {0}".format(e)
        return "{0.text}\n{1:>{0.offset}}\n{2}: {0}".format(e, "^", type(e).__name__)
        
    
    @staticmethod
    def get_pages(msg: str):
        """Pagify the given message for output to the user."""
        return pagify(msg, delims=["\n", " "], priority=True, shorten_by=10)

    async def handler(
        self,
        action: str,
        expected_count: int,
        args: dict = {},
        _timeout: int = 2,
        scope: str = "bot",
    ):  # TODO: think of a better name
        """
        coro
        A function that sends an event and catches all incoming events. Can be used anywhere.

        ex:
            await ctx.send(await bot.cogs["Sharding"].handler("evaluate", 4, {"code": '", ".join([f"{a} - {round(b*1000,2)} ms" for a,b in self.bot.latencies])'}))

        action: str          Must be the function's name you need to call
        expected_count: int  Minimal amount of data to send back. Can be more than the given and less on timeout
        args: dict           A dictionary for the action function's args to pass
        _timeout: int=2      Maximal amount of time waiting for incoming responses
        scope: str="bot"     Can be either launcher or bot. Used to differentiate them
        """
        # Preparation
        command_id = f"{uuid4()}"  # str conversion
        if expected_count > 0:
            self._messages[command_id] = [
                asyncio.Future() for _ in range(expected_count)
            ]  # must create it (see the router)
            results = []

        # Sending
        payload = {"scope": scope, "action": action, "command_id": command_id}
        if args:
            payload["args"] = args

        await self.bot.redis.execute_command(
            "PUBLISH",
            settings.redis_db,
            json.dumps(payload),
        )

        if expected_count > 0:
            # Message collector
            try:
                done, _ = await asyncio.wait(self._messages[command_id], timeout=_timeout)
                for fut in done:
                    results.append(fut.result())
            except asyncio.TimeoutError:
                pass
            del self._messages[command_id]
            return results

    @commands.command()
    @commands.is_owner()
    async def ceval(self, ctx, *, code: str):
        """
        Evaluate a piece of code
        """

        results = await self.handler("evaluate", self.bot.cluster_count, {"code": code})
        msg = ""
        for result in results:
            msg += f"{result}\n"
        if not msg:
            msg = "No result"
        pages = pagify(msg, delims=["["], priority=True, shorten_by=10)
        await send_interactive(ctx, pages)

    @commands.command()
    @commands.is_owner()
    async def clustereval(self, ctx, cluster: int, *, code: str):
        """
        Evaluate a piece of code on a specific cluster
        """
        results = await self.handler(
            "evaluate", 1, {"code": code, "cluster": cluster}
        )
        msg = ""
        for result in results:
            msg += f"{result}\n"
        if not msg:
            msg = "No result"
        pages = pagify(msg, delims=["["], priority=True, shorten_by=10)
        await send_interactive(ctx, pages)

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, package: str):
        """
        Reload an extension
        """
        results = await self.handler(
            "reload_packages", self.bot.cluster_count, {"package": package}
        )
        msg = ""
        for result in results:
            msg += f"{result}\n"
        if not msg:
            msg = "No result"
        msg = f"```py\n{msg}```"
        await ctx.send(msg)

    async def reload_packages(self, package: str, command_id: str):
        package = "ballsdex.packages." + package
        try:
            try:
                await self.bot.reload_extension(package)
            except commands.ExtensionNotLoaded:
                await self.bot.load_extension(package)
        except commands.ExtensionNotFound:
            result = f"Extension {package} not found."
        except Exception:
            result = f"Failed to reload extension {package}"
            log.error(f"Failed to reload extension {package}", exc_info=True)
        else:
            result = f"Reloaded extension {package}"

        payload = {"output": result, "command_id": command_id}
        await self.bot.redis.execute_command(
            "PUBLISH",
            settings.redis_db,
            json.dumps(payload),
        )

    @commands.command()
    @commands.is_owner()
    async def reloadcache(self, ctx: commands.Context):
        """
        Reload the cache of database models.

        This is needed each time the database is updated, otherwise changes won't reflect until
        next start.
        """
        await self.handler("reload_cache", 0, {})
        await ctx.message.add_reaction("✅")

    async def reload_cache(self, command_id: str):
        await self.bot.load_cache()
        payload = {"output": "Cache reloaded.", "command_id": command_id}
        await self.bot.redis.execute_command(
            "PUBLISH",
            settings.redis_db,
            json.dumps(payload),
        )

    async def blacklist_update(self, command_id: str):
        self.bot.blacklist.clear()
        for blacklisted_id in await BlacklistedID.all().only("discord_id"):
            self.bot.blacklist.add(blacklisted_id.discord_id)
        self.bot.blacklist_guild.clear()
        for blacklisted_id in await BlacklistedGuild.all().only("discord_id"):
            self.bot.blacklist_guild.add(blacklisted_id.discord_id)
        payload = {"output": "Blacklist updated.", "command_id": command_id}
        await self.bot.redis.execute_command(
            "PUBLISH",
            settings.redis_db,
            json.dumps(payload),
        )

    async def guilds(self, user_id, command_id: str):
        user = await self.bot.fetch_user(user_id)
        guilds = [x for x in self.bot.guilds if x.owner_id == user.id]
        guilds = [[x.id, x.name, x.member_count] for x in guilds]

        payload = {"output": guilds, "command_id": command_id}
        await self.bot.redis.execute_command(
            "PUBLISH",
            settings.redis_db,
            json.dumps(payload),
        )
