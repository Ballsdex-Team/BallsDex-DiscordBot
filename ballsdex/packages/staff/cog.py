import io
from typing import TYPE_CHECKING
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands
from ballsdex.core.utils.logging import log_action
from tortoise.exceptions import BaseORMException, DoesNotExist
from ballsdex.packages.admin.balls import save_file
from ballsdex.packages.staff.cardmaker import merge_images
from ballsdex.packages.staff.cardgenerator import CardGenerator
from ballsdex.settings import settings
from ballsdex.core.utils.transformers import BallTransform, SpecialTransform
from ballsdex.core.models import Ball, Special

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.staff")

@app_commands.guilds(*settings.admin_guild_ids)
class Staff(commands.GroupCog, group_name="staff"):
    """
    Staff commands.
    """
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command(name="cardart", description="Create a card art by merging a background and an image.")
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
            log.error(f"Error in makecardart: {e}")
            await interaction.followup.send("Something went wrong while processing the images.", ephemeral=True)
    
    @app_commands.command(name="viewcard", description="View a card of an existing brawler/skin.")
    @app_commands.describe(brawler="The brawler/skin to view card of")
    @app_commands.describe(special="The special to apply")
    @app_commands.checks.has_any_role(*settings.root_role_ids, 1357857303222816859)
    async def viewcard(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        brawler: BallTransform,
        special: SpecialTransform | None = None
    ):
        generator = CardGenerator(brawler, special)
        generator.special = special
        image, _ = generator.generate_image()

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

    # Send it as a Discord file
        discord_file = discord.File(fp=buffer, filename="card.png")
        try:
            await interaction.response.send_message(file=discord_file, ephemeral=True)
        except Exception as e:
            log.error("Something went wrong.", exc_info=e)
            await interaction.response.send_message("Something went wrong.", ephemeral=True)

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, 1357857303222816859)
    @app_commands.choices(type=[
        app_commands.Choice(name="Wild Art", value="wild"),
        app_commands.Choice(name="Card Art", value="card")
        ])
    async def uploadcard(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        brawler: BallTransform,
        image: discord.Attachment,
        type: app_commands.Choice[str]
        ):
        """
        Update an image asset for a brawler/skin.

        Parameters
        ----------
        brawler: Ball
           The brawler/skin to update its asset
        image: discord.Attachment
            The image to use as the new asset
        type: app_commands.Choice[str]
            Type of the asset (Wild/Card).
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            card_path = await save_file(image)
        except Exception as e:
            await interaction.followup.send("Failed to upload the asset.", ephemeral=True)
            log.exception("Failed to upload the asset", exc_info=True)
            return

        try:
            if type.value.lower() == "wild":
                brawler.wild_card = "/" + str(card_path)
            elif type.value.lower() == "card":
                brawler.collection_card = "/" + str(card_path)
            else:
                await interaction.followup.send("Invalid asset type provided.", ephemeral=True)
                return

            await brawler.save()
            await interaction.followup.send("Asset upload successful.", ephemeral=True)
            await log_action(f"{interaction.user} updated {brawler.country}'s card asset.", interaction.client)
            await interaction.client.load_cache()
        except BaseORMException as e:
            await interaction.followup.send("Failed to update the brawler.", ephemeral=True)
            log.exception("Failed to update the brawler", exc_info=True)
        
    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, 1357857303222816859)
    @app_commands.choices(type=[
        app_commands.Choice(name="Title", value="title"),
        app_commands.Choice(name="Text", value="text"),
        app_commands.Choice(name="Credits", value="credits")
        ])
    async def uploadtext(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        brawler: BallTransform,
        text: str,
        type: app_commands.Choice[str]
        ):
        """
        Update a text asset for a brawler/skin.

        Parameters
        ----------
        brawler: Ball
            The brawler/skin to update its asset.
        text: str
            The text to use as the new asset.
        type: app_commands.Choice[str]
            Type of the asset (Title/Text/Credits).
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            if type.value.lower() == "title":
                brawler.capacity_name = text
            elif type.value.lower() == "text":
                brawler.capacity_description = text
            elif type.value.lower() == "credits":
                brawler.credits = text
            else:
                await interaction.followup.send("Invalid asset type provided.", ephemeral=True)
                return

            await brawler.save()
            await interaction.followup.send("Text update successful.", ephemeral=True)
            await log_action(f"{interaction.user} updated {brawler.country}'s text asset.", interaction.client)
            await interaction.client.load_cache()
        except BaseORMException as e:
            await interaction.followup.send("Failed to update the brawler.", ephemeral=True)
            log.exception("Failed to update the brawler", exc_info=True)
