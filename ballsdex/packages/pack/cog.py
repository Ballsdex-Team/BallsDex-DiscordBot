import discord
import random
from datetime import datetime, timedelta
from discord.ext import commands
from discord import app_commands
from tortoise.models import Model
from tortoise import fields
from typing import Optional

from ballsdex.core.models import Ball, Player, BallInstance


class PacklyCooldown(Model):
    """Model for tracking daily pack cooldowns for users."""
    id = fields.IntField(pk=True)
    user_id = fields.BigIntField(unique=True)
    last_claim_time = fields.DatetimeField(auto_now_add=True)
    next_claim_time = fields.DatetimeField()

    class Meta:
        table = "packly_cooldowns"

    @classmethod
    async def can_claim(cls, user_id: int) -> bool:
        """Check if a user can claim their daily pack."""
        cooldown = await cls.filter(user_id=user_id).first()
        if not cooldown:
            return True
        now = datetime.now()
        return now >= cooldown.next_claim_time

    @classmethod
    async def update_cooldown(cls, user_id: int):
        """Update the cooldown for a user after claiming their daily pack."""
        now = datetime.now()
        next_claim = now + timedelta(days=1)
        cooldown, created = await cls.get_or_create(
            user_id=user_id,
            defaults={"next_claim_time": next_claim}
        )
        if not created:
            cooldown.last_claim_time = now
            cooldown.next_claim_time = next_claim
            await cooldown.save()


class WeeklyCooldown(Model):
    """Model for tracking weekly pack cooldowns for users."""
    id = fields.IntField(pk=True)
    user_id = fields.BigIntField(unique=True)
    last_claim_time = fields.DatetimeField(auto_now_add=True)
    next_claim_time = fields.DatetimeField()

    class Meta:
        table = "weekly_cooldowns"

    @classmethod
    async def can_claim(cls, user_id: int) -> bool:
        """Check if a user can claim their weekly pack."""
        cooldown = await cls.filter(user_id=user_id).first()
        if not cooldown:
            return True
        now = datetime.now()
        return now >= cooldown.next_claim_time

    @classmethod
    async def update_cooldown(cls, user_id: int):
        """Update the cooldown for a user after claiming their weekly pack."""
        now = datetime.now()
        next_claim = now + timedelta(days=7)
        cooldown, created = await cls.get_or_create(
            user_id=user_id,
            defaults={"next_claim_time": next_claim}
        )
        if not created:
            cooldown.last_claim_time = now
            cooldown.next_claim_time = next_claim
            await cooldown.save()


class Packly(commands.Cog):
    """Simple pack commands for BallsDex."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="packly")
    @app_commands.guild_only()
    async def packly_command(self, interaction: discord.Interaction):
        """Claim your daily pack! Get a random ball with a maximum rarity of 2.0."""
        # Get the player
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        
        # Check cooldown
        can_claim = await PacklyCooldown.can_claim(interaction.user.id)
        if not can_claim:
            await interaction.response.send_message("You have already claimed your daily pack. You can claim your next pack in 24 hours.")
            return
            
        # Find eligible balls (max rarity 2.0)
        eligible_balls = await Ball.filter(rarity__lte=2.0).all()
        if not eligible_balls:
            await interaction.response.send_message("There are no eligible balls available right now. Please try again later.")
            return
            
        # Pick a random ball
        ball = random.choice(eligible_balls)
        
        # Give the ball to the player
        ball_instance = await BallInstance.create(
            ball=ball,
            player=player,
            catch_date=datetime.now(),
            shiny=random.random() < 0.01  # 1% chance of shiny
        )
        
        # Update cooldown
        await PacklyCooldown.update_cooldown(interaction.user.id)
        
        # Create embed to show the result
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Daily Pack!",
            description=f"You received a **{ball.country}** ball!",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=ball.image_url)
        embed.add_field(name="Rarity", value=f"{ball.rarity:.2f}")
        if ball_instance.shiny:
            embed.add_field(name="Shiny", value="✨ Yes ✨")
        
        # Send the result
        await interaction.response.send_message(embed=embed)
        
    @app_commands.command(name="weekly")
    @app_commands.guild_only()
    async def weekly_command(self, interaction: discord.Interaction):
        """Claim your weekly pack! Get a rare ball with a maximum rarity of 0.3."""
        # Get the player
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        
        # Check cooldown
        can_claim = await WeeklyCooldown.can_claim(interaction.user.id)
        if not can_claim:
            await interaction.response.send_message("You have already claimed your weekly pack. You can claim your next pack in 7 days.")
            return
            
        # Find eligible rare balls (max rarity 0.3)
        eligible_balls = await Ball.filter(rarity__lte=0.3).all()
        if not eligible_balls:
            await interaction.response.send_message("There are no eligible rare balls available right now. Please try again later.")
            return
            
        # Pick a random ball
        ball = random.choice(eligible_balls)
        
        # Give the ball to the player
        ball_instance = await BallInstance.create(
            ball=ball,
            player=player,
            catch_date=datetime.now(),
            shiny=random.random() < 0.05  # 5% chance of shiny for weekly packs
        )
        
        # Update cooldown
        await WeeklyCooldown.update_cooldown(interaction.user.id)
        
        # Create embed to show the result
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Weekly Pack!",
            description=f"You received a **{ball.country}** ball!",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=ball.image_url)
        embed.add_field(name="Rarity", value=f"{ball.rarity:.2f}")
        if ball_instance.shiny:
            embed.add_field(name="Shiny", value="✨ Yes ✨")
        
        # Send the result
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    """Set up the Packly cog."""
    await bot.add_cog(Packly(bot))