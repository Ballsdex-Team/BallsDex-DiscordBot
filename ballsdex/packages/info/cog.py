import discord
import random
import sys
import logging

from typing import TYPE_CHECKING
from tortoise.transactions import in_transaction

from discord import app_commands
from discord.ext import commands

from ballsdex import __version__ as ballsdex_version
from ballsdex.core.models import Ball, BallInstance, Player

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.info")

GITHUB_LINK = "https://github.com/laggron42/BallsDex-DiscordBot"
DISCORD_SERVER_LINK = "https://discord.gg/w9HJU5nGJT"


class Info(commands.Cog):
    """
    Simple info commands.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    async def _get_10_balls_emojis(self, balls_count: int) -> list[discord.Emoji]:
        # ball_count is reused
        balls_pks = random.choices(list(range(1, balls_count + 1)), k=max(balls_count, 10))

        balls: list[Ball] = []
        emotes: list[discord.Emoji] = []

        async with in_transaction():
            for pk in balls_pks:
                balls.append(await Ball.get(pk=pk).only("emoji_id"))

        for ball in balls:
            if emoji := self.bot.get_emoji(ball.emoji_id):
                emotes.append(emoji)

        return emotes

    @app_commands.command()
    async def about(self, interaction: discord.Interaction):
        """
        Get information about this bot.
        """
        embed = discord.Embed(title="BallsDex Discord bot", color=discord.Colour.blurple())

        balls_count = await Ball.all().count()
        try:
            balls = await self._get_10_balls_emojis(balls_count)
        except Exception:
            log.error("Failed to fetch 10 balls emotes", exc_info=True)
            balls = []

        # TODO: find a better solution to get the count of all rows
        # possible track: https://stackoverflow.com/a/7945274
        players_count = await Player.all().count()
        balls_instances_count = await BallInstance.all().count()

        assert self.bot.user
        assert self.bot.application
        try:
            assert self.bot.application.install_params
        except AssertionError:
            invite_link = discord.utils.oauth_url(
                self.bot.application.id,
                permissions=discord.Permissions(
                    manage_webhooks=True,
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True,
                    embed_links=True,
                    attach_files=True,
                    use_external_emojis=True,
                    add_reactions=True,
                ),
                scopes=("bot", "applications.commands"),
            )
        else:
            invite_link = discord.utils.oauth_url(
                self.bot.application.id,
                permissions=self.bot.application.install_params.permissions,
                scopes=self.bot.application.install_params.scopes,
            )
        embed.description = (
            f"{' '.join(str(x) for x in balls)}\n"
            "Collect countryballs on Discord, exchange them and battle with friends!\n"
            f"*Running version **[{ballsdex_version}]({GITHUB_LINK}/releases)***\n\n"
            f"**{balls_count}** countryballs to collect\n"
            f"**{players_count}** players that caught **{balls_instances_count}** countryballs\n"
            f"**{len(self.bot.guilds)}** servers playing\n\n"
            f"[Discord server]({DISCORD_SERVER_LINK}) • [Invite me]({invite_link}) • "
            f"[Source code and issues]({GITHUB_LINK})"
        )

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        v = sys.version_info
        embed.set_footer(
            text=f"Python {v.major}.{v.minor}.{v.micro} • discord.py {discord.__version__}"
        )

        await interaction.response.send_message(embed=embed)
