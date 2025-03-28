# put this in commands (credit me somewhere pls)
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from ballsdex.packages.countryballs.models import BallInstance, Player
from ballsdex.packages.countryballs.views import ConfirmationView

class DropCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="drop", description="Drop one of your balls to be placed as a normal ball")
    @app_commands.describe(
        ball="The ID or name of the ball you want to drop"
    )
    async def drop(self, interaction: discord.Interaction, ball: str):
        # Get the player
        player, created = await Player.get_or_create(discord_id=interaction.user.id)
        
        # Find the ball instance
        try:
            # First try to get by ID
            ball_id = int(ball)
            ball_instance = await BallInstance.filter(
                id=ball_id, 
                player=player
            ).first()
        except ValueError:
            # If not an ID, try to get by name
            ball_instance = await BallInstance.filter(
                player=player,
                countryball__name__icontains=ball
            ).first()
        
        if not ball_instance:
            await interaction.response.send_message(
                "Ball not found in your collection. Please check the ID or name and try again.",
                ephemeral=True
            )
            return
        
        # Create confirmation view
        view = ConfirmationView(interaction.user)
        embed = discord.Embed(
            title="Drop Confirmation",
            description=f"Are you sure you want to drop your {ball_instance.countryball.name} (ID: {ball_instance.id})?\n\n"
                        f"**This will remove the ball from your collection and place it as a normal ball that anyone can catch.**",
            color=discord.Color.yellow()
        )
        embed.set_thumbnail(url=ball_instance.countryball.image_url)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()
        
        if view.value is True:
            # Remove the ball from the player's collection
            await ball_instance.delete()
            
            # Spawn the ball in the channel
            await self.bot.get_cog("CountryballSpawner").spawn_specific_ball(
                interaction.channel,
                ball_instance.countryball,
                special=ball_instance.special,
                atk_bonus=ball_instance.attack_bonus,
                hp_bonus=ball_instance.health_bonus
            )
            
            await interaction.edit_original_response(
                content=f"You dropped your {ball_instance.countryball.name}! It can now be caught by anyone.",
                embed=None,
                view=None
            )
        elif view.value is False:
            await interaction.edit_original_response(
                content="Drop cancelled.",
                embed=None,
                view=None
            )
        else:
            await interaction.edit_original_response(
                content="Drop timed out.",
                embed=None,
                view=None
            )

async def setup(bot):
    await bot.add_cog(DropCommand(bot))
