import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from tortoise import Tortoise

from ballsdex.core.dev import pagify, send_interactive
from ballsdex.core.models import Ball
from ballsdex.settings import read_settings, settings

log = logging.getLogger("ballsdex.core.commands")

if TYPE_CHECKING:
    from .bot import BallsDexBot


class SimpleCheckView(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.value = False

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"]) -> bool:
        return interaction.user == self.ctx.author

    @discord.ui.button(
        style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}"
    )
    async def confirm_button(
        self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button
    ):
        await interaction.response.edit_message(content="Starting upload...", view=None)
        self.value = True
        self.stop()


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

    async def reload_package(self, package: str, *, with_prefix=False):
        try:
            try:
                await self.bot.reload_extension(package)
            except commands.ExtensionNotLoaded:
                await self.bot.load_extension(package)
        except commands.ExtensionNotFound:
            if not with_prefix:
                return await self.reload_package("ballsdex.packages." + package, with_prefix=True)
            raise

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, package: str):
        """
        Reload an extension
        """
        try:
            await self.reload_package(package)
        except commands.ExtensionNotFound:
            await ctx.send("Extension not found.")
        except Exception:
            await ctx.send("Failed to reload extension.")
            log.error(f"Failed to reload extension {package}", exc_info=True)
        else:
            await ctx.send("Extension reloaded.")

    @commands.command()
    @commands.is_owner()
    async def reloadconf(self, ctx: commands.Context):
        """
        Reload the config file
        """

        read_settings(Path("./config.yml"))
        await ctx.message.reply(
            "Config values have been updated. Some changes may require a restart."
        )

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
    async def analyzedb(self, ctx: commands.Context):
        """
        Analyze the database. This refreshes the counts displayed by the `/about` command.
        """
        connection = Tortoise.get_connection("default")
        t1 = time.time()
        await connection.execute_query("ANALYZE")
        t2 = time.time()
        await ctx.send(f"Analyzed database in {round((t2 - t1) * 1000)}ms.")

    @commands.command()
    @commands.is_owner()
    async def migrateemotes(self, ctx: commands.Context):
        """
        Upload all guild emojis used by the bot to application emojis.

        The emoji IDs of the countryballs are updated afterwards.
        This does not delete guild emojis after they were migrated.
        """
        balls = await Ball.all()
        if not balls:
            await ctx.send(f"No {settings.plural_collectible_name} found.")
            return

        application_emojis = set(x.name for x in await self.bot.fetch_application_emojis())

        not_found: set[Ball] = set()
        already_uploaded: list[tuple[Ball, discord.Emoji]] = []
        matching_name: list[tuple[Ball, discord.Emoji]] = []
        to_upload: list[tuple[Ball, discord.Emoji]] = []

        for ball in balls:
            emote = self.bot.get_emoji(ball.emoji_id)
            if not emote:
                not_found.add(ball)
            elif emote.is_application_owned():
                already_uploaded.append((ball, emote))
            elif emote.name in application_emojis:
                matching_name.append((ball, emote))
            else:
                to_upload.append((ball, emote))

        if len(already_uploaded) == len(balls):
            await ctx.send(
                f"All of your {settings.plural_collectible_name} already use application emojis."
            )
            return
        if len(to_upload) + len(application_emojis) > 2000:
            await ctx.send(
                f"{len(to_upload)} emojis are available for migration, but this would "
                f"result in {len(to_upload) + len(application_emojis)} total application emojis, "
                "which is above the limit (2000)."
            )
            return

        text = ""
        if not_found:
            not_found_str = ", ".join(f"{x.country} ({x.emoji_id})" for x in not_found)
            text += f"### {len(not_found)} emojis not found\n{not_found_str}\n"
        if matching_name:
            matching_name_str = ", ".join(f"{x[1]} {x[0].country}" for x in matching_name)
            text += (
                f"### {len(matching_name)} emojis with conflicting names\n{matching_name_str}\n"
            )
        if already_uploaded:
            already_uploaded_str = ", ".join(f"{x[1]} {x[0].country}" for x in already_uploaded)
            text += (
                f"### {len(already_uploaded)} emojis are already "
                f"application emojis\n{already_uploaded_str}\n"
            )
        if to_upload:
            to_upload_str = ", ".join(f"{x[1]} {x[0].country}" for x in to_upload)
            text += f"## {len(to_upload)} emojis to migrate\n{to_upload_str}"
        else:
            text += "\n**No emojis can be migrated at this time.**"

        pages = pagify(text, delims=["###", "\n\n", "\n"], priority=True)
        await send_interactive(ctx, pages, block=None)
        if not to_upload:
            return

        view = SimpleCheckView(ctx)
        msg = await ctx.send("Do you want to proceed?", view=view)
        if await view.wait() or view.value is False:
            return

        uploaded = 0

        async def update_message_loop():
            for i in range(5 * 12 * 10):  # timeout progress after 10 minutes
                print(f"Updating msg {uploaded}")
                await msg.edit(
                    content=f"Uploading emojis... ({uploaded}/{len(to_upload)})",
                    view=None,
                )
                await asyncio.sleep(5)

        task = self.bot.loop.create_task(update_message_loop())
        try:
            async with ctx.typing():
                for ball, emote in to_upload:
                    new_emote = await self.bot.create_application_emoji(
                        name=emote.name, image=await emote.read()
                    )
                    ball.emoji_id = new_emote.id
                    await ball.save()
                    uploaded += 1
                    print(f"Uploaded {ball}")
                    await asyncio.sleep(1)
                await self.bot.load_cache()
            task.cancel()
            assert self.bot.application
            await ctx.send(
                f"Successfully migrated {len(to_upload)} emojis. You can check them [here]("
                f"<https://discord.com/developers/applications/{self.bot.application.id}/emojis>)."
            )
        finally:
            task.cancel()
