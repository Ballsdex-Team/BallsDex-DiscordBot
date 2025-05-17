import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands
from ballsdex.settings import settings
from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import Ball
from ballsdex.core.utils.logging import log_action
from ballsdex.core.utils.transformers import BallTransform
from tortoise.exceptions import BaseORMException, DoesNotExist
from ballsdex.packages.admin.balls import save_file

log = logging.getLogger("ballsdex.packages.assetuploader.cog")
  
@app_commands.guilds(*settings.admin_guild_ids)
class AssetUploader(commands.GroupCog, group_name="upload"):
    """Asset uploader commands."""
    
    @app_commands.command()
    @app_commands.checks.has_any_role(1357857303222816859, 1295410565157490742, 1295410565157490741)
    @app_commands.choices(type=[
        app_commands.Choice(name="Wild Art", value="wild"),
        app_commands.Choice(name="Card Art", value="card")
        ])
    async def card(
        self,
        interaction: discord.Interaction[BallsDexBot],
        brawler: BallTransform,
        image: discord.Attachment,
        type: app_commands.Choice[str]
        ):
        """
        Update an image asset for a brawler.

        Parameters
        ----------
        brawler: Ball
           The brawler to update its asset
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
    @app_commands.checks.has_any_role(1357857303222816859, 1295410565157490742, 1295410565157490741)
    @app_commands.choices(type=[
        app_commands.Choice(name="Title", value="title"),
        app_commands.Choice(name="Text", value="text"),
        app_commands.Choice(name="Credits", value="credits")
        ])
    async def text(
        self,
        interaction: discord.Interaction[BallsDexBot],
        brawler: BallTransform,
        text: str,
        type: app_commands.Choice[str]
        ):
        """
        Update a text asset for a brawler.

        Parameters
        ----------
        brawler: Ball
            The brawler to update its asset.
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
