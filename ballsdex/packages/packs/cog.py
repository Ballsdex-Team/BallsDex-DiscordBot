"""
Pack system for the football players bot.

This module implements a pack opening system where users can:
- Receive packs from admins
- View their pack inventory
- Open packs to receive random players based on rarity weights
"""

import logging
import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, button

from ballsdex.core.models import Ball, BallInstance, Player, UserPacks, RARITY_COLORS, balls
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")


# Pack configuration: defines contents and rarity weights for each pack type
PACK_CONFIG = {
    "common": {
        "count": 3,
        "weights": {"common": 70, "rare": 20, "epic": 8, "legendary": 2},
        "color": RARITY_COLORS["common"],
        "emoji": "📦",
    },
    "rare": {
        "count": 5,
        "weights": {"common": 40, "rare": 35, "epic": 20, "legendary": 5},
        "color": RARITY_COLORS["rare"],
        "emoji": "📦",
    },
    "epic": {
        "count": 7,
        "weights": {"common": 20, "rare": 30, "epic": 40, "legendary": 10},
        "color": RARITY_COLORS["epic"],
        "emoji": "📦",
    },
}


def get_random_player_by_tier(tier: str) -> Ball | None:
    """Get a random player from the given rarity tier."""
    eligible_players = [
        ball for ball in balls.values()
        if ball.enabled and ball.rarity_tier == tier
    ]
    if not eligible_players:
        # Fallback: get any enabled player
        eligible_players = [ball for ball in balls.values() if ball.enabled]
    
    if eligible_players:
        return random.choice(eligible_players)
    return None


def roll_pack(pack_type: str) -> List[Ball]:
    """
    Roll a pack and return the list of players obtained.
    
    Parameters
    ----------
    pack_type: str
        The type of pack to open (common, rare, epic)
    
    Returns
    -------
    List[Ball]
        List of Ball models representing the players obtained
    """
    config = PACK_CONFIG.get(pack_type)
    if not config:
        return []
    
    players = []
    weights = config["weights"]
    tiers = list(weights.keys())
    probabilities = list(weights.values())
    
    for _ in range(config["count"]):
        # Roll for rarity tier
        tier = random.choices(tiers, weights=probabilities, k=1)[0]
        player = get_random_player_by_tier(tier)
        if player:
            players.append(player)
    
    return players


class PackClaimButton(Button):
    """Button to claim a single player from a pack."""
    
    def __init__(self, ball: Ball, index: int, pack_view: "PackOpenView"):
        self.ball = ball
        self.pack_view = pack_view
        color = RARITY_COLORS.get(ball.rarity_tier, RARITY_COLORS["common"])
        
        # Map color to button style
        if ball.rarity_tier == "legendary":
            style = discord.ButtonStyle.danger
        elif ball.rarity_tier == "epic":
            style = discord.ButtonStyle.primary
        elif ball.rarity_tier == "rare":
            style = discord.ButtonStyle.primary
        else:
            style = discord.ButtonStyle.secondary
            
        super().__init__(
            style=style,
            label=f"⚽ {ball.country[:15]}",
            row=index // 4,
        )
    
    async def callback(self, interaction: discord.Interaction["BallsDexBot"]):
        # This button is disabled after pack opening - players are auto-claimed
        await interaction.response.send_message(
            "Players are automatically added to your collection!",
            ephemeral=True
        )


