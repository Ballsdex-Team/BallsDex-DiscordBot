import logging
import random
import sys
from typing import TYPE_CHECKING, Dict
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands

import asyncio
import io

from ballsdex.core.models import (
    Ball,
    BallInstance,
    Player,
)
from ballsdex.core.models import balls as countryballs
from ballsdex.settings import settings

from ballsdex.core.utils.transformers import (
    BallInstanceTransform,
    BallTransform
)

from ballsdex.packages.battle.xe_battle_lib import (
    BattleBall,
    BattleInstance,
    Ability,
    define_abilities,
    gen_battle,
)

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
log = logging.getLogger("ballsdex.packages.battle")


@dataclass
class GuildBattle:
    author: discord.Member
    opponent: discord.Member
    author_ready: bool = False
    opponent_ready: bool = False
    battle: BattleInstance = field(default_factory=BattleInstance)
    current_turn: discord.Member = None  # Track whose turn it is
    battle_message: discord.Message = None  # Store the battle embed message
    author_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)  # Stats for author's balls
    opponent_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)  # Stats for opponent's balls
    author_deck: list = field(default_factory=list)  # Store author's deck
    opponent_deck: list = field(default_factory=list)  # Store opponent's deck

def gen_deck(balls) -> str:
    """Generates a text representation of the player's deck."""
    if not balls:
        return "No balls added yet. Use `/battle add` to add your balls."
    deck = "\n".join(
        [
            f"- {ball.emoji} {ball.name} (HP: {ball.health} | DMG: {ball.attack})\n"
            f"  Ability: {', '.join(f'{ability.name} (Uses: {"Infinite" if ability.max_uses == -1 else ability.max_uses})' for ability in ball.abilities) if ball.abilities else 'None'}"
            for ball in balls
        ]
    )
    if len(deck) > 1024:
        return deck[0:951] + '\n<truncated due to discord limits, the rest of your balls are still here>'
    return deck

def create_disabled_buttons() -> discord.ui.View:
    """Creates a view with disabled start and cancel buttons."""
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.success, emoji="✔", label="Ready", disabled=True
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.danger, emoji="✖", label="Cancel", disabled=True
        )
    )


