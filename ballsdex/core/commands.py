from collections import defaultdict
import logging

from typing import TYPE_CHECKING, Literal
from ballsdex.core.dev import pagify
from ballsdex.core.models import Ball
from discord.ext import commands

log = logging.getLogger("ballsdex.core.commands")

if TYPE_CHECKING:
    from .bot import BallsDexBot


class Core(commands.Cog):
    """
    Core commands of BallsDex bot
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """
        Ping!
        """
        await ctx.send("Pong")

    @commands.command()
    @commands.is_owner()
    async def reloadtree(self, ctx: commands.Context):
        """
        Sync the application commands with Discord
        """
        await self.bot.tree.sync()
        await ctx.send("Application commands tree reloaded.")

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, package: str):
        """
        Reload an extension
        """
        package = "ballsdex.packages." + package
        try:
            try:
                await self.bot.reload_extension(package)
            except commands.ExtensionNotLoaded:
                await self.bot.load_extension(package)
        except commands.ExtensionNotFound:
            await ctx.send("Extension not found")
        except Exception:
            await ctx.send("Failed to reload extension.")
            log.error(f"Failed to reload extension {package}", exc_info=True)
        else:
            await ctx.send("Extension reloaded.")

    @commands.command()
    @commands.is_owner()
    async def reloadcache(self, ctx: commands.Context):
        """
        Reload the cache of database models.

        This is needed each time the database is updated, otherwise changes won't reflect until
        next start.
        """
        await self.bot.load_cache()
        await ctx.message.add_reaction("✅")

    @commands.command()
    @commands.is_owner()
    async def ballrarity(self, ctx: commands.Context, *, rarity: Literal["continuous", "grouped"]):
        """
        Return a list of countryballs in rarity order.

        Parameters
        ----------
        type: continuous  | rarity
            The type of list you want to get. 
            Continous will list 1-X, rarity will list by grouping those with the same rarity.
        """
        if rarity not in ("continuous ", "grouped"):
            await ctx.send("Invalid rarity type. Must be grouped or continous.")
            return
        balls = await Ball.all().order_by("rarity")
        if not balls:
            await ctx.send("No balls found.")
            return
        i = 1
        msg = ""
        if rarity == "continuous ":
            for ball in balls:
                msg += f"{i}. {ball.country}\n"
                i += 1
        else:
            chunked = defaultdict(list)
            for ball in balls:
                chunked[ball.rarity].append(ball)
            for chunk in chunked.values():
                for ball in chunk:
                    msg += f"{i}. {ball.country}\n"
                i += len(chunk)
        for page in pagify(msg):
            await ctx.send(page)
