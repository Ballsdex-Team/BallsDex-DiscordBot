import logging
import random
import sys
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from discord import app_commands
from discord.app_commands.translator import TranslationContext, TranslationContextLocation, locale_str
from discord.ext import commands

from ballsdex import __version__ as ballsdex_version
from ballsdex.core.translation import t
from ballsdex.core.utils.django import row_count_estimate
from ballsdex.core.utils.formatting import pagify
from bd_models.models import Ball
from bd_models.models import balls as countryballs
from settings.models import settings

from .license import LicenseInfo, extra_apps_dist

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.info")


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
        balls: list[Ball] = random.choices(
            [x for x in countryballs.values() if x.enabled], k=min(10, len(countryballs))
        )
        emotes: list[discord.Emoji] = []

        for ball in balls:
            if emoji := self.bot.get_emoji(ball.emoji_id):
                emotes.append(emoji)

        return emotes

    @app_commands.command()
    async def about(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Get information about this bot.
        """
        embed = discord.Embed(
            title=t("{bot_name} Discord bot").format(bot_name=settings.bot_name), color=discord.Colour.blurple()
        )

        try:
            balls = await self._get_10_balls_emojis()
        except Exception:
            log.error("Failed to fetch 10 balls emotes", exc_info=True)
            balls = []

        balls_count = len([x for x in countryballs.values() if x.enabled])
        players_count = await sync_to_async(row_count_estimate)("player")
        balls_instances_count = await sync_to_async(row_count_estimate)("ballinstance")

        if self.bot.startup_time is not None:
            uptime_duration = datetime.now() - self.bot.startup_time
            formatted_uptime = str(uptime_duration).split(".")[0]
        else:
            formatted_uptime = "N/A"

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

        bot_info = await self.bot.application_info()
        if bot_info.team:
            dex_credits = t(
                "This instance is owned by the team {owner}.\nAn instance of [Ballsdex]({repo}) by El "
                "Laggron and maintained by the Ballsdex Team and community of "
                "[contributors]({repo}/graphs/contributors)."
            ).format(owner=bot_info.team.name, repo=settings.repository)
        else:
            dex_credits = t(
                "This instance is owned by {owner}.\nAn instance of [Ballsdex]({repo}) by El "
                "Laggron and maintained by the Ballsdex Team and community of "
                "[contributors]({repo}/graphs/contributors)."
            ).format(owner=bot_info.owner, repo=settings.repository)
        embed.description = t(
            "{balls_emojis}\n"
            "{about_description}\n"
            "*Running version **[{version}]({repo}/releases)***\n"
            "The bot has been online for **{uptime}**.\n\n"
            "**{balls_count}** {collectibles} to collect\n"
            "**{players_count}** players that caught **{instances_count}** {collectibles}\n"
            "**{guilds_count}** servers playing\n\n"
            "{dex_credits}\n\n"
            "Consider supporting El Laggron on [Patreon](https://patreon.com/retke) :heart:\n\n"
            "[Discord server]({invite}) • [Invite me]({invite_link}) • "
            "[Source code and issues]({repo})\n"
            "[Terms of Service]({tos}) • [Privacy policy]({privacy})"
        ).format(
            balls_emojis=" ".join(str(x) for x in balls),
            about_description=settings.about_description,
            version=ballsdex_version,
            repo=settings.repository,
            uptime=formatted_uptime,
            balls_count=f"{balls_count:,}",
            collectibles=settings.plural_collectible_name,
            players_count=f"{players_count:,}",
            instances_count=f"{balls_instances_count:,}",
            guilds_count=f"{len(self.bot.guilds):,}",
            dex_credits=dex_credits,
            invite=settings.discord_invite,
            invite_link=invite_link,
            tos=settings.terms_of_service,
            privacy=settings.privacy_policy,
        )

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        v = sys.version_info
        python = "Python"
        if v.major == 3 and v.minor == 14 and random.random() < 0.1:
            python = "πthon"
        embed.set_footer(text=f"{python} {v.major}.{v.minor}.{v.micro} • discord.py {discord.__version__}")

        view = LicenseInfo()
        if not extra_apps_dist:
            view.remove_item(view.children[-1])
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command()
    async def help(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Show the list of commands from the bot.
        """
        assert self.bot.user
        embed = discord.Embed(
            title=t("{bot_name} Discord bot - help menu").format(bot_name=settings.bot_name),
            color=discord.Colour.blurple(),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        for cog in self.bot.cogs.values():
            if cog.qualified_name == "Admin":
                continue
            content = ""
            for app_command in cog.walk_app_commands():
                translated = await self.bot.tree.translator.translate(  # type: ignore
                    locale_str(app_command.description),
                    interaction.locale,
                    TranslationContext(TranslationContextLocation.other, None),
                )
                content += f"{mention_app_command(app_command)}: {translated}\n"
            if not content:
                continue
            pages = pagify(content, page_length=1024)
            for i, page in enumerate(pages):
                embed.add_field(name=cog.qualified_name if i == 0 else "\u200b", value=page, inline=False)

        await interaction.response.send_message(embed=embed)
