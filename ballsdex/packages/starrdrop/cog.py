
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
class StarrDrop(commands.GroupCog, group_name="starrdrop"):
    """
    The daily starr drop command.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        
    @app_commands.command()
    @app_commands.checks.cooldown(2, 10, key=lambda i: i.user.id)
    async def claim(
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
            ("rare", 50, 1.0),
            ("super_rare", 28, 1.1),
            ("epic", 15, 1.25),
            ("mythic", 5, 1.5),
            ("legendary", 2, 1.0),
        ]

        rarities = [{"name": n, "weight": w, "multiplier": m} for n, w, m in raw_rarities]
        
        total = sum(r["weight"] for r in rarities)
        normalized_weights = [r["weight"] / total for r in rarities]


        player.sdcount-=openamount ; await player.save(update_fields=("sdcount",))
        
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
        
            options = ["brawler", "skin", "credits", "powerpoints"]
        
            weights = [5, 2, 4, 4]

            if ounce.get('name') in {"mythic", "legendary"}:
                options.remove("powerpoints")
                weights.remove(4)
            if ounce.get('name') in {"legendary"}:
                options.remove("credits")
                weights.remove(4)

            result = random.choices(options, weights=weights, k=1)[0]
        
            log.debug(f"{interaction.user.id} Is Opening a {ounce.get('name')} Starr Drop!")
        
            if result in {"brawler", "skin"}:
                rarityexclude = {"rare":{8, 16, 36, 25, 26, 27, 37, 39, 40}, "super_rare":{16, 36, 26, 27, 37, 40}, "epic":{36, 27, 37, 40}, "mythic":{5, 6, 27, 40}, "legendary":{5, 6, 7}}
                if result == "brawler":
                    available_balls = [ball for ball in balls.values() if ball.enabled and ball.rarity > 0 and ball.regime_id in {5, 6, 7, 8, 16, 36}]
                    available_balls = [ball for ball in available_balls if ball.regime_id not in rarityexclude[ounce.get('name')]]
                else:
                    available_balls = [ball for ball in balls.values() if ball.enabled and ball.regime_id in {22, 23, 24, 25, 26, 27, 37, 38, 39, 40}]
                    available_balls = [ball for ball in available_balls if ball.regime_id not in rarityexclude[ounce.get('name')]]
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
            elif result in {"powerpoints", "credits"}:
                options = [(5, 10), (10, 25), (50, 100), (250, 250), (1000, 1000)]
                weights = [10, 10, 25, 10, 3]
                rangespec = random.choices(options, weights=weights, k=1)[0]
                amount = round(random.randint(rangespec[0], rangespec[1]) / 5) * 5
                mjid = 1364877727601004634 if result == "credits" else 1364807487106191471
                if result == "credits" and amount >= 40:
                    mjid = 1364877745032794192
                elif result == "powerpoints" and amount >= 75:
                    mjid = 1364817571819425833
                mj = self.bot.get_emoji(mjid)
                
                if result == "credits":
                    totalcredits += amount
                else:
                    totalpps += amount
            
                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"{ounce.get('name').replace('_', ' ').title()} Starr Drop",
                        view=view,
                        ephemeral=False
                    )

                    await view.continued.wait()
        
                    await interaction.edit_original_response(
                        content=f"You opened your {ounce.get('name').replace('_', ' ').title()} Starr Drop and got... \n\n{mj}{amount} {result}!",
                        view=None
                    )
                else:
                    totalrewards.append(f"{mj}{amount} {result}{mj}")

        if totalcredits > 0:
            player.credits += totalcredits
        if totalpps > 0:
            player.powerpoints += totalpps
        if totalcredits > 0 or totalpps > 0:
            await player.save(update_fields=("credits", "powerpoints"))
        
        if openamount > 1:          
            rarity_names = [r["name"].replace("_", " ").title() for r in ounces]

            rarity_counts = Counter(rarity_names)
            
            formatted = [f"{count}× {name}" for name, count in rarity_counts.items()]

            if len(formatted) == 1:
                rarity_line = f"{formatted[0]} Starr Drop"
            else:
                rarity_line = f"{', '.join(formatted[:-1])}, and {formatted[-1]} Starr Drops"
            
            view = ContinueView(author=interaction.user)
            
            await interaction.response.send_message(
                content=f"You're opening: {rarity_line}",
                view=view
            )

            await view.continued.wait()
            
            reward_list = "\n".join(f"- {item}" for item in totalrewards)
            await interaction.edit_original_response(
                content=f"You opened your {openamount} {rarity_line} and got... \n\n{reward_list}",
                view=None
            )
