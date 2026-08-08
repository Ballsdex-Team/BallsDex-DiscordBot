from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button

from ballsdex.core.discord import View

from ..models import VoteSettings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class VoteView(View):
    def __init__(self, vote_url: str):
        super().__init__(timeout=None)
        self.add_item(Button(style=discord.ButtonStyle.link, label="Vote on Top.gg", url=vote_url))


class Vote(commands.Cog):
    """
    Vote for the bot.
    """

    def __init__(self, bot: "BallsDexBot", vote_settings: VoteSettings):
        self.bot = bot
        self.vote_settings = vote_settings

    @app_commands.command()
    async def vote(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Support the bot by voting for it!
        """
        embed = discord.Embed(
            title="🗳️ Support us!",
            description=(
                "Don't hesitate to support us by voting and leaving a comment!\n\n"
                f"[Click here to vote]({self.vote_settings.vote_url})\n\n"
                "You'll receive a reward by DM once your vote is confirmed."
            ),
            color=discord.Colour.blurple(),
        )
        await interaction.response.send_message(
            embed=embed, view=VoteView(self.vote_settings.vote_url), ephemeral=True
        )
