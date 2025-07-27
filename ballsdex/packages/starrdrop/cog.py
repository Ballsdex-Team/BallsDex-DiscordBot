import logging
from typing import TYPE_CHECKING, cast
import random
import asyncio
import math
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, button
from ballsdex.core.models import Ball, BallInstance, balls, Player
from ballsdex.core.customexceptions import NotAdminGuildError
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


class StarrDrop(commands.Cog):
    """
    The daily starr drop command.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(dms=True, private_channels=True, guilds=True)
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    async def starrdrop(
        self,
        interaction: discord.Interaction,
        amount: int = 1,
    ):
        """
        Open one or more of your Starr Drops.
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        openamount = min(10, amount)

        if player.sdcount < openamount:
            await interaction.response.send_message(
                "You don't have enough Starr Drops, get them by catching Brawlers or Skins!",
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
        DROP_RARITY_EMOJIS = {
            "rare": 1330493249235714189,
            "super_rare": 1330493410884456528,
            "epic": 1330493427011555460,
            "mythic": 1330493448469483580,
            "legendary": 1330493465221529713
        }
        DROP_RARITY_EMOJI = ""
        rarities = [{"name": n, "weight": w, "multiplier": m} for n, w, m in raw_rarities]
        total = sum(r["weight"] for r in rarities)
        normalized_weights = [r["weight"] / total for r in rarities]

        player.sdcount -= openamount
        await player.save(update_fields=("sdcount",))

        totalcredits = 0
        totalpps = 0
        if openamount > 1:
            log.debug(f"{interaction.user.id} Is Opening {openamount} Starr Drops:")
            totalrewards = []
            ounces = []

        for i in range(openamount):
            ounce = random.choices(rarities, weights=normalized_weights, k=1)[0]
            if openamount > 1:
                ounces.append(ounce)

            rarity = ounce["name"]
            reward = None

            if rarity == "rare":
                reward = random.choices(["25pp", "100c", "rare_skin"], weights=[50, 30, 20], k=1)[0]
                DROP_RARITY_EMOJI = interaction.client.get_emoji(DROP_RARITY_EMOJIS.get(rarity))
            elif rarity == "super_rare":
                reward = random.choices(["50pp", "200c", "super_skin"], weights=[50, 30, 20], k=1)[0]
                DROP_RARITY_EMOJI = interaction.client.get_emoji(DROP_RARITY_EMOJIS.get(rarity))
            elif rarity == "epic":
                reward = random.choices(["100pp", "500c", "epic_skin"], weights=[50, 30, 20], k=1)[0]
                DROP_RARITY_EMOJI = interaction.client.get_emoji(DROP_RARITY_EMOJIS.get(rarity))
            elif rarity == "mythic":
                reward = random.choices(["1000c", "mythic_brawler", "mythic_skin"], weights=[35, 40, 25], k=1)[0]
                DROP_RARITY_EMOJI = interaction.client.get_emoji(DROP_RARITY_EMOJIS.get(rarity))
            elif rarity == "legendary":
                DROP_RARITY_EMOJI = interaction.client.get_emoji(DROP_RARITY_EMOJIS.get(rarity))
                reward = random.choices(
                    ["legendary_brawler", "legendary_skin", "ultra_legendary", "ultimate_skin", "hypercharged_skin"],
                    weights=[40, 35, 5, 15, 5],
                    k=1
                )[0]

            if reward.endswith("pp") or reward.endswith("c"):
                amount = int(reward.rstrip("pc"))
                currency_type = "power_points" if reward.endswith("pp") else "credits"
                emoji_id = 1364807487106191471 if currency_type == "power_points" else 1364877727601004634
                if currency_type == "credits" and amount >= 40:
                    emoji_id = 1364877745032794192
                elif currency_type == "power_points" and amount >= 75:
                    emoji_id = 1364817571819425833
                mj = self.bot.get_emoji(emoji_id)

                if currency_type == "credits":
                    totalcredits += amount
                else:
                    totalpps += amount

                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"# {DROP_RARITY_EMOJI} {rarity.replace('_', ' ').title()} Starr Drop {DROP_RARITY_EMOJI}",
                        view=view,
                        ephemeral=False
                    )
                    await view.continued.wait()

                    await interaction.edit_original_response(
                        content=f"You opened your {rarity.replace('_', ' ').title()} Starr Drop and...\n# {mj} You got {amount} {currency_type.replace("_", " ").title()}! {mj}",
                        view=None
                    )
                else:
                    totalrewards.append(f"{mj} {amount} {currency_type.replace("_", " ").title()}")
            else:
                brawler_ids = {
                    "mythic_brawler": {8},
                    "legendary_brawler": {16},
                    "ultra_legendary": {36}
                }
                skin_ids = {
                    "rare_skin": {22},
                    "super_skin": {23, 38},
                    "epic_skin": {24},
                    "mythic_skin": {39, 25},
                    "legendary_skin": {26},
                    "ultimate_skin": {37},
                    "hypercharged_skin": {40, 27}
                }

                ids = brawler_ids.get(reward) or skin_ids.get(reward) or set()

                available_balls = [
                    ball for ball in balls.values()
                    if ball.regime_id in ids and getattr(ball, "enabled", True)
                ]

                if not available_balls:
                    await interaction.followup.send("There are no brawlers available to claim at the moment.", ephemeral=True)
                    return

                base_rarity_weight = ounce["weight"]
                rarity_weights = [
                    (ball.rarity if ball.rarity > 0 else base_rarity_weight) ** (1 / ounce["multiplier"])
                    for ball in available_balls
                ]
                claimed_ball = random.choices(available_balls, weights=rarity_weights, k=1)[0]

                ball_instance = await BallInstance.create(
                    ball=claimed_ball,
                    player=player,
                    attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                    health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                    server_id=interaction.user.guild.id if interaction.guild else None,
                )

                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"# {DROP_RARITY_EMOJI} {rarity.replace('_', ' ').title()} Starr Drop {DROP_RARITY_EMOJI}",
                        view=view,
                        ephemeral=False
                    )
                    await view.continued.wait()

                    data, file, view = await ball_instance.prepare_for_message(interaction)
                    await interaction.edit_original_response(
                        content=f"You opened your {rarity.replace('_', ' ').title()} Starr Drop and got...\n{data}",
                        attachments=[file],
                        view=view
                    )
                else:
                    totalrewards.append(f"{self.bot.get_emoji(claimed_ball.emoji_id)} [{claimed_ball.country}](<https://brawldex.fandom.com/wiki/{claimed_ball.country.replace(" ", "_")}>)")

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
            rarity_line = f"{', '.join(formatted[:-1])}, and {formatted[-1]}" if len(formatted) > 1 else f"{formatted[0]}"

            view = ContinueView(author=interaction.user)
            await interaction.response.send_message(
                content=f"You're opening: {rarity_line} Starr Drop{'s' if openamount > 1 else ''}",
                view=view
            )
            await view.continued.wait()

            reward_list = "\n".join(f"- {item}" for item in totalrewards)
            await interaction.edit_original_response(
                content=f"You opened your {openamount} Starr Drops and got...\n\n{reward_list}",
                view=None
            )

    @app_commands.command(name="brawlpass", description="Claim your daily Starr Drops if you have Brawl Pass!")
    @app_commands.guilds(*settings.admin_guild_ids)
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def claim_brawlpass_drops(self, interaction: discord.Interaction["BallsDexBot"]):
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        try:
            bp_type, bp_msg = await interaction.client.brawl_pass_check(interaction)
        except NotAdminGuildError as e:
            log.error("Not possible to execute this command here", exc_info=e)
            return
        if bp_type == "Brawl Pass Plus":
            player.sdcount += 2
            await player.save()
            await interaction.response.send_message("Successfully claimed 2 Starr Drops since you have Brawl Pass Plus!", ephemeral=True)
            log.debug(f"{bp_msg} 2 Starr Drops are given. (User ID: {interaction.user.id})")
        elif bp_type == "Brawl Pass":
            player.sdcount += 1
            await player.save()
            await interaction.response.send_message("Successfully claimed a Starr Drop since you have Brawl Pass!", ephemeral=True)
            log.debug(f"{bp_msg} A Starr Drop is given. (User ID: {interaction.user.id})")

        else:
            await interaction.response.send_message("You can't use this command as you don't have Brawl Pass!", ephemeral=True)
            log.debug(f"{bp_msg} No any Starr Drops are given. (User ID: {interaction.user.id})")
