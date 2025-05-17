from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, button
from tortoise.exceptions import DoesNotExist
from tortoise.functions import Count

from ballsdex.core.models import BallInstance, Player
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

@app_commands.guilds(*settings.admin_guild_ids)
@app_commands.default_permissions(administrator=True)
class PowerLevel(commands.GroupCog, group_name="powerlevel"):
    """
    Brawler power level manager commands..
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def upgrade(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        brawler_id: str
    ):
        """
        Upgrade a brawler's power level once.
        
        Parameters
        ----------
        brawler_id: str
            The ID of the brawler you want to upgrade its power level.
        """
        channel = self.bot.get_channel(interaction.channel.id)
        try:
            brawlerIdConverted = int(brawler_id, 16)
        except ValueError:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True
            )
            return
        try:
            brawler = await BallInstance.get(id=brawlerIdConverted)
        except DoesNotExist:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return

        if brawler.health_bonus == 100 and brawler.attack_bonus == 100:
            await interaction.response.send_message(
                "This brawler is already at maximum level!", ephemeral=True
            )
        else:
            brawler.health_bonus += 10
            brawler.attack_bonus += 10
            await brawler.save()
            await interaction.response.send_message("Brawler successfully upgraded.", ephemeral=True)
            owner = await Player.get(id=brawler.player_id)
            data, file = await brawler.prepare_for_message(interaction)
            await channel.send(f"<@{owner.discord_id}>, your Brawler has been upgraded. \n\n{data}", file=file)
            
    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def downgrade(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        brawler_id: str
    ):
        """
        Downgrade a brawler's power level once.
        
        Parameters
        ----------
        brawler_id: str
            The ID of the brawler you want to downgrade its power level.
        """
        try:
            brawlerIdConverted = int(brawler_id, 16)
        except ValueError:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True
            )
            return
        try:
            brawler = await BallInstance.get(id=brawlerIdConverted)
        except DoesNotExist:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return
        if brawler.health_bonus <= 0 and brawler.attack_bonus <= 0:
            await interaction.response.send_message(
           "You can't downgrade a Power Level 1 brawler.", ephemeral=True
           )
        else:
            brawler.health_bonus -= 10
            brawler.attack_bonus -= 10
            await brawler.save()
            await interaction.response.send_message(
           "Brawler successfully downgraded.", ephemeral=True
           )
    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def reset(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        brawler_id: str
    ):
        """
        Reset a brawler's power level.
        
        Parameters
        ----------
        brawler_id: str
            The ID of the brawler you want to reset its power level.
        """
        try:
            brawlerIdConverted = int(brawler_id, 16)
        except ValueError:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave is not valid.", ephemeral=True
            )
            return
        try:
            brawler = await BallInstance.get(id=brawlerIdConverted)
        except DoesNotExist:
            await interaction.response.send_message(
                f"The {settings.collectible_name} ID you gave does not exist.", ephemeral=True
            )
            return
        if brawler.health_bonus == 0 and brawler.attack_bonus == 0:
         await interaction.response.send_message(
                f"This brawler is already resetted!", ephemeral=True
            )
        else:
         brawler.health_bonus = 0
         brawler.attack_bonus = 0
         await brawler.save()
         await interaction.response.send_message(
                f"Brawler successfully resetted.", ephemeral=True
            )
