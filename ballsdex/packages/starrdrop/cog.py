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
from collections import Counter

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
log = logging.getLogger("ballsdex.packages.starrdrop")

class ContinueView(discord.ui.View):
    def __init__(self, author: discord.User | discord.Member):
        super().__init__(timeout=180)
        self.author = author
        self.continued = asyncio.Event()

    @button(label="Open", style=discord.ButtonStyle.secondary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("You can't open someone else's Starr Drop!", ephemeral=True)
            return
        
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
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    async def starrdrop(
        self,
        interaction: discord.Interaction,
        amount: int = 1,
    ):
        """
        Open one or more of your Starr Drops.
        
        Parameters
        ----------
        amount: int
            How much Starrdrops you want to open (Max 10).
        """
        
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        
        openamount = min(10, amount)
        
        if player.sdcount < openamount:
            await interaction.response.send_message(
                "You don't have enough Starr Drops, get them by catching brawlers or skins!",
                ephemeral=True
            )
            return
        
        raw_rarities = [
            ("rare", 50, 0.9),
            ("super_rare", 28, 0.65),
            ("epic", 15, 0.7),
            ("mythic", 5, 0.8),
            ("legendary", 2, 1.0),
        ]

        rarities = [{"name": n, "weight": w, "multiplier": m} for n, w, m in raw_rarities]
        
        total = sum(r["weight"] for r in rarities)
        normalized_weights = [r["weight"] / total for r in rarities]

        # Define reward pools by rarity with weights matching your percentages
        reward_tables = {
            "rare": (
                ["powerpoints", "credits", "skin", "bling"],
                [40, 20, 20, 20],
            ),
            "super_rare": (
                ["powerpoints", "credits", "skin", "bling"],
                [40, 20, 20, 20],
            ),
            "epic": (
                ["credits", "skin", "bling", "powerpoints"],
                [20, 20, 20, 40],
            ),
            "mythic": (
                ["credits_small", "credits_large", "skin", "bling"],
                [20, 40, 20, 20],
            ),
            "legendary": (
                ["legendary_brawler", "legendary_skin", "ultra_legendary_brawler", "ultimate_skin", "hypercharged_skin"],
                [35, 35, 10, 15, 5],
            ),
        }

        # Amount values for each reward type
        amounts = {
            "rare": {"powerpoints": 25, "credits": 100, "bling": 100},
            "super_rare": {"powerpoints": 50, "credits": 200, "bling": 250},
            "epic": {"powerpoints": 100, "credits": 500, "bling": 500},
            "mythic": {"credits_small": 250, "credits_large": 1000, "bling": 1000},
        }

        player.sdcount -= openamount
        await player.save(update_fields=("sdcount",))
        
        totalcredits  = 0
        totalpps      = 0
        if openamount > 1:
            log.debug(f"{interaction.user.id} Is Opening {openamount} Starr Drops:")   
            totalrewards  = []
            ounces        = []
        for i in range(openamount):
            ounce = random.choices(rarities, weights=normalized_weights, k=1)[0]
            
            if openamount > 1:
                ounces.append(ounce)
        
            options, weights = reward_tables[ounce.get("name")]
            result = random.choices(options, weights=weights, k=1)[0]
        
            log.debug(f"{interaction.user.id} Is Opening a {ounce.get('name')} Starr Drop!")
        
            if result in {"brawler", "legendary_brawler", "ultra_legendary_brawler"}:
                rarityexclude = {
                    "rare": {8, 16, 36, 25, 26, 27, 37, 39, 40},
                    "super_rare": {16, 36, 26, 27, 37, 40},
                    "epic": {36, 27, 37, 40},
                    "mythic": {5, 6, 22, 23, 38, 27, 40},
                    "legendary": {5, 6, 7, 22, 23, 38, 24},
                }

                # For legendary brawlers, regime_ids may be specific, add your filtering as needed
                if result in {"brawler", "legendary_brawler", "ultra_legendary_brawler"}:
                    available_balls = [ball for ball in balls.values() if ball.enabled and ball.rarity > 0 and ball.regime_id in {5, 6, 7, 8, 16, 36}]
                    available_balls = [ball for ball in available_balls if ball.regime_id not in rarityexclude[ounce.get('name')]]
                    if not available_balls:
                        await interaction.followup.send(
                            "There are no brawlers available to claim at the moment.", ephemeral=True
                        )
                        return

                    is_special = random.randint(1, 4096) == 1
                    if is_special:
                        spec = await Special.get(name="Chromatic")
                    rarity_vals = [x.rarity for x in available_balls]
                    factor = ounce.get("multiplier")
                    adjusted_rarity = [r ** (1 / factor) for r in rarity_vals]
                    claimed_ball = random.choices(population=available_balls, weights=adjusted_rarity, k=1)[0]

                    ball_instance = await BallInstance.create(
                        ball=claimed_ball,
                        player=player,
                        attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                        health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                        special=spec if is_special else None,
                        server_id=interaction.user.guild.id if interaction.user.guild else None,
                    )

                    if openamount == 1:
                        view = ContinueView(author=interaction.user)
                        await interaction.response.send_message(
                            f"{ounce.get('name').replace('_', ' ').title()} Starr Drop",
                            view=view,
                            ephemeral=False
                        )

                        await view.continued.wait()
                
                        data, file, view = await ball_instance.prepare_for_message(interaction)
                        await interaction.edit_original_response(
                            content=f"You opened your {ounce.get('name').replace('_', ' ').title()} Starr Drop and got... **{'Shiny ' if is_special else ''}{claimed_ball.country}**!\n\n{data}",
                            attachments=[file],
                            view=view
                        )
                    else:
                        totalrewards.append(f"{self.bot.get_emoji(ball_instance.ball.emoji_id)}{ball_instance.ball.country}")

            elif result in {"powerpoints", "credits", "credits_small", "credits_large", "bling"}:
                if result == "powerpoints":
                    amount = amounts[ounce.get("name")]["powerpoints"]
                    totalpps += amount
                    mjid = 1364807487106191471
                    if amount >= 75:
                        mjid = 1364817571819425833
                    mj = self.bot.get_emoji(mjid)
                    reward_text = f"{mj}{amount} powerpoints"

                elif result == "credits":
                    amount = amounts[ounce.get("name")]["credits"]
                    totalcredits += amount
                    mjid = 1364877727601004634
                    if amount >= 40:
                        mjid = 1364877745032794192
                    mj = self.bot.get_emoji(mjid)
                    reward_text = f"{mj}{amount} credits"

                elif result == "credits_small":
                    amount = amounts["mythic"]["credits_small"]
                    totalcredits += amount
                    mjid = 1364877727601004634
                    mj = self.bot.get_emoji(mjid)
                    reward_text = f"{mj}{amount} credits"

                elif result == "credits_large":
                    amount = amounts["mythic"]["credits_large"]
                    totalcredits += amount
                    mjid = 1364877745032794192
                    mj = self.bot.get_emoji(mjid)
                    reward_text = f"{mj}{amount} credits"

                elif result == "bling":
                    amount = amounts[ounce.get("name")]["bling"] if ounce.get("name") != "mythic" else amounts["mythic"]["bling"]
                    # Assuming bling is a special currency emoji, replace 💎 with your actual emoji if any
                    reward_text = f"💎 {amount} bling"

                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"{ounce.get('name').replace('_', ' ').title()} Starr Drop",
                        view=view,
                        ephemeral=False
                    )

                    await view.continued.wait()
            
                    await interaction.edit_original_response(
                        content=f"You opened your {ounce.get('name').replace('_', ' ').title()} Starr Drop and got... \n\n{reward_text}!",
                        view=None
                    )
                else:
                    totalrewards.append(reward_text)

            elif result in {"skin", "legendary_skin", "ultimate_skin", "hypercharged_skin"}:
                # Implement your skin selection logic by rarity here (filter by rarity and regime_id)
                # Placeholder reward text for now:
                reward_text = f"A {result.replace('_', ' ').title()}"

                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"{ounce.get('name').replace('_', ' ').title()} Starr Drop",
                        view=view,
                        ephemeral=False
                    )
                    await view.continued.wait()
                    await interaction.edit_original_response(
                        content=f"You opened your {ounce.get('name').replace('_', ' ').title()} Starr Drop and got... \n\n{reward_text}!",
                        view=None
                    )
                else:
                    totalrewards.append(reward_text)

        if openamount > 1:
            totalrewards_text = "\n".join(totalrewards)
            await interaction.response.send_message(
                f"You opened your {openamount} Starr Drops and got:\n\n{totalrewards_text}",
                ephemeral=False,
            )
        
        # Save credits, powerpoints, and any other currency to player here if applicable
        player.credits += totalcredits
        player.powerpoints += totalpps
        await player.save(update_fields=("credits", "powerpoints"))