class PackOpenView(View):
    """View for displaying pack opening results."""
    
    def __init__(
        self,
        bot: "BallsDexBot",
        user: discord.User,
        pack_type: str,
        players: List[Ball],
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.user = user
        self.pack_type = pack_type
        self.players = players
        self.claimed = False
        
        # Add info buttons for each player (display only)
        for i, ball in enumerate(players):
            btn = PackClaimButton(ball, i, self)
            btn.disabled = True  # Display only
            self.add_item(btn)
    
    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"], /) -> bool:
        return interaction.user.id == self.user.id
    
    def create_embed(self) -> discord.Embed:
        """Create the pack opening embed."""
        config = PACK_CONFIG[self.pack_type]
        
        embed = discord.Embed(
            title=f"📦 {self.pack_type.title()} Pack Opened!",
            description=f"⚽ You received {len(self.players)} players:",
            color=config["color"],
        )
        
        # Group players by rarity
        rarity_groups = {}
        for ball in self.players:
            tier = ball.rarity_tier
            if tier not in rarity_groups:
                rarity_groups[tier] = []
            rarity_groups[tier].append(ball)
        
        # Add fields for each rarity tier
        tier_order = ["legendary", "epic", "rare", "common"]
        tier_emojis = {
            "legendary": "🌟",
            "epic": "💜",
            "rare": "💙",
            "common": "⚪",
        }
        
        for tier in tier_order:
            if tier in rarity_groups:
                players_list = "\n".join([
                    f"⚽ **{ball.country}** (Rating: {ball.rating})"
                    for ball in rarity_groups[tier]
                ])
                embed.add_field(
                    name=f"{tier_emojis[tier]} {tier.title()}",
                    value=players_list,
                    inline=False,
                )
        
        embed.set_footer(text="Players have been added to your collection!")
        return embed


class Packs(commands.Cog):
    """
    Manage and open player packs.
    """
    
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
    
    @app_commands.command(name="packs")
    async def packs(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        View your pack inventory.
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        user_packs = await UserPacks.get_or_create_for_player(player)
        
        total = user_packs.common_packs + user_packs.rare_packs + user_packs.epic_packs
        
        embed = discord.Embed(
            title="📦 Your Pack Inventory",
            description=f"You have **{total}** packs available to open.",
            color=0x3498DB,
        )
        
        embed.add_field(
            name="⚪ Common Packs",
            value=str(user_packs.common_packs),
            inline=True,
        )
        embed.add_field(
            name="💙 Rare Packs",
            value=str(user_packs.rare_packs),
            inline=True,
        )
        embed.add_field(
            name="💜 Epic Packs",
            value=str(user_packs.epic_packs),
            inline=True,
        )
        
        embed.set_footer(text="Use /open <type> to open a pack!")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="open")
    @app_commands.describe(
        pack_type="The type of pack to open"
    )
    @app_commands.choices(pack_type=[
        app_commands.Choice(name="Common (3 players)", value="common"),
        app_commands.Choice(name="Rare (5 players)", value="rare"),
        app_commands.Choice(name="Epic (7 players)", value="epic"),
    ])
    async def open_pack(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        pack_type: app_commands.Choice[str],
    ):
        """
        Open a pack from your inventory.
        
        Parameters
        ----------
        pack_type: str
            The type of pack to open (common, rare, or epic)
        """
        await interaction.response.defer()
        
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        user_packs = await UserPacks.get_or_create_for_player(player)
        
        pack_name = pack_type.value
        
        # Check if user has the pack
        pack_count = getattr(user_packs, f"{pack_name}_packs", 0)
        if pack_count <= 0:
            await interaction.followup.send(
                f"❌ You don't have any {pack_name} packs! "
                f"Use `/packs` to check your inventory.",
                ephemeral=True,
            )
            return
        
        # Deduct the pack
        setattr(user_packs, f"{pack_name}_packs", pack_count - 1)
        await user_packs.save()
        
        # Roll the pack
        players = roll_pack(pack_name)
        
        if not players:
            await interaction.followup.send(
                "❌ No players are available. Please contact an administrator.",
                ephemeral=True,
            )
            # Refund the pack
            setattr(user_packs, f"{pack_name}_packs", pack_count)
            await user_packs.save()
            return
        
        # Create player instances and add to collection
        bonus_range = settings.max_attack_bonus
        created_instances = []
        
        for ball in players:
            instance = await BallInstance.create(
                ball=ball,
                player=player,
                attack_bonus=random.randint(-bonus_range, bonus_range),
                health_bonus=random.randint(-bonus_range, bonus_range),
            )
            created_instances.append(instance)
        
        # Create and send the pack opening view
        view = PackOpenView(self.bot, interaction.user, pack_name, players)
        embed = view.create_embed()
        
        await interaction.followup.send(embed=embed, view=view)
        
        log.info(
            f"{interaction.user} opened a {pack_name} pack and received "
            f"{len(players)} players"
        )

    @app_commands.command(name="daily")
    async def daily_pack(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim your free daily pack! (Resets every 24 hours)
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        user_packs = await UserPacks.get_or_create_for_player(player)

        # Get current time (timezone-aware)
        now = datetime.now()
        cooldown = timedelta(hours=24)

        # Check if user is on cooldown
        if user_packs.last_daily_claim is not None:
            # Make both datetimes naive for comparison
            last_claim = user_packs.last_daily_claim
            if hasattr(last_claim, 'tzinfo') and last_claim.tzinfo is not None:
                last_claim = last_claim.replace(tzinfo=None)
            
            time_since_claim = now - last_claim
            if time_since_claim < cooldown:
                remaining = cooldown - time_since_claim
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                
                await interaction.response.send_message(
                    f"⏰ You've already claimed your daily pack!\n"
                    f"Come back in **{hours}h {minutes}m**.",
                    ephemeral=True,
                )
                return

        # Roll for random pack type
        pack_weights = {"common": 60, "rare": 30, "epic": 10}
        pack_types = list(pack_weights.keys())
        weights = list(pack_weights.values())
        pack_type = random.choices(pack_types, weights=weights, k=1)[0]
        
        # Grant the random pack
        pack_field = f"{pack_type}_packs"
        current_count = getattr(user_packs, pack_field)
        setattr(user_packs, pack_field, current_count + 1)
        user_packs.last_daily_claim = now
        await user_packs.save()

        pack_emojis = {"common": "⚪", "rare": "💙", "epic": "💜"}
        embed = discord.Embed(
            title="🎁 Daily Pack Claimed!",
            description=f"You received **1x {pack_type.title()} Pack**!\n\nUse `/open {pack_type}` to open it.",
            color=RARITY_COLORS[pack_type],
        )
        embed.add_field(
            name=f"{pack_emojis[pack_type]} Your {pack_type.title()} Packs",
            value=str(getattr(user_packs, pack_field)),
            inline=True,
        )
        embed.set_footer(text="Come back tomorrow for another free pack!")

        await interaction.response.send_message(embed=embed)
        log.info(f"{interaction.user} claimed their daily pack ({pack_type})")

    @app_commands.command(name="weekly")
    async def weekly_pack(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim your free weekly pack! (Resets every 7 days)
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        user_packs = await UserPacks.get_or_create_for_player(player)

        # Get current time
        now = datetime.now()
        cooldown = timedelta(days=7)

        # Check if user is on cooldown
        if user_packs.last_weekly_claim is not None:
            # Make both datetimes naive for comparison
            last_claim = user_packs.last_weekly_claim
            if hasattr(last_claim, 'tzinfo') and last_claim.tzinfo is not None:
                last_claim = last_claim.replace(tzinfo=None)
            
            time_since_claim = now - last_claim
            if time_since_claim < cooldown:
                remaining = cooldown - time_since_claim
                days = remaining.days
                hours, remainder = divmod(int(remaining.seconds), 3600)
                minutes, _ = divmod(remainder, 60)
                
                await interaction.response.send_message(
                    f"⏰ You've already claimed your weekly pack!\n"
                    f"Come back in **{days}d {hours}h {minutes}m**.",
                    ephemeral=True,
                )
                return

        # Roll for random pack type (better odds than daily!)
        pack_weights = {"common": 30, "rare": 45, "epic": 25}
        pack_types = list(pack_weights.keys())
        weights = list(pack_weights.values())
        pack_type = random.choices(pack_types, weights=weights, k=1)[0]
        
        # Grant the random pack
        pack_field = f"{pack_type}_packs"
        current_count = getattr(user_packs, pack_field)
        setattr(user_packs, pack_field, current_count + 1)
        user_packs.last_weekly_claim = now
        await user_packs.save()

        pack_emojis = {"common": "⚪", "rare": "💙", "epic": "💜"}
        embed = discord.Embed(
            title="🎁 Weekly Pack Claimed!",
            description=f"You received **1x {pack_type.title()} Pack**!\n\nUse `/open {pack_type}` to open it.",
            color=RARITY_COLORS[pack_type],
        )
        embed.add_field(
            name=f"{pack_emojis[pack_type]} Your {pack_type.title()} Packs",
            value=str(getattr(user_packs, pack_field)),
            inline=True,
        )
        embed.set_footer(text="Come back next week for another free pack!")

        await interaction.response.send_message(embed=embed)
        log.info(f"{interaction.user} claimed their weekly pack ({pack_type})")

