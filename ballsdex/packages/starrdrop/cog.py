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
        # Define rarity levels for balls to compare by integer rarity field
        self.rarity_levels = {
            "rare": 1,
            "super_rare": 2,
            "epic": 3,
            "mythic": 4,
            "legendary": 5,
        }

    def _get_balls_by_rarity_and_type(self, rarity_name: str, kind: str):
        """
        Return filtered balls by rarity and kind (brawler or skin).
        For legendary, we retry picking balls that match exactly the legendary rarity.
        """
        rarity_level = self.rarity_levels[rarity_name]

        if kind == "brawler":
            # regime_id filter like before for brawlers
            allowed_regimes = {5, 6, 7, 8, 16, 36}
        else:
            # skin regime_ids as before
            allowed_regimes = {22, 23, 24, 25, 26, 27, 37, 38, 39, 40}

        # Base ball filter
        filtered = [
            ball for ball in balls.values()
            if ball.enabled
            and ball.rarity == rarity_level
            and ball.regime_id in allowed_regimes
        ]

        # If no balls found exactly, fallback to any enabled balls of allowed regime but any rarity
        if not filtered:
            filtered = [
                ball for ball in balls.values()
                if ball.enabled
                and ball.regime_id in allowed_regimes
            ]

        return filtered

    async def _create_ball_instance(self, player: Player, ball: Ball, interaction: discord.Interaction):
        is_special = random.randint(1, 4096) == 1
        spec = await Special.get(name="Chromatic") if is_special else None

        ball_instance = await BallInstance.create(
            ball=ball,
            player=player,
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            special=spec,
            server_id=interaction.user.guild.id,
        )
        return ball_instance, is_special

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

        # Rarity weights and multipliers
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

        # Reward distributions you gave:
        rewards_by_rarity = {
            "rare": [
                ("powerpoints", 25, 50),
                ("credits", 100, 30),
                ("skin", None, 20),
            ],
            "super_rare": [
                ("powerpoints", 50, 50),
                ("credits", 200, 30),
                ("skin", None, 20),
            ],
            "epic": [
                ("credits", 500, 30),
                ("skin", None, 30),
                ("powerpoints", 100, 40),
            ],
            "mythic": [
                ("credits", 1000, 35),
                ("brawler", None, 40),
                ("skin", None, 25),
            ],
            "legendary": [
                ("brawler", "legendary", 40),
                ("skin", "legendary", 35),
                ("brawler", "ultra_legendary", 5),
                ("skin", "ultimate", 15),
                ("skin", "hypercharged", 5),
            ],
        }

        player.sdcount -= openamount
        await player.save(update_fields=("sdcount",))

        totalcredits = 0
        totalpps = 0

        totalrewards = []
        rarity_names = []

        for i in range(openamount):
            # Pick rarity for this drop
            ounce = random.choices(rarities, weights=normalized_weights, k=1)[0]
            rarity_name = ounce["name"]
            rarity_names.append(rarity_name.replace("_", " ").title())

            # Pick reward type within that rarity
            rewards = rewards_by_rarity[rarity_name]
            reward_types = [r[0] for r in rewards]
            reward_weights = [r[2] for r in rewards]
            reward_choice = random.choices(rewards, weights=reward_weights, k=1)[0]

            reward_type, reward_subtype, _ = reward_choice if len(reward_choice) == 3 else (*reward_choice, None)

            if reward_type in {"brawler", "skin"}:
                # For legendary subtype variants, adjust rarity filter accordingly:
                ball_rarity_name = rarity_name
                if rarity_name == "legendary" and reward_subtype:
                    if reward_subtype in {"legendary", "ultra_legendary"}:
                        ball_rarity_name = "legendary"
                    elif reward_subtype in {"ultimate", "hypercharged"}:
                        ball_rarity_name = rarity_name  # keep legendary, regime_id filter will differentiate skins

                # Get filtered balls of proper rarity and type
                available_balls = self._get_balls_by_rarity_and_type(ball_rarity_name, reward_type)

                if not available_balls:
                    await interaction.followup.send(
                        f"No {reward_type}s available for this Starr Drop rarity.",
                        ephemeral=True
                    )
                    return

                # Retry picking a ball that definitely matches rarity for legendary brawlers (fix mythic bug)
                chosen_ball = None
                if rarity_name == "legendary" and reward_type == "brawler":
                    for _ in range(10):
                        candidate = random.choice(available_balls)
                        if candidate.rarity == self.rarity_levels["legendary"]:
                            chosen_ball = candidate
                            break
                    if not chosen_ball:
                        chosen_ball = available_balls[0]
                else:
                    chosen_ball = random.choice(available_balls)

                ball_instance, is_special = await self._create_ball_instance(player, chosen_ball, interaction)

                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"{rarity_name.replace('_', ' ').title()} Starr Drop",
                        view=view,
                        ephemeral=False
                    )
                    await view.continued.wait()

                    data, file, view_card = await ball_instance.prepare_for_message(interaction)
                    await interaction.edit_original_response(
                        content=f"You opened your {rarity_name.replace('_', ' ').title()} Starr Drop and got... **{'Shiny ' if is_special else ''}{ball_instance.ball.country}**!\n\n{data}",
                        attachments=[file],
                        view=view_card
                    )
                    return  # single open done

                else:
                    # For mass opening collect string with emoji + ball country name
                    emoji = self.bot.get_emoji(ball_instance.ball.emoji_id)
                    totalrewards.append(f"{emoji} **{ball_instance.ball.country}**")
            elif reward_type == "credits":
                amount = reward_subtype if reward_subtype is not None else 100  # default if missing
                totalcredits += amount
                emoji_id = 1364877727601004634 if amount < 40 else 1364877745032794192
                mj = self.bot.get_emoji(emoji_id)

                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"{rarity_name.replace('_', ' ').title()} Starr Drop",
                        view=view,
                        ephemeral=False
                    )
                    await view.continued.wait()

                    await interaction.edit_original_response(
                        content=f"You opened your {rarity_name.replace('_', ' ').title()} Starr Drop and got {mj} **{amount} credits!**",
                    )
                    return
            elif reward_type == "powerpoints":
                amount = reward_subtype if reward_subtype is not None else 25
                totalpps += amount

                if openamount == 1:
                    view = ContinueView(author=interaction.user)
                    await interaction.response.send_message(
                        f"{rarity_name.replace('_', ' ').title()} Starr Drop",
                        view=view,
                        ephemeral=False
                    )
                    await view.continued.wait()

                    await interaction.edit_original_response(
                        content=f"You opened your {rarity_name.replace('_', ' ').title()} Starr Drop and got **{amount} power points!**",
                    )
                    return

        # After all opened
        summary = f"**Opened {openamount} Starr Drops:**\n"
        rarity_count = Counter(rarity_names)
        for r_name, count in rarity_count.items():
            summary += f"\n{r_name} x{count}"

        if totalpps:
            summary += f"\n\n**Power Points:** {totalpps}"
        if totalcredits:
            summary += f"\n\n**Credits:** {totalcredits}"
        if totalrewards:
            summary += "\n\n**Rewards:** " + ", ".join(totalrewards)

        await interaction.response.send_message(summary)


async def setup(bot):
    await bot.add_cog(StarrDrop(bot))
