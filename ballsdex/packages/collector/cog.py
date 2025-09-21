import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.models import (
    Ball,
    BallInstance,
    Player,
    Special,
)
from ballsdex.core.utils.transformers import BallEnabledTransform
from tortoise.exceptions import DoesNotExist

RARITY_REQUIREMENTS = [
    (0.0020, 200),
    (0.0026, 250),
    (0.0030, 300),
    (0.0038, 350),
    (0.0048, 400),
    (0.0061, 450),
    (0.0064, 475),
    (0.0074, 500),
    (0.0078, 525),
    (0.0081, 550),
    (0.0085, 575),
    (0.0089, 600),
    (0.0093, 625),
    (0.0098, 650),
    (0.0103, 675),
    (0.0108, 700),
    (0.0114, 725),
    (0.0120, 750),
    (0.0129, 775),
    (0.0135, 800),
    (0.0142, 825),
    (0.0250, 1000),
]

DIAMOND_SHINY_REQUIREMENTS_CLUSTERED = [
    (0.0020, 10),  # T1
    (0.0026, 11),  # T4
    (0.0030, 12),  # T5
    (0.0038, 13),  # T7
    (0.0048, 14),  # T9
    (0.0061, 15),  # T12
    (0.0064, 16),  # T13
    (0.0074, 17),  # T19
    (0.0078, 18),  # T20
    (0.0081, 19),  # T21
    (0.0085, 20),  # T22
    (0.0089, 21),  # T23
    (0.0093, 22),  # T24
    (0.0098, 23),  # T25
    (0.0103, 24),  # T26
    (0.0108, 24),  # T27
    (0.0114, 24),  # T28
    (0.0120, 24),  # T29
    (0.0129, 24),  # T31
    (0.0135, 25),  # T32
    (0.0142, 25),  # T33
    (0.0250, 25),  # T43
]

class Collector(commands.GroupCog, group_name="claim"):
    """
    Cog for claiming collector and diamond countryballs.
    """

    @app_commands.command()
    async def collector(self, interaction: discord.Interaction, countryball: BallEnabledTransform):
        """
        Claim a collector countryball.

        Parameters
        ----------
        countryball: Ball
            Ball to claim.
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        try:
            special = await Special.get(name="Collector")
        except DoesNotExist:
            await interaction.response.send_message(
                "No `Collector` special is registered on this bot.", ephemeral=True
            )
            return

        # Check if the player already has a collector instance for this ball
        already_claimed = await BallInstance.filter(
            ball=countryball, player=player, special=special
        ).exists()
        if already_claimed:
            await interaction.response.send_message(
                "You have already claimed this collector ball.", ephemeral=True
            )
            return

        # Fetch the player's ball instances for the given countryball
        player_balls = await BallInstance.filter(
            ball=countryball, player=player
        ).order_by("-catch_date")

        # Determine the required amount based on rarity
        rarity = countryball.rarity
        required_amount = 0
        for threshold, amount in RARITY_REQUIREMENTS:
            if rarity <= threshold:
                required_amount = amount
                break

        # Check if the player has enough balls to claim the collector
        if len(player_balls) < required_amount:
            await interaction.response.send_message(
                f"You need **{required_amount}** {countryball.country} balls to claim this collector.\n"
                f"You currently have **{len(player_balls)}**.",
                ephemeral=True,
            )
            return

        # Create a new BallInstance for the collector
        collector_instance = await BallInstance.create(
            ball=countryball,
            player=player,
            health_bonus=0,
            attack_bonus=0,
            defense_bonus=0,
            special=special,
        )

        await interaction.response.send_message(
            f"Congratulations! You have claimed a collector {collector_instance.ball.country}!",
            ephemeral=True,
        )

    @app_commands.command()
    async def diamond(self, interaction: discord.Interaction, countryball: BallEnabledTransform):
        """
        Claim a diamond countryball.

        Parameters
        ----------
        countryball: Ball
            Ball to claim.
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        try:
            special = await Special.get(name="Diamond")
        except DoesNotExist:
            await interaction.response.send_message(
                "No `Diamond` special is registered on this bot.", ephemeral=True
            )
            return

        # Check if the player already has a diamond instance for this ball
        already_claimed = await BallInstance.filter(
            ball=countryball, player=player, special=special
        ).exists()
        if already_claimed:
            await interaction.response.send_message(
                "You have already claimed this diamond ball.", ephemeral=True
            )
            return

        # Determine required shinies based on rarity
        rarity = countryball.rarity
        required_shinies = 1  # default fallback
        for threshold, amount in DIAMOND_SHINY_REQUIREMENTS_CLUSTERED:
            if rarity <= threshold:
                required_shinies = amount
                break

        shiny_count = await BallInstance.filter(
            ball=countryball, player=player, shiny=True
        ).count()

        if shiny_count < required_shinies:
            await interaction.response.send_message(
                f"You need **{required_shinies} shiny {countryball.country} balls** to claim this diamond ball.\n"
                f"You currently have **{shiny_count}**.",
                ephemeral=True,
            )
            return

        # Create a new BallInstance for the diamond
        diamond_instance = await BallInstance.create(
            ball=countryball,
            player=player,
            health_bonus=0,
            attack_bonus=0,
            defense_bonus=0,
            special=special,
        )

        await interaction.response.send_message(
            f"Congratulations! You have claimed a diamond {diamond_instance.ball.country}!",
            ephemeral=True,
        )