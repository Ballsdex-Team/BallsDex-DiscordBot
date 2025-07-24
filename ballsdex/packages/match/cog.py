import datetime
from collections import defaultdict
from typing import TYPE_CHECKING, Optional, cast

import discord
from cachetools import TTLCache
from discord import app_commands
from discord.ext import commands
from discord.utils import MISSING
from tortoise.expressions import Q

from ballsdex.core.models import BallInstance, Player
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.paginator import Pages
from ballsdex.core.utils.sorting import FilteringChoices, SortingChoices, filter_balls, sort_balls
from ballsdex.core.utils.transformers import (
    BallEnabledTransform,
    BallInstanceTransform,
    SpecialEnabledTransform,
    TradeCommandType,
)
from ballsdex.packages.match.display import MatchViewFormat
from ballsdex.packages.match.menu import BulkAddView, MatchMenu, MatchViewMenu
from ballsdex.packages.match.match_user import MatchingUser
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


@app_commands.guild_only()
class Match(commands.GroupCog):
    """
    Challenge other players to 50/50 matches where winner takes all countryballs.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.matches: TTLCache[int, dict[int, list[MatchMenu]]] = TTLCache(maxsize=999999, ttl=1800)

    bulk = app_commands.Group(name="bulk", description="Bulk Commands")

    def get_match(
        self,
        interaction: discord.Interaction["BallsDexBot"] | None = None,
        *,
        channel: discord.TextChannel | None = None,
        user: discord.User | discord.Member = MISSING,
    ) -> tuple[MatchMenu, MatchingUser] | tuple[None, None]:
        """
        Find an ongoing match for the given interaction.

        Parameters
        ----------
        interaction: discord.Interaction["BallsDexBot"]
            The current interaction, used for getting the guild, channel and author.

        Returns
        -------
        tuple[MatchMenu, MatchingUser] | tuple[None, None]
            A tuple with the `MatchMenu` and `MatchingUser` if found, else `None`.
        """
        guild: discord.Guild
        if interaction:
            guild = cast(discord.Guild, interaction.guild)
            channel = cast(discord.TextChannel, interaction.channel)
            user = interaction.user
        elif channel:
            guild = channel.guild
        else:
            raise TypeError("Missing interaction or channel")

        if guild.id not in self.matches:
            self.matches[guild.id] = defaultdict(list)
        if channel.id not in self.matches[guild.id]:
            return (None, None)
        to_remove: list[MatchMenu] = []
        for match in self.matches[guild.id][channel.id]:
            if (
                match.current_view.is_finished()
                or match.player1.cancelled
                or match.player2.cancelled
            ):
                # remove what was supposed to have been removed
                to_remove.append(match)
                continue
            try:
                player = match._get_player(user)
            except RuntimeError:
                continue
            else:
                break
        else:
            for match in to_remove:
                self.matches[guild.id][channel.id].remove(match)
            return (None, None)

        for match in to_remove:
            self.matches[guild.id][channel.id].remove(match)
        return (match, player)

    @app_commands.command()
    async def begin(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User):
        """
        Begin a 50/50 match with the chosen user where winner takes all balls.

        Parameters
        ----------
        user: discord.User
            The user you want to challenge to a match
        """
        if user.bot:
            await interaction.response.send_message("You cannot match with bots.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot match with yourself.", ephemeral=True
            )
            return
        player1, _ = await Player.get_or_create(discord_id=interaction.user.id)
        player2, _ = await Player.get_or_create(discord_id=user.id)
        blocked = await player1.is_blocked(player2)
        if blocked:
            await interaction.response.send_message(
                "You cannot begin a match with a user that you have blocked.", ephemeral=True
            )
            return
        blocked2 = await player2.is_blocked(player1)
        if blocked2:
            await interaction.response.send_message(
                "You cannot begin a match with a user that has blocked you.", ephemeral=True
            )
            return

        match1, player1_obj = self.get_match(interaction)
        match2, player2_obj = self.get_match(channel=interaction.channel, user=user)  # type: ignore
        if match1 or player1_obj:
            await interaction.response.send_message(
                "You already have an ongoing match.", ephemeral=True
            )
            return
        if match2 or player2_obj:
            await interaction.response.send_message(
                "The user you are trying to match with is already in a match.", ephemeral=True
            )
            return

        player1, _ = await Player.get_or_create(discord_id=interaction.user.id)
        player2, _ = await Player.get_or_create(discord_id=user.id)
        if player2.discord_id in self.bot.blacklist:
            await interaction.response.send_message(
                "You cannot match with a blacklisted user.", ephemeral=True
            )
            return

        menu = MatchMenu(
            self, interaction, MatchingUser(interaction.user, player1), MatchingUser(user, player2)
        )
        self.matches[interaction.guild.id][interaction.channel.id].append(menu)  # type: ignore
        await menu.start()
        await interaction.response.send_message("Match started!", ephemeral=True)

    @app_commands.command(extras={"match": TradeCommandType.PICK})
    async def add(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Add a countryball to your match bet.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to add to your bet
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        if not countryball:
            return
        if not countryball.is_tradeable:
            await interaction.response.send_message(
                f"You cannot bet this {settings.collectible_name}.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        if countryball.favorite:
            view = ConfirmChoiceView(
                interaction,
                accept_message=f"{settings.collectible_name.title()} added to bet.",
                cancel_message="This request has been cancelled.",
            )
            await interaction.followup.send(
                f"This {settings.collectible_name} is a favorite, "
                "are you sure you want to bet it?",
                view=view,
                ephemeral=True,
            )
            await view.wait()
            if not view.value:
                return

        match, player = self.get_match(interaction)
        if not match or not player:
            await interaction.followup.send("You do not have an ongoing match.", ephemeral=True)
            return
        if player.locked:
            await interaction.followup.send(
                "You have locked your bet, it cannot be edited! "
                "You can click the cancel button to stop the match instead.",
                ephemeral=True,
            )
            return
        if countryball in player.bet:
            await interaction.followup.send(
                f"You already have this {settings.collectible_name} in your bet.",
                ephemeral=True,
            )
            return
        if await countryball.is_locked():
            await interaction.followup.send(
                f"This {settings.collectible_name} is currently in an active trade or donation, "
                "please try again later.",
                ephemeral=True,
            )
            return

        await countryball.lock_for_trade()
        player.bet.append(countryball)
        await interaction.followup.send(
            f"{countryball.countryball.country} added to bet.", ephemeral=True
        )

    @bulk.command(name="add", extras={"match": TradeCommandType.PICK})
    async def bulk_add(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallEnabledTransform | None = None,
        sort: SortingChoices | None = None,
        special: SpecialEnabledTransform | None = None,
        filter: FilteringChoices | None = None,
    ):
        """
        Bulk add countryballs to your match bet, with parameters to aid with searching.

        Parameters
        ----------
        countryball: Ball
            The countryball you would like to filter the results to
        sort: SortingChoices
            Choose how countryballs are sorted. Can be used to show duplicates.
        special: Special
            Filter the results to a special event
        filter: FilteringChoices
            Filter the results to a specific filter
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        match, player = self.get_match(interaction)
        if not match or not player:
            await interaction.followup.send("You do not have an ongoing match.", ephemeral=True)
            return
        if player.locked:
            await interaction.followup.send(
                "You have locked your bet, it cannot be edited! "
                "You can click the cancel button to stop the match instead.",
                ephemeral=True,
            )
            return
        query = BallInstance.filter(player__discord_id=interaction.user.id)
        if countryball:
            query = query.filter(ball=countryball)
        if special:
            query = query.filter(special=special)
        if sort:
            query = sort_balls(sort, query)
        if filter:
            query = filter_balls(filter, query, interaction.guild_id)
        balls = await query
        if not balls:
            await interaction.followup.send(
                f"No {settings.plural_collectible_name} found.", ephemeral=True
            )
            return
        balls = [x for x in balls if x.is_tradeable]

        view = BulkAddView(interaction, balls, self)  # type: ignore
        await view.start(
            content=f"Select the {settings.plural_collectible_name} you want to add "
            "to your bet, note that the display will wipe on pagination however "
            f"the selected {settings.plural_collectible_name} will remain."
        )

    @app_commands.command(extras={"match": TradeCommandType.REMOVE})
    async def remove(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Remove a countryball from your match bet.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to remove from your bet
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        if not countryball:
            return

        match, player = self.get_match(interaction)
        if not match or not player:
            await interaction.response.send_message(
                "You do not have an ongoing match.", ephemeral=True
            )
            return
        if player.locked:
            await interaction.response.send_message(
                "You have locked your bet, it cannot be edited! "
                "You can click the cancel button to stop the match instead.",
                ephemeral=True,
            )
            return
        if countryball not in player.bet:
            await interaction.response.send_message(
                f"That {settings.collectible_name} is not in your bet.", ephemeral=True
            )
            return
        player.bet.remove(countryball)
        await countryball.unlock()
        await interaction.response.send_message(
            f"{countryball.countryball.country} removed from bet.", ephemeral=True
        )

    @app_commands.command()
    async def view(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        View your current match and the balls you've bet.
        """
        match, player = self.get_match(interaction)
        if not match or not player:
            await interaction.response.send_message(
                "You do not have an ongoing match.", ephemeral=True
            )
            return

        if not player.bet:
            await interaction.response.send_message(
                "You have no balls in your current bet.", ephemeral=True
            )
            return

        view = MatchViewMenu(interaction, player.bet)
        await view.start()

    @app_commands.command()
    async def info(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Get information about the current match.
        """
        match, player = self.get_match(interaction)
        if not match or not player:
            await interaction.response.send_message(
                "You do not have an ongoing match.", ephemeral=True
            )
            return

        other_player = match.player1 if player == match.player2 else match.player2
        
        embed = discord.Embed(
            title="Match Information",
            description="50/50 winner takes all match",
            color=discord.Color.gold()
        )
        embed.add_field(
            name=f"{player.user.display_name}'s Bet",
            value=f"{len(player.bet)} {settings.plural_collectible_name}" if player.bet else "Empty",
            inline=True
        )
        embed.add_field(
            name=f"{other_player.user.display_name}'s Bet",
            value=f"{len(other_player.bet)} {settings.plural_collectible_name}" if other_player.bet else "Empty",
            inline=True
        )
        embed.add_field(
            name="Status",
            value=f"Your bet: {'🔒 Locked' if player.locked else '🔓 Unlocked'}\n"
                  f"Their bet: {'🔒 Locked' if other_player.locked else '🔓 Unlocked'}",
            inline=False
        )
        embed.add_field(
            name="How it works",
            value="Once both players lock their bets, the match will execute automatically. "
                  "The winner is chosen randomly (50/50 chance) and gets all balls from both bets!",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)
