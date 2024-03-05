import asyncio
import json
from logging import getLogger
from uuid import uuid4

import discord
from discord.ext import commands

from ballsdex.core.models import BlacklistedGuild, BlacklistedID
from ballsdex.settings import settings

log = getLogger("ballsdex.packages.ipc.cog")


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

        try:
            compiled = cog.async_compile(code, "<string>", "eval")
            result = await cog.maybe_await(eval(compiled, env))
            # result = cog.sanitize_output(result)
        except SyntaxError as e:
            result = "SyntaxError: " + str(e)
        except Exception as e:
            result = "Error: " + str(e)

        result = f"[Cluster #{self.bot.cluster_id}]: {result}"
        payload = {"output": result, "command_id": command_id}
        await self.bot.redis.execute_command(
            "PUBLISH",
            settings.redis_db,
            json.dumps(payload),
        )

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
        msg = f"```py\n{msg}```"
        await ctx.send(msg)

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
