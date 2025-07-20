import logging
from typing import TYPE_CHECKING, cast
import random
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, button
from ballsdex.core.models import Special, Ball, BallInstance, balls, Player
from ballsdex.settings import settings
from collections import Counter

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.starrdrop")

STARRDROP_REWARDS = {
    "rare": [
        {"type": "powerpoints", "amount": 25, "weight": 50},
        {"type": "credits", "amount": 100, "weight": 30},
        {"type": "skin", "rarity": "rare", "weight": 20},
    ],
    "super_rare": [
        {"type": "powerpoints", "amount": 50, "weight": 50},
        {"type": "credits", "amount": 200, "weight": 30},
        {"type": "skin", "rarity": "super_rare", "weight": 20},
    ],
    "epic": [
        {"type": "powerpoints", "amount": 100, "weight": 50},
        {"type": "credits", "amount": 500, "weight": 30},
        {"type": "skin", "rarity": "epic", "weight": 20},
    ],
    "mythic": [
        {"type": "credits", "amount": 1000, "weight": 35},
        {"type": "brawler", "rarity": "mythic", "weight": 40},
        {"type": "skin", "rarity": "mythic", "weight": 25},
    ],
    "legendary": [
        {"type": "brawler", "rarity": "legendary", "weight": 40},
        {"type": "skin", "rarity": "legendary", "weight": 35},
        {"type": "brawler", "rarity": "ultra_legendary", "weight": 5},
        {"type": "skin", "rarity": "ultimate", "weight": 15},
        {"type": "skin", "rarity": "hypercharged", "weight": 5},
    ]
}

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
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    @app_commands.checks.has_any_role(*settings.root_role_ids, 1357857303222816859)
    async def starrdrop(self, interaction: discord.Interaction, amount: int = 1):
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        openamount = min(10, amount)
        if player.sdcount < openamount:
            await interaction.response.send_message("You don't have enough Starr Drops!", ephemeral=True)
            return

        player.sdcount -= openamount
        await player.save(update_fields=("sdcount",))

        raw_rarities = [("rare", 50), ("super_rare", 28), ("epic", 15), ("mythic", 5), ("legendary", 2)]
        rarities = [r[0] for r in raw_rarities]
        weights = [r[1] for r in raw_rarities]

        totalcredits = 0
        totalpps = 0
        totalrewards = []
        rarity_names = []

        for _ in range(openamount):
            rarity_name = random.choices(rarities, weights=weights)[0]
            rarity_names.append(rarity_name)
            reward_pool = STARRDROP_REWARDS[rarity_name]
            reward_weights = [r["weight"] for r in reward_pool]
            reward = random.choices(reward_pool, weights=reward_weights)[0]
            await ball.prefetch_related("regime")
            if reward["type"] in {"brawler", "skin"}:
                matching_balls = [
                    ball for ball in balls.values()
                    if ball.enabled and ball.regime.name == reward["rarity"].replace("_", " ").title() and
                    (ball.regime_id in {5, 6, 7, 8, 16} if reward["type"] == "brawler" else ball.regime_id in {22, 23, 24, 25, 26, 27, 37, 38, 39, 40})
                ]
                if not matching_balls:
                    totalrewards.append(f"{reward['rarity'].title()} {reward['type'].title()} (none available)")
                    continue

                claimed_ball = random.choice(matching_balls)
                is_special = random.randint(1, 4096) == 1
                spec = await Special.get(name="Chromatic") if is_special else None

                ball_instance = await BallInstance.create(
                    ball=claimed_ball,
                    player=player,
                    attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                    health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                    special=spec,
                    server_id=interaction.guild_id if interaction.guild else None
                )

                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"{rarity_name.replace('_', ' ').title()} Starr Drop",
                        view=view
                    )
                    await view.continued.wait()

                    data, file, view_card = await ball_instance.prepare_for_message(interaction)
                    await interaction.edit_original_response(
                        content=f"You opened your {rarity_name.replace('_', ' ').title()} Starr Drop and got... **{'Shiny ' if is_special else ''}{claimed_ball.country}**!\n\n{data}",
                        attachments=[file],
                        view=view_card
                    )
                    return
                else:
                    emoji = self.bot.get_emoji(claimed_ball.emoji_id)
                    totalrewards.append(f"{emoji} **{claimed_ball.country}**")

            elif reward["type"] == "credits":
                amount = reward["amount"]
                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"{rarity_name.replace('_', ' ').title()} Starr Drop",
                        view=view
                    )
                    await view.continued.wait()
                    await interaction.edit_original_response(
                        content=f"You opened your {rarity_name.replace('_', ' ').title()} Starr Drop and got 💰 **{amount} credits!**",
                        view=None
                    )
                    return
                totalcredits += amount
            elif reward["type"] == "powerpoints":
                amount = reward["amount"]
                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"{rarity_name.replace('_', ' ').title()} Starr Drop",
                        view=view
                    )
                    await view.continued.wait()
                    await interaction.edit_original_response(
                        content=f"You opened your {rarity_name.replace('_', ' ').title()} Starr Drop and got ⚡ **{amount} power points!**",
                        view=None
                    )
                    return
                totalpps += amount

        if totalcredits:
            player.credits += totalcredits
        if totalpps:
            player.powerpoints += totalpps
        await player.save(update_fields=("credits", "powerpoints"))

        summary = f"**Opened {openamount} Starr Drops:**\n"
        rarity_count = Counter(rarity_names)
        for r_name, count in rarity_count.items():
            summary += f"\n{r_name.replace('_', ' ').title()} ×{count}"

        if totalpps:
            summary += f"\n\n**Power Points:** {totalpps}"
        if totalcredits:
            summary += f"\n\n**Credits:** {totalcredits}"
        if totalrewards:
            summary += "\n\n**Rewards:** " + ", ".join(totalrewards)

        await interaction.response.send_message(summary)

async def setup(bot):
    await bot.add_cog(StarrDrop(bot))
