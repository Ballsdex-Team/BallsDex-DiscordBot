"""
Miner Wheel - Interactive Discord spinning wheel for BallsDx miners
"""

import discord
from discord.ext import commands
from .wheel import MinerWheel
from .views import WheelView
from .utils import get_all_miners
from discord import app_commands

# Hardcoded admin guild and staff role IDs
ADMIN_GUILD_ID = "1405512069465374730"
STAFF_ROLE_ID = "1405512666901909635"

class MinerWheelCog(commands.Cog):
    """Miner Wheel commands for BallsDx"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="wheel")
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def create_wheel(self, ctx):
        """Create an interactive miner spinning wheel"""
        try:
            wheel = await MinerWheel.create_from_database()
            if wheel.is_empty():
                await ctx.send("❌ No miners found in the database!")
                return

            await wheel.send_to_channel(ctx.channel)

        except Exception as e:
            await ctx.send(f"❌ Error creating wheel: {str(e)}")

    @commands.command(name="rarewheel")
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def create_rare_wheel(self, ctx, max_rarity: float = 15.0):
        """Create a wheel with only rare miners (rarity <= max_rarity)"""
        try:
            from ballsdex.core.models import Ball
            rare_miners = [ball for ball in await Ball.filter(enabled=True, rarity__lte=max_rarity) if ball.country]

            if not rare_miners:
                await ctx.send(f"❌ No miners found with rarity ≤ {max_rarity}!")
                return

            wheel = MinerWheel(rare_miners)
            await wheel.send_to_channel(ctx.channel)

        except Exception as e:
            await ctx.send(f"❌ Error creating rare wheel: {str(e)}")

    @app_commands.command(name="wheel", description="Create an interactive miner spinning wheel")
    @app_commands.guild_only()
    async def wheel_slash(self, interaction: discord.Interaction):
        """Create an interactive miner spinning wheel (admin guild only, staff only)"""
        # Check if command is used in the allowed guild
        if str(interaction.guild_id) != ADMIN_GUILD_ID:
            await interaction.response.send_message("❌ This command can only be used in the admin guild.", ephemeral=True)
            return

        # Check if user has the staff role
        member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
        if not member or not any(str(role.id) == STAFF_ROLE_ID for role in member.roles):
            await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            return

        try:
            wheel = await MinerWheel.create_from_database()
            if wheel.is_empty():
                await interaction.response.send_message("❌ No miners found in the database!", ephemeral=True)
                return

            await wheel.send_to_channel(interaction.channel)
            await interaction.response.send_message("Wheel sent!", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Error creating wheel: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MinerWheelCog(bot))