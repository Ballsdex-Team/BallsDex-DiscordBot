import discord
import sys
import logging

from typing import TYPE_CHECKING
from tortoise.contrib.postgres.functions import Random

from discord import app_commands
from discord.ext import commands

from ballsdex import __version__ as ballsdex_version
from ballsdex.core.models import Ball, BallInstance, Player

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.info")

GITHUB_LINK = "https://github.com/laggron42/BallsDex-DiscordBot"
DISCORD_SERVER_LINK = "https://discord.gg/Qn2Rkdkxwc"
TERMS_OF_SERVICE = "https://gist.github.com/laggron42/52ae099c55c6ee1320a260b0a3ecac4e"
PRIVACY_POLICY = "https://gist.github.com/laggron42/1eaa122013120cdfcc6d27f9485fe0bf"


def mention_app_command(app_command: app_commands.Command | app_commands.Group) -> str:
    if "mention" in app_command.extras:
        return app_command.extras["mention"]
    else:
        if isinstance(app_command, app_commands.ContextMenu):
            return f"`{app_command.name}`"
        else:
            return f"`/{app_command.name}`"


class Info(commands.Cog):
    """
    Simple info commands.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    async def _get_10_balls_emojis(self) -> list[discord.Emoji]:
        balls: list[Ball] = (
            await Ball.annotate(order=Random()).order_by("order").limit(10).only("emoji_id")
        )
        emotes: list[discord.Emoji] = []

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

        try:
            balls = await self._get_10_balls_emojis()
        except Exception:
            log.error("Failed to fetch 10 balls emotes", exc_info=True)
            balls = []

        # TODO: find a better solution to get the count of all rows
        # possible track: https://stackoverflow.com/a/7945274
        balls_count = await Ball.all().count()
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
            "Coded by **El Laggron**, original concept from **Speedroide**.\n"
            "All pictures are used with permission from [Polandball Wiki]"
            "(https://www.polandballwiki.com/wiki/Polandball_Wiki) and/or "
            "from the respective artists.\n"
            "**The complete list of artworks credits can be found [here]("
            "https://docs.google.com/document/d/1XqPysHQCDgifBkM_FHwgoDyy37bFz5GS9ItYpg-IxYo/edit)"
            "**\n\n"
            f"[Discord server]({DISCORD_SERVER_LINK}) • [Invite me]({invite_link}) • "
            f"[Source code and issues]({GITHUB_LINK}) • [Terms of Service]({TERMS_OF_SERVICE}) • "
            f"[Privacy policy]({PRIVACY_POLICY})"
        )

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        v = sys.version_info
        embed.set_footer(
            text=f"Python {v.major}.{v.minor}.{v.micro} • discord.py {discord.__version__}"
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command()
    async def help(self, interaction: discord.Interaction):
        """
        Show the list of commands from the bot.
        """
        assert self.bot.user
        embed = discord.Embed(
            title="BallsDex Discord bot - help menu", color=discord.Colour.blurple()
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        for cog in self.bot.cogs.values():
            content = ""
            for app_command in cog.walk_app_commands():
                content += f"{mention_app_command(app_command)}: {app_command.description}\n"
            if not content:
                continue
            embed.add_field(name=cog.qualified_name, value=content, inline=False)

        await interaction.response.send_message(embed=embed)
