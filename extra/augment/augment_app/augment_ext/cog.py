import logging
import random
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from django.utils import timezone

from augment_app import formulas
from augment_app.models import AugmentSettings
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.transformers import BallInstanceTransform
from bd_models.models import Player
from settings.models import settings
from settings.utils import format_currency

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from bd_models.models import BallInstance

log = logging.getLogger(__name__)


class Augment(commands.Cog):
    """
    Spend berries for a chance to improve a card's stats.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def augment(self, interaction: discord.Interaction["BallsDexBot"], countryball: BallInstanceTransform):
        """
        Spend berries for a chance to improve a card's stats.

        Parameters
        ----------
        countryball: BallInstance
            The card you want to augment.
        """
        if not countryball:
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        if countryball.locked and countryball.locked > timezone.now() - timedelta(minutes=30):
            await interaction.followup.send(
                f"This {settings.collectible_name} is locked for a trade and cannot be augmented right now."
            )
            return

        augment_settings = await AugmentSettings.aload()
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)

        price = formulas.cost(augment_settings, countryball)
        chance = formulas.success_rate(augment_settings, countryball)

        if not player.can_afford(price):
            await interaction.followup.send(
                f"You don't have enough {settings.currency_display_plural(self.bot)} to augment this "
                f"{settings.collectible_name}.\n"
                f"Cost: **{format_currency(price, False, self.bot)}**\n"
                f"Your balance: **{format_currency(player.money, False, self.bot)}**"
            )
            return

        embed = self._build_prompt_embed(countryball, augment_settings, price, chance)
        view = ConfirmChoiceView(interaction, accept_message="Augmenting...", cancel_message="Augment cancelled.")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()
        if not view.value:
            return

        await player.remove_money(price)

        success = random.uniform(0, 100) < chance
        sign = 1 if success else -1
        attack_delta = sign * random.randint(augment_settings.min_roll, augment_settings.max_roll)
        health_delta = sign * random.randint(augment_settings.min_roll, augment_settings.max_roll)

        max_attack, max_health = settings.max_attack_bonus, settings.max_health_bonus
        countryball.attack_bonus = max(-max_attack, min(max_attack, countryball.attack_bonus + attack_delta))
        countryball.health_bonus = max(-max_health, min(max_health, countryball.health_bonus + health_delta))
        await countryball.asave(update_fields=("attack_bonus", "health_bonus"))

        result_embed = self._build_result_embed(countryball, player, success, attack_delta, health_delta)
        await interaction.followup.send(embed=result_embed, ephemeral=True)

    def _build_prompt_embed(
        self,
        countryball: "BallInstance",
        augment_settings: AugmentSettings,
        price: int,
        chance: float,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"Augment {countryball.countryball.country}",
            description=(
                f"{countryball.description(include_emoji=True, bot=self.bot)}\n\n"
                f"**Cost:** {format_currency(price, False, self.bot)}\n"
                f"**Success chance:** {chance:.1f}%\n\n"
                f"On success, ATK and HP each increase by "
                f"{augment_settings.min_roll}-{augment_settings.max_roll}%.\n"
                f"On failure, ATK and HP each *decrease* by "
                f"{augment_settings.min_roll}-{augment_settings.max_roll}%.\n\n"
                f"Do you want to reroll the stats of this {settings.collectible_name} for "
                f"**{format_currency(price, False, self.bot)}**?"
            ),
            color=settings.embed_colour,
        )
        return embed

    def _build_result_embed(
        self,
        countryball: "BallInstance",
        player: Player,
        success: bool,
        attack_delta: int,
        health_delta: int,
    ) -> discord.Embed:
        return discord.Embed(
            title="Augment successful!" if success else "Augment failed...",
            description=(
                f"{countryball.description(include_emoji=True, bot=self.bot)}\n\n"
                f"ATK: {attack_delta:+d}% \N{RIGHTWARDS ARROW} now **{countryball.attack_bonus:+d}%**\n"
                f"HP: {health_delta:+d}% \N{RIGHTWARDS ARROW} now **{countryball.health_bonus:+d}%**\n\n"
                f"Remaining balance: **{format_currency(player.money, False, self.bot)}**"
            ),
            color=settings.embed_colour,
        )
