from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, List, Set, cast

import discord
from discord.ui import Button, View, button
from discord.utils import format_dt, utcnow

from ballsdex.core.models import BallInstance, Player
from ballsdex.core.utils import menus
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.paginator import Pages
from ballsdex.packages.balls.countryballs_paginator import CountryballsViewer
from ballsdex.packages.match.display import fill_match_embed_fields
from ballsdex.packages.match.match_user import MatchingUser
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.packages.match.cog import Match as MatchCog

log = logging.getLogger("ballsdex.packages.match.menu")


class InvalidMatchOperation(Exception):
    pass


class MatchView(View):
    def __init__(self, match: MatchMenu):
        super().__init__(timeout=60 * 30)
        self.match = match

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"], /) -> bool:
        try:
            self.match._get_player(interaction.user)
        except RuntimeError:
            await interaction.response.send_message(
                "You are not allowed to interact with this match.", ephemeral=True
            )
            return False
        else:
            return True

    @button(label="Lock bet", emoji="\N{LOCK}", style=discord.ButtonStyle.primary)
    async def lock(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        player = self.match._get_player(interaction.user)
        if player.locked:
            await interaction.response.send_message(
                "You have already locked your bet!", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        await self.match.lock(player)
        if self.match.player1.locked and self.match.player2.locked:
            await interaction.followup.send(
                "Your bet has been locked. The match will execute automatically!",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "Your bet has been locked. "
                "Waiting for the other player to lock their bet...",
                ephemeral=True,
            )

    @button(label="Reset", emoji="\N{DASH SYMBOL}", style=discord.ButtonStyle.secondary)
    async def clear(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        player = self.match._get_player(interaction.user)
        await interaction.response.defer(thinking=True, ephemeral=True)

        if player.locked:
            await interaction.followup.send(
                "You have locked your bet, it cannot be edited! "
                "You can click the cancel button to stop the match instead.",
                ephemeral=True,
            )
            return

        view = ConfirmChoiceView(
            interaction,
            accept_message="Clearing your bet...",
            cancel_message="This request has been cancelled.",
        )
        await interaction.followup.send(
            "Are you sure you want to clear your bet?", view=view, ephemeral=True
        )
        await view.wait()
        if not view.value:
            return

        if player.locked:
            await interaction.followup.send(
                "You have locked your bet, it cannot be edited! "
                "You can click the cancel button to stop the match instead.",
                ephemeral=True,
            )
            return

        for countryball in player.bet:
            await countryball.unlock()

        player.bet.clear()
        await interaction.followup.send("Bet cleared.", ephemeral=True)

    @button(
        label="Cancel match",
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.danger,
    )
    async def cancel(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)

        view = ConfirmChoiceView(
            interaction,
            accept_message="Cancelling the match...",
            cancel_message="This request has been cancelled.",
        )
        await interaction.followup.send(
            "Are you sure you want to cancel this match?", view=view, ephemeral=True
        )
        await view.wait()
        if not view.value:
            return

        await self.match.user_cancel(self.match._get_player(interaction.user))
        await interaction.followup.send("Match has been cancelled.", ephemeral=True)


class MatchMenu:
    def __init__(
        self,
        cog: MatchCog,
        interaction: discord.Interaction["BallsDexBot"],
        player1: MatchingUser,
        player2: MatchingUser,
    ):
        self.cog = cog
        self.bot = interaction.client
        self.channel: discord.TextChannel = cast(discord.TextChannel, interaction.channel)
        self.player1 = player1
        self.player2 = player2
        self.embed = discord.Embed()
        self.task: asyncio.Task | None = None
        self.current_view: MatchView = MatchView(self)
        self.message: discord.Message

    def _get_player(self, user: discord.User | discord.Member) -> MatchingUser:
        if user.id == self.player1.user.id:
            return self.player1
        elif user.id == self.player2.user.id:
            return self.player2
        raise RuntimeError(f"User with ID {user.id} cannot be found in the match")

    def _generate_embed(self):
        add_command = self.cog.add.extras.get("mention", "`/match add`")
        remove_command = self.cog.remove.extras.get("mention", "`/match remove`")
        view_command = self.cog.view.extras.get("mention", "`/match view`")

        self.embed.title = "CHAMPFUT MATCH"
        self.embed.color = discord.Colour.gold()
        self.embed.description = (
            f"Add {settings.plural_collectible_name} you want to bet "
            f"using the {add_command} and {remove_command} commands.\n"
            "Once you're ready, click the lock button below to confirm your bet.\n"
            "**When both players lock their bets, a winner will be chosen randomly (50/50 chance).**\n"
            "**The winner gets ALL balls from both bets!**\n\n"
            "*This match will timeout "
            f"{format_dt(utcnow() + timedelta(minutes=30), style='R')}.*\n\n"
            f"Use the {view_command} command to see your full bet."
        )
        self.embed.set_footer(
            text="This message is updated every 15 seconds, "
            "but you can keep on editing your bet."
        )

    async def update_message_loop(self):
        """
        A loop task that updates each 15 seconds the menu with the new content.
        """

        assert self.task
        start_time = datetime.utcnow()

        while True:
            await asyncio.sleep(15)
            if datetime.utcnow() - start_time > timedelta(minutes=15):
                self.embed.colour = discord.Colour.dark_red()
                await self.cancel("The match timed out")
                return

            try:
                fill_match_embed_fields(self.embed, self.bot, self.player1, self.player2)
                await self.message.edit(embed=self.embed)
            except Exception:
                log.exception(
                    "Failed to refresh the match menu "
                    f"guild={self.message.guild.id} "  # type: ignore
                    f"player1={self.player1.user.id} player2={self.player2.user.id}"
                )
                self.embed.colour = discord.Colour.dark_red()
                await self.cancel("The match timed out")
                return

    async def start(self):
        """
        Start the match by sending the initial message and opening up the betting.
        """
        self._generate_embed()
        fill_match_embed_fields(self.embed, self.bot, self.player1, self.player2)
        self.message = await self.channel.send(
            content=f"Hey {self.player2.user.mention}, {self.player1.user.name} "
            "is challenging you to a 50/50 match!",
            embed=self.embed,
            view=self.current_view,
            allowed_mentions=discord.AllowedMentions(users=self.player2.player.can_be_mentioned),
        )
        self.task = self.bot.loop.create_task(self.update_message_loop())

    async def cancel(self, reason: str = "The match has been cancelled."):
        """
        Cancel the match immediately.
        """
        if self.task:
            self.task.cancel()

        for countryball in self.player1.bet + self.player2.bet:
            await countryball.unlock()

        self.current_view.stop()
        for item in self.current_view.children:
            item.disabled = True  # type: ignore

        fill_match_embed_fields(self.embed, self.bot, self.player1, self.player2)
        self.embed.description = f"**{reason}**"
        if getattr(self, "message", None):
            await self.message.edit(embed=self.embed, view=self.current_view)

    async def user_cancel(self, player: MatchingUser):
        """
        Mark a player as having cancelled the match.
        """
        player.cancelled = True
        await self.cancel(f"{player.user.name} cancelled the match.")

    async def lock(self, player: MatchingUser):
        """
        Lock a player's bet and check if both are ready to execute the match.
        """
        player.locked = True

        # Check if both players have locked their bets
        if self.player1.locked and self.player2.locked:
            await self.execute_match()

    async def execute_match(self):
        """
        Execute the match by randomly selecting a winner and transferring all balls.
        """
        if self.task:
            self.task.cancel()

        # Use secure random to determine winner (50/50 chance)
        winner = secrets.choice([self.player1, self.player2])
        loser = self.player2 if winner == self.player1 else self.player1

        # Mark the winner
        winner.matched = True

        # Transfer all balls from loser to winner
        all_balls = winner.bet + loser.bet
        
        try:
            # Transfer ownership of all balls to the winner
            for ball in all_balls:
                ball.player = winner.player
                await ball.save()
                await ball.unlock()

            # Clear both bets
            winner.bet.clear()
            loser.bet.clear()

            # Update the embed to show the result
            self.embed.title = "🎉 Match Complete! 🎉"
            self.embed.color = discord.Color.green()
            self.embed.description = (
                f"**{winner.user.name} wins!**\n\n"
                f"🏆 **Winner:** {winner.user.mention}\n"
                f"💔 **Loser:** {loser.user.mention}\n\n"
                f"**{len(all_balls)} {settings.plural_collectible_name} "
                f"have been transferred to {winner.user.name}!**\n\n"
                "Thanks for playing!"
            )

            # Disable all buttons
            self.current_view.stop()
            for item in self.current_view.children:
                item.disabled = True  # type: ignore

            # Update the final embed
            fill_match_embed_fields(self.embed, self.bot, self.player1, self.player2)
            await self.message.edit(embed=self.embed, view=self.current_view)

            # Send announcement
            await self.channel.send(
                f"🎉 **Match Result:** {winner.user.mention} defeats {loser.user.mention} "
                f"and wins {len(all_balls)} {settings.plural_collectible_name}! 🎉"
            )

        except Exception as e:
            log.exception(f"Failed to execute match: {e}")
            await self.cancel("An error occurred while executing the match.")


class MatchViewMenu(CountryballsViewer):
    """View for displaying a player's current match bet."""
    
    def __init__(self, interaction: discord.Interaction, balls: list[BallInstance]):
        super().__init__(interaction, balls)

    @property
    def format_page(self):
        def _format_page(menu, balls):
            embed = discord.Embed(
                title="Your Current Match Bet",
                description=f"You have {len(self.entries)} {settings.plural_collectible_name} in your bet.",
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Page {menu.current_page + 1}/{menu.source.get_max_pages()}")
            
            for ball in balls:
                embed.add_field(
                    name=ball.countryball.country,
                    value=ball.description(short=True, include_emoji=True, bot=menu.bot),
                    inline=True
                )
            
            return embed
        return _format_page


class BulkAddView(View):
    """View for bulk adding balls to a match bet."""
    
    def __init__(self, interaction: discord.Interaction, balls: list[BallInstance], cog: MatchCog):
        super().__init__(timeout=300)
        self.interaction = interaction
        self.balls = balls
        self.cog = cog
        self.selected_balls: Set[int] = set()
        self.current_page = 0
        self.per_page = 10

    async def start(self, content: str = None):
        embed = self._build_embed()
        await self.interaction.followup.send(content=content, embed=embed, view=self, ephemeral=True)

    def _build_embed(self) -> discord.Embed:
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_balls = self.balls[start_idx:end_idx]
        
        embed = discord.Embed(
            title="Bulk Add to Match Bet",
            description=f"Select balls to add to your bet. Page {self.current_page + 1}/{((len(self.balls) - 1) // self.per_page) + 1}",
            color=discord.Color.gold()
        )
        
        for i, ball in enumerate(page_balls, start_idx):
            selected = "✅" if ball.pk in self.selected_balls else "❌"
            embed.add_field(
                name=f"{i + 1}. {selected} {ball.countryball.country}",
                value=ball.description(short=True, include_emoji=True, bot=self.cog.bot),
                inline=False
            )
        
        embed.set_footer(text=f"Selected: {len(self.selected_balls)} balls")
        return embed

    @button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            embed = self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()

    @button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_page(self, interaction: discord.Interaction, button: Button):
        max_pages = ((len(self.balls) - 1) // self.per_page) + 1
        if self.current_page < max_pages - 1:
            self.current_page += 1
            embed = self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()

    @button(label="Add Selected", style=discord.ButtonStyle.success, emoji="✅")
    async def add_selected(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        match, player = self.cog.get_match(interaction)
        if not match or not player:
            await interaction.followup.send("Match not found.", ephemeral=True)
            return
            
        if player.locked:
            await interaction.followup.send(
                "Your bet is locked and cannot be edited.", ephemeral=True
            )
            return
            
        added_count = 0
        for ball in self.balls:
            if ball.pk in self.selected_balls and ball not in player.bet:
                if not await ball.is_locked():
                    await ball.lock_for_trade()
                    player.bet.append(ball)
                    added_count += 1
        
        await interaction.followup.send(
            f"Added {added_count} {settings.plural_collectible_name} to your bet.",
            ephemeral=True
        )
        self.stop()

    @button(label="Toggle Select All", style=discord.ButtonStyle.primary, emoji="🔄")
    async def toggle_all(self, interaction: discord.Interaction, button: Button):
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_balls = self.balls[start_idx:end_idx]
        
        # Check if all on current page are selected
        page_ball_ids = {ball.pk for ball in page_balls}
        all_selected = page_ball_ids.issubset(self.selected_balls)
        
        if all_selected:
            # Deselect all on current page
            self.selected_balls -= page_ball_ids
        else:
            # Select all on current page
            self.selected_balls.update(page_ball_ids)
        
        embed = self._build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Selection cancelled.", embed=None, view=None)
        self.stop()
