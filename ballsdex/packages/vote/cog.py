from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button

from ballsdex.core.discord import View
from bd_models.models import VoteInteraction
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class VoteView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(style=discord.ButtonStyle.link, label="Vote on Top.gg", url=settings.vote_url))


class Vote(commands.Cog):
    """
    Vote for the bot.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    async def vote(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Support the bot by voting for it!
        """
        embed = discord.Embed(
            title=f"🗳️ Support {settings.bot_name}!",
            description=(
                "Don't hesitate to support us by voting and leaving a comment!\n\n"
                f"[Click here to vote]({settings.vote_url})"
            ),
            color=discord.Colour.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=VoteView(), ephemeral=True)

        assert interaction.application_id is not None
        await VoteInteraction.objects.aupdate_or_create(
            discord_id=interaction.user.id,
            defaults={"application_id": interaction.application_id, "token": interaction.token},
        )
