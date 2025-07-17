import discord, random
from discord import app_commands
from discord.ext import commands
from ballsdex.settings import settings
from collections import defaultdict
from tortoise.functions import Count
from ballsdex.core.models import Ball, BallInstance, Player, balls, Special
from ballsdex.core.utils.paginator import FieldPageSource, Pages, TextPageSource

class Custom(commands.GroupCog, group_name="custom"):

    @app_commands.command()
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def claim(self, interaction: discord.Interaction):
        """
        Claim a random countryball once every day.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        player, created = await Player.get_or_create(discord_id=interaction.user.id)
        available_balls = [ball for ball in balls.values() if ball.enabled and ball.rarity >= 2]

        if not available_balls:
            await interaction.followup.send(
                f"There are no {settings.collectible_name} available to claim at the moment.", ephemeral=True
            )
            return

        specials = await Special.all()
        special_weights = [special.rarity for special in specials]
        total_weight = sum(special_weights) + len(available_balls)
        weights = special_weights + [1] * len(available_balls)

        claimed_ball = random.choices(specials + available_balls, weights=weights, k=1)[0]

        ball_instance = await BallInstance.create(
            ball=claimed_ball if isinstance(claimed_ball, Ball) else None,
            player=player,
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            special=claimed_ball if isinstance(claimed_ball, Special) else None,
        )

        _, file, _ = await ball_instance.prepare_for_message(interaction)
        await interaction.followup.send(
            content=f"Congratulations! You have claimed a {claimed_ball.country if isinstance(claimed_ball, Ball) else claimed_ball.name} {settings.collectible_name}!",
            file=file,
            ephemeral=True,
        )
        file.close()

    @app_commands.command()
    @app_commands.checks.cooldown(1, 604800, key=lambda i: i.user.id)  # 7 days
    async def weekly(self, interaction: discord.Interaction):
        """
        Claim a random countryball once every 7 days.
        """
        await interaction.response.defer(thinking=True)
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        # Include enabled balls with 0.5 <= rarity <= 7.0
        available_balls = [ball for ball in balls.values() if ball.enabled and 0.5 <= ball.rarity <= 7.0]

        if not available_balls:
            await interaction.followup.send(
                f"There are no {settings.collectible_name}s available to claim right now.", ephemeral=False
            )
            return

        specials = await Special.all()
        special_weights = [special.rarity for special in specials]
        weights = special_weights + [2] * len(available_balls)

        claimed_ball = random.choices(specials + available_balls, weights=weights, k=1)[0]

        attack_bonus = random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
        health_bonus = random.randint(-settings.max_health_bonus, settings.max_health_bonus)

        ball_instance = await BallInstance.create(
            ball=claimed_ball if isinstance(claimed_ball, Ball) else None,
            player=player,
            attack_bonus=attack_bonus,
            health_bonus=health_bonus,
            special=claimed_ball if isinstance(claimed_ball, Special) else None,
        )

        _, file, _ = await ball_instance.prepare_for_message(interaction)

        name = claimed_ball.country if isinstance(claimed_ball, Ball) else claimed_ball.name
        rarity = claimed_ball.rarity
        base_attack = claimed_ball.attack
        base_health = claimed_ball.health

        await interaction.followup.send(
            content=(
                f"**⚽ You got {name}!**\n\n"
                f"**⭐ Rarity:** {rarity}\n"
                f"**♥️ Health:** {base_health}\n"
                f"**🗡️ Attack:** {base_attack}"
            ),
            file=file,
            ephemeral=False,
        )
        file.close()
