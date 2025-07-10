from typing import TYPE_CHECKING
import logging
import discord
from discord import app_commands
from discord.ext import commands
from ballsdex.packages.cardmaker.cardmaker import merge_images
from ballsdex.packages.cardmaker.cardgenerator import CardGenerator
from ballsdex.settings import settings
from ballsdex.core.utils.transformers import BallTransform, SpecialTransform
from ballsdex.core.models import Ball, Special

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.cardmaker")

class CardMaker(commands.Cog):
    """
    Card Maker commands.
    """
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command(name="makecard", description="Create a card by merging a background and an image.")
    @app_commands.guilds(*settings.admin_guild_ids)
    @app_commands.checks.has_any_role(*settings.root_role_ids, 1357857303222816859)
    async def makecard(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        background: discord.Attachment,
        image: discord.Attachment
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            # Validate content types
            if not background.content_type.startswith("image") or not image.content_type.startswith("image"):
                await interaction.followup.send("Both attachments must be image files (e.g., PNG, JPG).", ephemeral=True)
                return

            # Optional: File size limits (Discord caps at 25 MB normally)
            if background.size > 10 * 1024 * 1024 or image.size > 10 * 1024 * 1024:
                await interaction.followup.send("Each image must be under 10 MB.", ephemeral=True)
                return

            # Merge and send
            result_image = await merge_images(background, image)
            file = discord.File(result_image, filename="card.png")

            await interaction.followup.send(content="Here's your generated card:", file=file, ephemeral=False)

        except Exception as e:
            log.error(f"Error in makecard: {e}")
            await interaction.followup.send("Something went wrong while processing the images.", ephemeral=True)
    
    @app_commands.command(name="buildcard", description="Build a card of an existing brawler/skin.")
    @app_commands.describe(brawler="The brawler/skin to generate card of")
    @app_commands.describe(special="The special to apply)
    @app_commands.guilds(*settings.admin_guild_ids)
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def buildcard(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        brawler: BallTransform,
        special: SpecialTransform | None = None
    ):
        generator = CardGenerator(brawler)
        generator.special = special
        image, _ = generator.generate_image()
        try:
            await interaction.response.send_message(file=discord.File(image, "card.png"))
        except Exception as e:
            log.error("Something went wrong.", exc_info=e)
        