class Battle(commands.GroupCog):
    """
    Battle your countryballs!
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.battles: Dict[int, GuildBattle] = {}
        self.interactions: Dict[int, discord.Interaction] = {}

    bulk = app_commands.Group(
        name='bulk', description='Bulk commands for battle'
    )

    async def start_battle(self, interaction: discord.Interaction):
        guild_battle = self.battles.get(interaction.guild_id)
        if not guild_battle or interaction.user not in (
            guild_battle.author,
            guild_battle.opponent,
        ):
            await interaction.response.send_message(
                "You aren't a part of this battle.", ephemeral=True
            )
            return
    
        # Defer the interaction to prevent it from expiring
        await interaction.response.defer()
    
        if interaction.user == guild_battle.author:
            guild_battle.author_ready = True
        elif interaction.user == guild_battle.opponent:
            guild_battle.opponent_ready = True
    
        # Update the first battle embed to show the checkmark
        await self.update_first_battle_embed(interaction, guild_battle)
    
        if guild_battle.author_ready and guild_battle.opponent_ready:
            if not (guild_battle.battle.p1_balls and guild_battle.battle.p2_balls):
                await interaction.followup.send(
                    f"Both players must add {settings.collectible_name}!"
                )
                return
    
            # Save the decks for both players
            guild_battle.author_deck = [ball for ball in guild_battle.battle.p1_balls]
            guild_battle.opponent_deck = [ball for ball in guild_battle.battle.p2_balls]
    
            # Initialize default stats for all balls in both decks
            for ball in guild_battle.author_deck:
                guild_battle.author_stats.setdefault(ball.name, {"damage": 0, "kills": 0, "deaths": 0})
            for ball in guild_battle.opponent_deck:
                guild_battle.opponent_stats.setdefault(ball.name, {"damage": 0, "kills": 0, "deaths": 0})
    
            # Send a new embed for the main battle
            battle_message = await interaction.followup.send(
                embed=discord.Embed(
                    title=f"⚔️ {settings.collectible_name.title()} Battle Begins!",
                    description="The battle is starting! Good luck!",
                    color=discord.Color.blurple(),
                )
            )
            guild_battle.battle_message = battle_message  # Store the message for updates
    
            await self.start_main_battle(interaction, guild_battle)
        else:
            await interaction.followup.send(
                f"Done! Waiting for the other player to press `Ready`.", ephemeral=True
            )

    async def update_first_battle_embed(self, interaction: discord.Interaction, guild_battle: GuildBattle):
        """Update the first battle embed to show readiness status."""
        embed = discord.Embed(
            title=f"⚔️ {settings.collectible_name.title()} Battle Challenge!",
            description=(
                f"{guild_battle.author.mention} has challenged {guild_battle.opponent.mention} to a battle!\n\n"
                f"**Instructions:**\n"
                f"1. Use `/battle add` to add your {settings.collectible_name} to your deck.\n"
                f"2. Once both players are ready, click the **Ready** button to start the battle.\n"
                f"3. You can cancel the battle at any time using the **Cancel** button.\n\n"
                f"Good luck, and may the best {settings.collectible_name} trainer win! 🎉"
            ),
            color=discord.Color.gold(),
        )
        # Add checkmarks next to players who are ready
        author_status = "✅" if guild_battle.author_ready else "⬜"
        opponent_status = "✅" if guild_battle.opponent_ready else "⬜"
    
        embed.add_field(
            name=f"{guild_battle.author.display_name}'s Deck {author_status}",
            value=gen_deck(guild_battle.battle.p1_balls),
            inline=True,
        )
        embed.add_field(
            name=f"{guild_battle.opponent.display_name}'s Deck {opponent_status}",
            value=gen_deck(guild_battle.battle.p2_balls),
            inline=True,
        )
        embed.set_footer(text="Waiting for both players to get ready...")
    
        # Update the first battle embed
        if guild_battle.battle_message:
            await guild_battle.battle_message.edit(embed=embed)
        else:
            log.error("Battle message not found. Unable to update the embed.")

    async def start_main_battle(self, interaction: discord.Interaction, guild_battle: GuildBattle):
        # Randomly determine the first turn
        players = [guild_battle.author, guild_battle.opponent]
        random.shuffle(players)
        guild_battle.current_turn = players[0]  # First player in the shuffled list gets the first turn
    
        # Determine the active ball and the opponent's ball
        active_ball = guild_battle.battle.p1_balls[0] if guild_battle.current_turn == guild_battle.author else guild_battle.battle.p2_balls[0]
        opponent_ball = guild_battle.battle.p2_balls[0] if guild_battle.current_turn == guild_battle.author else guild_battle.battle.p1_balls[0]

        # Trigger passive abilities for the active ball
        '''
        for ability in active_ball.abilities:
            if ability.is_passive and ability.trigger == "on_battlefield":
                # Apply the ability's effect
                ability.logic(active_ball, opponent_ball)  # Pass the correct defender
                # Log the ability's effect
                guild_battle.battle.battle_log.append(
                    f"{active_ball.emoji} {active_ball.name}'s ability `{ability.name}` triggered: {ability.description}"
                )

        # Trigger passive abilities for the opponent's ball
        for ability in opponent_ball.abilities:
            if ability.is_passive and ability.trigger == "on_battlefield":
                # Apply the ability's effect
                ability.logic(opponent_ball, active_ball)  # Pass the correct defender
                # Log the ability's effect
                guild_battle.battle.battle_log.append(
                    f"{opponent_ball.emoji} {opponent_ball.name}'s ability `{ability.name}` triggered: {ability.description}"
                )
        '''
        guild_battle.battle.battle_log.append(f"**{guild_battle.current_turn.display_name}**")
    
        # Check for user-initiated abilities
        user_initiated_abilities = [
            ability for ability in active_ball.abilities if not ability.is_passive and ability.trigger == "user_initiated"
        ]
    
        # Create the embed
        embed = discord.Embed(
            title=f"⚔️ {settings.collectible_name.title()} Battle Begins!",
            description=f"{guild_battle.author.mention} vs {guild_battle.opponent.mention}",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name=f"{guild_battle.author.display_name}'s Ball",
            value=f"{guild_battle.battle.p1_balls[0].name} (HP: {guild_battle.battle.p1_balls[0].health}, ATK: {guild_battle.battle.p1_balls[0].attack})",
            inline=True,
        )
        embed.add_field(
            name=f"{guild_battle.opponent.display_name}'s Ball",
            value=f"{opponent_ball.name} (HP: {opponent_ball.health}, ATK: {opponent_ball.attack})",
            inline=True,
        )
    
        embed.add_field(
            name="Battle Log",
            value="The battle has begun!",
            inline=False,
        )

        # Include ability usage in the embed if user-initiated abilities exist
        if user_initiated_abilities:
            abilities_text = "\n".join(
                f"- `{ability.name}`: {ability.description} "
                f"({'Unlimited uses' if ability.max_uses == -1 else f'{ability.max_uses - ability.uses}/{ability.max_uses} uses left'})"
                for ability in user_initiated_abilities
            )
        else:
            abilities_text = "No abilities available."
        embed.add_field(
            name=f"{active_ball.name}'s Abilities",
            value=abilities_text,
            inline=False,
        )
    
        embed.set_footer(text=f"It is {guild_battle.current_turn.display_name}'s turn.")
    
        # Create buttons
        attack_button = discord.ui.Button(style=discord.ButtonStyle.primary, label="Attack")
        use_ability_button = discord.ui.Button(style=discord.ButtonStyle.success, label="Use Ability")
        switch_button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Switch Ball")
        forfeit_button = discord.ui.Button(style=discord.ButtonStyle.danger, label="Forfeit")
    
        # Set button callbacks
        attack_button.callback = self.attack
        use_ability_button.callback = self.use_ability
        switch_button.callback = self.switch_ball
        forfeit_button.callback = self.forfeit
    
        # Create the view
        view = discord.ui.View(timeout=120)
        view.add_item(attack_button)
        view.add_item(use_ability_button)
        view.add_item(switch_button)
        view.add_item(forfeit_button)
    
        # Edit the new battle embed
        await guild_battle.battle_message.edit(embed=embed, view=view)

    async def attack(self, interaction: discord.Interaction):
        guild_battle = self.battles.get(interaction.guild_id)
        
        # Save the decks if not already saved
        if not guild_battle.author_deck:
            guild_battle.author_deck = [ball for ball in guild_battle.battle.p1_balls]
        if not guild_battle.opponent_deck:
            guild_battle.opponent_deck = [ball for ball in guild_battle.battle.p2_balls]
        
        if not guild_battle:
            await interaction.response.send_message("No battle is currently ongoing.", ephemeral=True)
            return
    
        if interaction.user != guild_battle.current_turn:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return
    
        # Determine attacker and defender
        if guild_battle.current_turn == guild_battle.author:
            attacker = guild_battle.battle.p1_balls[0]
            defender = guild_battle.battle.p2_balls[0]
        else:
            attacker = guild_battle.battle.p2_balls[0]
            defender = guild_battle.battle.p1_balls[0]
    
        # Check if the attacker is stunned
        if getattr(attacker, "stunned", 0) > 0:
            guild_battle.battle.battle_log.append(
                f"{attacker.emoji} {attacker.name} is stunned and cannot attack this turn!"
            )
            setattr(attacker, "stunned", getattr(attacker, "stunned") - 1)
            await self.update_battle_embed(interaction, guild_battle)
            return

        # Check if the defender's health triggers any passive abilities
        for ability in defender.abilities:
            if ability.is_passive and ability.trigger == "on_health" and defender.health <= ability.trigger_threshold:
                # Apply the ability's effect
                ability.logic(defender, guild_battle)
                # Log the ability's effect
                guild_battle.battle.battle_log.append(
                    f"{defender.emoji} {defender.name}'s ability `{ability.name}` triggered: {ability.description}"
                )

        # Check if the attacker is missing
        if getattr(attacker, "disappeared", False):
            guild_battle.battle.battle_log.append(
                f"{interaction.user.display_name}'s {attacker.emoji} {attacker.name} is disappeared and couldn't do anything!"
            )
            # Automatically end the turn
            guild_battle.current_turn = (
                guild_battle.author if guild_battle.current_turn == guild_battle.opponent else guild_battle.opponent
            )
            guild_battle.battle.battle_log.append(f"**{guild_battle.current_turn.display_name}**")
            await self.update_battle_embed(interaction, guild_battle)
            return
    
        # Check if the defender is missing
        if getattr(defender, "disappeared", False):
            guild_battle.battle.battle_log.append(
                f"{defender.emoji} {defender.name} is currently missing and cannot be attacked!"
            )
            await self.update_battle_embed(interaction, guild_battle)
            return
    
        # Calculate random damage
        damage = random.randint(100, attacker.attack)
        defender.health -= damage
    
        # Update the battle log
        guild_battle.battle.battle_log.append(
            f"{interaction.user.display_name}'s {attacker.emoji} {attacker.name} dealt {damage} damage to {defender.emoji} {defender.name}!"
        )
        # Determine the stats dictionaries for the attacker and defender
        if guild_battle.current_turn == guild_battle.author:
            attacker_stats = guild_battle.author_stats
            defender_stats = guild_battle.opponent_stats
        else:
            attacker_stats = guild_battle.opponent_stats
            defender_stats = guild_battle.author_stats
        
        # Initialize stats for attacker and defender if not already present
        attacker_stats.setdefault(attacker.name, {"damage": 0, "kills": 0, "deaths": 0})
        defender_stats.setdefault(defender.name, {"damage": 0, "kills": 0, "deaths": 0})
        
        # Update stats
        attacker_stats[attacker.name]["damage"] += damage
        
        # Check if the defender's ball is defeated
        if defender.health <= 0:
            attacker_stats[attacker.name]["kills"] += 1
            defender_stats[defender.name]["deaths"] += 1
            defender.health = 0  # Ensure health does not go below 0
            guild_battle.battle.battle_log.append(f"{defender.emoji} {defender.name} has been defeated!")
            if guild_battle.current_turn == guild_battle.author:
                guild_battle.battle.p2_balls.pop(0)
            else:
                guild_battle.battle.p1_balls.pop(0)
    
        # Check for victory
        if not guild_battle.battle.p1_balls or not guild_battle.battle.p2_balls:
            winner = guild_battle.author if guild_battle.battle.p1_balls else guild_battle.opponent
            guild_battle.battle.battle_log.append(f"{winner.display_name} wins the battle!")
            await self.update_battle_embed(interaction, guild_battle, winner=winner)
            del self.battles[interaction.guild_id]
            return
    
        # Switch turns
        guild_battle.current_turn = (
            guild_battle.author if guild_battle.current_turn == guild_battle.opponent else guild_battle.opponent
        )
    
        # Add a new line with the player's name to the battle log
        guild_battle.battle.battle_log.append(f"**{guild_battle.current_turn.display_name}**")
    
        # Defer the interaction and update the battle embed
        await interaction.response.defer()
        await self.update_battle_embed(interaction, guild_battle)

    async def switch_ball(self, interaction: discord.Interaction):
        guild_battle = self.battles.get(interaction.guild_id)
        if not guild_battle:
            await interaction.response.send_message("No battle is currently ongoing.", ephemeral=True)
            return
    
        if interaction.user != guild_battle.current_turn:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return
    
        # Determine the player's balls
        if guild_battle.current_turn == guild_battle.author:
            player_balls = guild_battle.battle.p1_balls
        else:
            player_balls = guild_battle.battle.p2_balls
    
        # Check if there are other balls to switch to
        if len(player_balls) <= 1:
            await interaction.response.send_message("You have no other balls to switch to!", ephemeral=True)
            return
    
        # Create a dropdown menu for selecting a ball to switch to
        class BallSelect(discord.ui.Select):
            def __init__(self, battle_instance):
                self.battle_instance = battle_instance  # Reference to the Battle instance
                options = [
                    discord.SelectOption(label=f"{ball.name}", description=f"HP: {ball.health}, ATK: {ball.attack}")
                    for ball in player_balls[1:]  # Exclude the currently active ball
                ]
                super().__init__(placeholder="Choose a ball to switch to...", options=options)
    
            async def callback(self, select_interaction: discord.Interaction):
                # Find the selected ball
                selected_ball_name = self.values[0]  # The name of the selected ball
                selected_ball_index = next(
                    (i for i, ball in enumerate(player_balls) if ball.name == selected_ball_name), None
                )
    
                if selected_ball_index is not None:
                    # Move the selected ball to the front of the list
                    player_balls.insert(0, player_balls.pop(selected_ball_index))
    
                    # Update the battle log
                    guild_battle.battle.battle_log.append(
                        f"{interaction.user.display_name} switched to {player_balls[0].emoji} {player_balls[0].name}!"                    )
    
                    # End the player's turn by switching to the other player
                    guild_battle.current_turn = (
                        guild_battle.author if guild_battle.current_turn == guild_battle.opponent else guild_battle.opponent
                    )
    
                    # Add a new line with the player's name to the battle log
                    guild_battle.battle.battle_log.append(f"**{guild_battle.current_turn.display_name}**")
    
                    # Update the battle embed using the Battle instance
                    await select_interaction.response.edit_message(view=None)  # Remove the dropdown menu
                    await self.battle_instance.update_battle_embed(select_interaction, guild_battle)
    
        # Create a view with the dropdown menu
        view = discord.ui.View()
        view.add_item(BallSelect(self))  # Pass the Battle instance to BallSelect
    
        # Send the dropdown menu to the user
        await interaction.response.send_message("Select a ball to switch to:", view=view, ephemeral=True)

    async def forfeit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild_battle = self.battles.get(interaction.guild_id)
        if not guild_battle:
            await interaction.response.send_message("No battle is currently ongoing.", ephemeral=True)
            return
    
        if interaction.user not in (guild_battle.author, guild_battle.opponent):
            await interaction.response.send_message("You aren't a part of this battle!", ephemeral=True)
            return
    
        # Determine the winner
        winner = (
            guild_battle.opponent
            if interaction.user == guild_battle.author
            else guild_battle.author
        )
    
        # Update the battle log
        guild_battle.battle.battle_log.append(
            f"{interaction.user.display_name} has forfeited the battle! {winner.display_name} wins!"
        )
    
        # Send the winner embed
        await self.update_battle_embed(interaction, guild_battle, winner=winner)
    
        # Clean up the battle
        del self.battles[interaction.guild_id]

    async def use_ability(self, interaction: discord.Interaction):
        guild_battle = self.battles.get(interaction.guild_id)
        if not guild_battle:
            await interaction.response.send_message("No battle is currently ongoing.", ephemeral=True)
            return
    
        if interaction.user != guild_battle.current_turn:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return
    
        # Determine the active ball
        if guild_battle.current_turn == guild_battle.author:
            active_ball = guild_battle.battle.p1_balls[0]
            opponent_ball = guild_battle.battle.p2_balls[0]
        else:
            active_ball = guild_battle.battle.p2_balls[0]
            opponent_ball = guild_battle.battle.p1_balls[0]
    
        # Check if the active ball has user-initiated abilities
        user_initiated_abilities = [
            ability for ability in active_ball.abilities if not ability.is_passive and ability.trigger == "user_initiated"
        ]
    
        if not user_initiated_abilities:
            await interaction.response.send_message("Your active ball has no user-initiated abilities.", ephemeral=True)
            return
    
        # Use the first user-initiated ability
        selected_ability = user_initiated_abilities[0]
    
        # Check if the ability has remaining uses
        if selected_ability.max_uses != -1 and selected_ability.uses >= selected_ability.max_uses:
            await interaction.response.send_message(
                f"The ability `{selected_ability.name}` has no remaining uses!", ephemeral=True
            )
            return
    
        # Increment the usage counter
        selected_ability.uses += 1
    
        # Apply the ability logic
        selected_ability.logic(active_ball, opponent_ball)
    
        # Add the ability usage to the battle log
        if selected_ability.max_uses != -1:
            remaining_uses = f"`({selected_ability.max_uses - selected_ability.uses}/{selected_ability.max_uses}` uses left)"
        
        guild_battle.battle.battle_log.append(
            f"{active_ball.emoji} {active_ball.name} used `{selected_ability.name}`!"
        )
        guild_battle.battle.battle_log.append(selected_ability.activation_message)
    
        # Check if the ability ends the turn
        if selected_ability.ends_turn:
            # Switch turns
            guild_battle.current_turn = (
                guild_battle.author if guild_battle.current_turn == guild_battle.opponent else guild_battle.opponent
            )
            guild_battle.battle.battle_log.append(f"**{guild_battle.current_turn.display_name}**")
    
        # Acknowledge the interaction by deferring it
        await interaction.response.defer()
    
        # Update the battle embed
        await self.update_battle_embed(interaction, guild_battle)

    async def update_battle_embed(self, interaction: discord.Interaction, guild_battle: GuildBattle, winner: discord.Member = None):
        if winner:
            # Set default stats for all balls in both players' decks
            for ball in guild_battle.author_deck:
                guild_battle.author_stats.setdefault(ball.name, {"damage": 0, "kills": 0, "deaths": 0})
            for ball in guild_battle.opponent_deck:
                guild_battle.opponent_stats.setdefault(ball.name, {"damage": 0, "kills": 0, "deaths": 0})
        
            # Combine stats from both sides
            combined_stats = {**guild_battle.author_stats, **guild_battle.opponent_stats}
        
            # Find the MVP based on the highest damage
            if combined_stats:
                mvp_ball, mvp_stats = max(combined_stats.items(), key=lambda item: item[1]["damage"], default=(None, None))
                if mvp_ball in guild_battle.author_stats:
                    mvp_owner = guild_battle.author
                elif mvp_ball in guild_battle.opponent_stats:
                    mvp_owner = guild_battle.opponent
                else:
                    mvp_owner = winner  # Default to the winner if no stats are available
            else:
                # Default to the first ball of the winner's deck if no stats are available
                winner_balls = guild_battle.battle.p1_balls if winner == guild_battle.author else guild_battle.battle.p2_balls
                if winner_balls:
                    mvp_ball = winner_balls[0].name
                    mvp_stats = {"damage": 0, "kills": 0, "deaths": 0}
                else:
                    mvp_ball = None
                    mvp_stats = None
        
            # Create the winner embed
            embed = discord.Embed(
                title=f"🏆 {settings.collectible_name.title()} Battle Over!",
                description=f"{winner.mention} is the winner! 🎉",
                color=discord.Color.green(),
            )
        
            if mvp_ball:
                # Retrieve the actual BattleBall object for the MVP ball
                all_balls = guild_battle.battle.p1_balls + guild_battle.battle.p2_balls
                mvp_ball_obj = next((ball for ball in all_balls if ball.name == mvp_ball), None)
        
                if mvp_ball_obj:
                    embed.add_field(
                        name="MVP Ball (Most Damage)",
                        value=(
                            f"{mvp_owner.mention}'s {mvp_ball_obj.emoji} **{mvp_ball_obj.name}** "
                            f"(Damage Done: **{mvp_stats['damage']}**)"
                        ),
                        inline=False,
                    )
            else:
                embed.add_field(
                    name="MVP Ball",
                    value=f"No MVP ball. {winner.mention} wins by default!",
                    inline=False,
                )
            
            def format_stats(stats, all_balls):
                def find_emoji(ball_name):
                    # Normalize ball names for comparison
                    normalized_name = ball_name.strip().lower()
                    return next(
                        (b.emoji for b in all_balls if b.name.strip().lower() == normalized_name),
                        '❓'  # Default to question mark if no match is found
                    )
            
                return "\n".join(
                    f"{find_emoji(ball)} **{ball}**\n"
                    f"  Damage: **{data['damage']}** | Kills: **{data['kills']}** | Deaths: **{data['deaths']}**"
                    for ball, data in stats.items()
                )
            
            all_balls = guild_battle.battle.p1_balls + guild_battle.battle.p2_balls
            
            embed.add_field(
                name=f"{guild_battle.author.display_name}'s Ball Stats",
                value=format_stats(guild_battle.author_stats, all_balls) or "No stats available.",
                inline=True,
            )
            embed.add_field(
                name=f"{guild_battle.opponent.display_name}'s Ball Stats",
                value=format_stats(guild_battle.opponent_stats, all_balls) or "No stats available.",
                inline=True,
            )
    
            embed.set_footer(text="The battle has concluded. Thanks for playing!")
    
            # Disable all buttons
            view = discord.ui.View()
            for row in interaction.message.components:
                for button in row.children:
                    if isinstance(button, discord.ui.Button):
                        button.disabled = True
                        view.add_item(button)
    
            # Update the battle message
            if guild_battle.battle_message:
                await guild_battle.battle_message.edit(embed=embed)
            else:
                log.error("Battle message not found. Unable to update the embed.")
            return
    
        # Determine if this is the first battle embed or the main battle embed
        is_main_battle_embed = guild_battle.author_ready and guild_battle.opponent_ready

        if is_main_battle_embed:
            # Determine the active ball and opponent ball based on the current turn
            if guild_battle.current_turn == guild_battle.author:
                active_ball = guild_battle.battle.p1_balls[0] if guild_battle.battle.p1_balls else None
                opponent_ball = guild_battle.battle.p2_balls[0] if guild_battle.battle.p2_balls else None
            else:
                active_ball = guild_battle.battle.p2_balls[0] if guild_battle.battle.p2_balls else None
                opponent_ball = guild_battle.battle.p1_balls[0] if guild_battle.battle.p1_balls else None

            # Trigger passive abilities for the active ball
            for ability in active_ball.abilities:
                if ability.is_passive and ability.trigger == "on_battlefield":
                    ability.logic(active_ball, opponent_ball)
                    guild_battle.battle.battle_log.append(
                        f"{active_ball.emoji} {active_ball.name}'s ability `{ability.name}` triggered: {ability.description}"
                    )
            
            # Trigger passive abilities for the opponent's ball
            for ability in opponent_ball.abilities:
                if ability.is_passive and ability.trigger == "on_battlefield":
                    ability.logic(opponent_ball, active_ball)
                    guild_battle.battle.battle_log.append(
                        f"{opponent_ball.emoji} {opponent_ball.name}'s ability `{ability.name}` triggered: {ability.description}"
                    )

            # Main battle embed creation logic
            active_ball = guild_battle.battle.p1_balls[0] if guild_battle.current_turn == guild_battle.author else guild_battle.battle.p2_balls[0]
            user_initiated_abilities = [
                ability for ability in active_ball.abilities if not ability.is_passive and ability.trigger == "user_initiated"
            ]

            # Create buttons
            attack_button = discord.ui.Button(style=discord.ButtonStyle.primary, label="Attack")
            use_ability_button = discord.ui.Button(style=discord.ButtonStyle.success, label="Use Ability")
            switch_button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Switch Ball")
            forfeit_button = discord.ui.Button(style=discord.ButtonStyle.danger, label="Forfeit")

            # Set button callbacks
            attack_button.callback = self.attack
            use_ability_button.callback = self.use_ability
            switch_button.callback = self.switch_ball
            forfeit_button.callback = self.forfeit

            # Create the view
            view = discord.ui.View(timeout=120)
            view.add_item(attack_button)
            view.add_item(use_ability_button)
            view.add_item(switch_button)
            view.add_item(forfeit_button)

            # Main battle embed content
            embed = discord.Embed(
                title=f"⚔️ {settings.collectible_name.title()} Battle Begins!",
                description=f"{guild_battle.author.mention} vs {guild_battle.opponent.mention}",
                color=discord.Color.blurple(),
            )
            embed.add_field(
                name=f"{guild_battle.author.display_name}'s Ball",
                value=f"{active_ball.emoji} {active_ball.name} (HP: {active_ball.health}, ATK: {active_ball.attack})",
                inline=True,
            )
            embed.add_field(
                name=f"{guild_battle.opponent.display_name}'s Ball",
                value=f"{opponent_ball.emoji} {opponent_ball.name} (HP: {opponent_ball.health}, ATK: {opponent_ball.attack})",
                inline=True,
            )
            embed.add_field(
                name="Battle Log",
                value="\n".join(guild_battle.battle.battle_log[-5:]) or "No actions yet.",
                inline=False,
            )

            # Include ability usage in the embed if user-initiated abilities exist
            if user_initiated_abilities:
                abilities_text = "\n".join(
                    f"- `{ability.name}`: {ability.description} "
                    f"({'Unlimited uses' if ability.max_uses == -1 else f'{ability.max_uses - ability.uses}/{ability.max_uses} uses left'})"
                    for ability in user_initiated_abilities
                )
            else:
                abilities_text = "No abilities available."

            embed.add_field(
                name=f"{active_ball.name}'s Abilities",
                value=abilities_text,
                inline=False,
            )

            # Set footer with the current player's turn
            embed.set_footer(text=f"It is {guild_battle.current_turn.display_name}'s turn.")

            # Update the main battle embed
            if guild_battle.battle_message:
                await guild_battle.battle_message.edit(embed=embed, view=view)
            else:
                log.error("Battle message not found. Unable to update the embed.")
        else:
            # First battle embed logic (unchanged)
            embed = discord.Embed(
                title=f"⚔️ {settings.collectible_name.title()} Battle Challenge!",
                description=(
                    f"{guild_battle.author.mention} has challenged {guild_battle.opponent.mention} to a battle!\n\n"
                    f"**Instructions:**\n"
                    f"1. Use `/battle add` to add your {settings.collectible_name} to your deck.\n"
                    f"2. Once both players are ready, click the **Ready** button to start the battle.\n"
                    f"3. You can cancel the battle at any time using the **Cancel** button.\n\n"
                    f"Good luck, and may the best {settings.collectible_name} trainer win! 🎉"
                ),
                color=discord.Color.gold(),
            )
            # Add checkmarks next to players who are ready
            author_status = "✅" if guild_battle.author_ready else "⬜"
            opponent_status = "✅" if guild_battle.opponent_ready else "⬜"

            embed.add_field(
                name=f"{guild_battle.author.display_name}'s Deck {author_status}",
                value=gen_deck(guild_battle.battle.p1_balls),
                inline=True,
            )
            embed.add_field(
                name=f"{guild_battle.opponent.display_name}'s Deck {opponent_status}",
                value=gen_deck(guild_battle.battle.p2_balls),
                inline=True,
            )
            embed.set_footer(text="Waiting for both players to get ready...")

            # Update the first battle embed
            if guild_battle.battle_message:
                await guild_battle.battle_message.edit(embed=embed)
            else:
                log.error("Battle message not found. Unable to update the embed.")

    async def cancel_battle(self, interaction: discord.Interaction):
        guild_battle = self.battles.get(interaction.guild_id)
    
        if interaction.user not in (guild_battle.author, guild_battle.opponent):
            await interaction.response.send_message(
                "You aren't a part of this battle!", ephemeral=True
            )
            return
    
        if guild_battle:
            # Create the themed embed for canceled battle
            embed = discord.Embed(
                title=f"⚔️ {settings.collectible_name.title()} Battle Cancelled!",
                description=(
                    f"The battle between {guild_battle.author.mention} and {guild_battle.opponent.mention} has been cancelled.\n\n"
                    f"**Summary:**\n"
                    f"- {guild_battle.author.display_name}'s Deck: {gen_deck(guild_battle.battle.p1_balls)}\n"
                    f"- {guild_battle.opponent.display_name}'s Deck: {gen_deck(guild_battle.battle.p2_balls)}\n\n"
                    f"Better luck next time! ✖"
                ),
                color=discord.Color.red(),  # Keep the red color for cancellation
            )
            embed.add_field(
                name=f"{guild_battle.author.display_name}'s Deck",
                value=gen_deck(guild_battle.battle.p1_balls),
                inline=True,
            )
            embed.add_field(
                name=f"{guild_battle.opponent.display_name}'s Deck",
                value=gen_deck(guild_battle.battle.p2_balls),
                inline=True,
            )
            embed.set_footer(text="The battle has been cancelled.")
    
            # Create a view with disabled buttons
            view = create_disabled_buttons()
    
            try:
                await interaction.response.defer()
            except discord.errors.InteractionResponded:
                pass
            await interaction.message.edit(embed=embed, view=view)
            self.battles[interaction.guild_id] = None

    @app_commands.command()
    async def start(self, interaction: discord.Interaction, opponent: discord.Member):
        """
        Start a battle with a chosen user.
        """
        if self.battles.get(interaction.guild_id):
            await interaction.response.send_message(
                "A battle is already ongoing in this server. Please wait for it to finish before starting a new one.",
                ephemeral=True,
            )
            return
    
        # Initialize the battle instance
        guild_battle = GuildBattle(
            author=interaction.user, opponent=opponent
        )
        self.battles[interaction.guild_id] = guild_battle
    
        # Create the embed
        embed = discord.Embed(
            title=f"⚔️ {settings.collectible_name.title()} Battle Challenge!",
            description=(
                f"{interaction.user.mention} has challenged {opponent.mention} to a battle!\n\n"
                f"**Instructions:**\n"
                f"1. Use `/battle add` to add your {settings.collectible_name} to your deck.\n"
                f"2. Once both players are ready, click the **Ready** button to start the battle.\n"
                f"3. You can cancel the battle at any time using the **Cancel** button.\n\n"
                f"Good luck, and may the best {settings.collectible_name} trainer win! 🎉"
            ),
            color=discord.Color.gold(),
        )
        embed.add_field(
            name=f"{interaction.user.display_name}'s Deck ⬜",
            value="No balls added yet. Use `/battle add` to add your balls.",
            inline=True,
        )
        embed.add_field(
            name=f"{opponent.display_name}'s Deck ⬜",
            value="No balls added yet. Use `/battle add` to add your balls.",
            inline=True,
        )
        embed.set_footer(text="Waiting for both players to get ready...")
    
        # Create the buttons
        start_button = discord.ui.Button(
            style=discord.ButtonStyle.success, emoji="✔", label="Ready"
        )
        cancel_button = discord.ui.Button(
            style=discord.ButtonStyle.danger, emoji="✖", label="Cancel"
        )
    
        # Set button callbacks
        start_button.callback = self.start_battle
        cancel_button.callback = self.cancel_battle
    
        # Create the view
        view = discord.ui.View(timeout=None)
        view.add_item(start_button)
        view.add_item(cancel_button)
    
        # Send the interaction response and store the message
        battle_message = await interaction.response.send_message(
            content=f"{opponent.mention}, {interaction.user.mention} is threatening to make your balls go missing!",
            embed=embed,
            view=view,
        )
        guild_battle.battle_message = await interaction.original_response()  # Store the message for updates
    
        # Store the interaction for later updates
        self.interactions[interaction.guild_id] = interaction

    async def add_balls(self, interaction: discord.Interaction, countryballs):
        guild_battle = self.battles.get(interaction.guild_id)
        if not guild_battle:
            return
    
        if (interaction.user == guild_battle.author and guild_battle.author_ready) or (
            interaction.user == guild_battle.opponent and guild_battle.opponent_ready
        ):
            await interaction.response.send_message(
                f"You cannot change your {settings.collectible_name} as you are already ready.", ephemeral=True
            )
            return
    
        if interaction.user not in (guild_battle.author, guild_battle.opponent):
            await interaction.response.send_message(
                "You aren't a part of this battle!", ephemeral=True
            )
            return
    
        user_balls = (
            guild_battle.battle.p1_balls
            if interaction.user == guild_battle.author
            else guild_battle.battle.p2_balls
        )
    
        abilities = define_abilities()  # Fetch all abilities
    
        for countryball in countryballs:
            # Ensure countryball and its attributes are valid
            if not countryball or not countryball.countryball:
                await interaction.response.send_message(
                    "Invalid countryball provided.", ephemeral=True
                )
                return
    
            ball_abilities = [
                ability for ability in abilities.values() if ability.ball_name == countryball.countryball.country
            ]
            ball = BattleBall(
                name=countryball.countryball.country,
                owner=interaction.user.name,
                health=countryball.health,
                attack=countryball.attack,
                abilities=ball_abilities,  # Assign abilities specific to this ball
                emoji=self.bot.get_emoji(countryball.countryball.emoji_id),
            )
    
            if ball in user_balls:
                yield True
                continue
    
            user_balls.append(ball)
            yield False
    
        await self.update_battle_embed(
            self.interactions[interaction.guild_id], guild_battle
        )

    async def remove_balls(self, interaction: discord.Interaction, countryballs):
        guild_battle = self.battles.get(interaction.guild_id)
        if not guild_battle:
            return
    
        if (interaction.user == guild_battle.author and guild_battle.author_ready) or (
            interaction.user == guild_battle.opponent and guild_battle.opponent_ready
        ):
            await interaction.response.send_message(
                "You cannot change your balls as you are already ready.", ephemeral=True
            )
            return
    
        if interaction.user not in (guild_battle.author, guild_battle.opponent):
            await interaction.response.send_message(
                "You aren't a part of this battle!", ephemeral=True
            )
            return
    
        user_balls = (
            guild_battle.battle.p1_balls
            if interaction.user == guild_battle.author
            else guild_battle.battle.p2_balls
        )
    
        for countryball in countryballs:
            ball = BattleBall(
                name=countryball.countryball.country,
                owner=interaction.user.name,
                health=countryball.health,
                attack=countryball.attack,
                abilities=define_abilities().values(),
                emoji=self.bot.get_emoji(countryball.countryball.emoji_id),
            )
    
            if ball not in user_balls:
                yield True
                continue
    
            user_balls.remove(ball)
            yield False
    
        await self.update_battle_embed(
            self.interactions[interaction.guild_id], guild_battle
        )
        
    @app_commands.command()
    async def add(
        self, interaction: discord.Interaction, countryball: BallInstanceTransform
    ):
        """
        Add a countryball to a battle.
        """
        
        async for dupe in self.add_balls(interaction, [countryball]):
            if dupe:
                await interaction.response.send_message(
                    "You cannot add the same ball twice!", ephemeral=True
                )
                return

        # Construct the message
        attack = "{:+}".format(countryball.attack_bonus)
        health = "{:+}".format(countryball.health_bonus)

        await interaction.response.send_message(
            f"Added `#{countryball.id} {countryball.countryball.country} ({attack}%/{health}%)`!",
            ephemeral=True,
        )

    @app_commands.command()
    async def remove(
        self, interaction: discord.Interaction, countryball: BallInstanceTransform
    ):
        """
        Remove a countryball from battle.
        """

        async for not_in_battle in self.remove_balls(interaction, [countryball]):
            if not_in_battle:
                await interaction.response.send_message(
                    f"You cannot remove a {settings.collectible_name} that is not in your deck!", ephemeral=True
                )
                return

        attack = "{:+}".format(countryball.attack_bonus)
        health = "{:+}".format(countryball.health_bonus)

        await interaction.response.send_message(
            f"Removed `#{countryball.id} {countryball.countryball.country} ({attack}%/{health}%)`!",
            ephemeral=True,
        )
    
    @bulk.command(name='add')
    async def bulk_add(
        self, interaction: discord.Interaction, countryball: BallTransform
    ):
        """
        Add countryballs to a battle in bulk.
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        balls = await countryball.ballinstances.filter(player=player)

        count = 0
        async for dupe in self.add_balls(interaction, balls):
            if not dupe:
                count += 1

        await interaction.response.send_message(
            f'Added {count} {countryball.country}{"s" if count != 1 else ""}!',
            ephemeral=True,
        )

    @bulk.command(name='all')
    async def bulk_all(
        self, interaction: discord.Interaction
    ):
        """
        Add all your countryballs to a battle.
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        balls = await BallInstance.filter(player=player)

        count = 0
        async for dupe in self.add_balls(interaction, balls):
            if not dupe:
                count += 1

        name = settings.collectible_name if count != 1 else settings.collectible_name

        await interaction.response.send_message(f"Added {count} {name}!", ephemeral=True)

    @bulk.command(name='clear')
    async def bulk_remove(
        self, interaction: discord.Interaction
    ):
        """
        Remove all your countryballs from a battle.
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        balls = await BallInstance.filter(player=player)

        count = 0
        async for not_in_battle in self.remove_balls(interaction, balls):
            if not not_in_battle:
                count += 1

        name = settings.collectible_name if count != 1 else settings.collectible_name

        await interaction.response.send_message(f"Removed {count} {name}!", ephemeral=True)

    @bulk.command(name='remove')
    async def bulk_remove(
        self, interaction: discord.Interaction, countryball: BallTransform
    ):
        """
        Remove countryballs from a battle in bulk.
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        balls = await countryball.ballinstances.filter(player=player)

        count = 0
        async for not_in_battle in self.remove_balls(interaction, balls):
            if not not_in_battle:
                count += 1

        await interaction.response.send_message(
            f'Removed {count} {countryball.country}{"s" if count != 1 else ""}!',
            ephemeral=True,
        )
