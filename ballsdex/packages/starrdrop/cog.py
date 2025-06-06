import logging
from typing import TYPE_CHECKING, cast
import random
import asyncio
import math
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, button
from ballsdex.core.models import Special, Ball, BallInstance, balls, Player
from ballsdex.settings import settings
from datetime import datetime, timedelta, timezone

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
log = logging.getLogger("ballsdex.packages.starrdrop")

class ContinueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.continued = asyncio.Event()

    @button(label="Open", style=discord.ButtonStyle.secondary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.continued.set()
        self.stop()

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(dms=True, private_channels=True, guilds=True)
class StarrDrop(commands.Cog):
    """
    The daily starr drop command.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        
    @app_commands.command()
    @app_commands.checks.cooldown(2, 30, key=lambda i: i.user.id)
    async def starrdrop(self, interaction: discord.Interaction):
        """
        Open one of your Starr Drops.
        """
        
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        if player.sdcount < 1:
            await interaction.response.send_message(
                "You don't have any Starr Drops, get them by catching brawlers or skins!",
                ephemeral=True
            )
            return
        
        raw_rarities = [
            ("rare", 50, 1.0),
            ("super_rare", 28, 1.25),
            ("epic", 15, 1.75),
            ("mythic", 5, 4.5),
            ("legendary", 2, 6),
        ]

        rarities = [{"name": n, "weight": w, "multiplier": m} for n, w, m in raw_rarities]
        
        total = sum(r["weight"] for r in rarities)
        normalized_weights = [r["weight"] / total for r in rarities]

        ounce = random.choices(rarities, weights=normalized_weights, k=1)[0]
        
        
        view = ContinueView()
        await interaction.response.send_message(
            f"{ounce.get('name').replace("_", " ").capitalize()} Starr Drop",
            view=view,
            ephemeral=False
        )

        await view.continued.wait()
        
        options = ["ball", "credits", "powerpoints"]
        
        weights = [5, 4, 4]

        if ounce.get("name") in {"mythic", "legendary"}:
            options.remove("powerpoints")
            weights.remove(4)
        

        result = random.choices(options, weights=weights, k=1)[0]
        
        player.sdcount-=1 ; await player.save(update_fields=("sdcount",))
        log.debug(f"{interaction.user.id} Is Opening a {ounce.get('name')} Starr Drop!")
        
        if result == "ball":
            available_balls = [ball for ball in balls.values() if ball.enabled]
            if not available_balls:
                await interaction.followup.send(
                    "There are no brawlers available to claim at the moment.", ephemeral=True
                )
                return

            is_special = random.randint(1, 4096) == 1
            if is_special:
                spec = await Special.get(name="Chromatic")
            rarity = [x.rarity for x in available_balls]
            factor = ounce.get("multiplier")
            adjusted_rarity = [r ** (1 / (factor)) for r in rarity]
            claimed_ball = random.choices(population=available_balls, weights=adjusted_rarity, k=1)[0]

            ball_instance = await BallInstance.create(
                ball=claimed_ball,
                player=player,
                attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                special=spec if is_special else None,
                server_id=interaction.user.guild.id,
            )

            data, file, view = await ball_instance.prepare_for_message(interaction)
            await interaction.edit_original_response(
                content=f"You opened your {ounce.get('name').replace("_", " ").capitalize()} Starr Drop and got... **{'Shiny ' if is_special else ''}{claimed_ball.country}**!\n\n{data}",
                attachments=[file],
                view=view
            )
        elif result in {"powerpoints", "credits"}:
            options = [25, 50, 100, 250]
            weights = [25, 15, 10, 4]
            amount = random.choices(options, weights=weights, k=1)[0]
            if result == "credits":
                amount*=1.25
            amount*= ounce.get("multiplier")
            amount = math.ceil(amount)
            mjid = 1364877745032794192 if result == "credits" else 1364817571819425833
            mj = self.bot.get_emoji(mjid)
            setattr(player, result, getattr(player, result) + amount)
            await player.save()
            await interaction.edit_original_response(
                content=f"You opened your {ounce.get('name').replace("_", " ").capitalize()} Starr Drop and got... \n\n{mj}{amount} {result}!",
                view=None
            )
