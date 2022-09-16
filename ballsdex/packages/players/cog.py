import discord
import time
import logging

from typing import TYPE_CHECKING, Optional, List, Union, AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from tortoise.exceptions import DoesNotExist

from discord import app_commands
from discord.ext import commands, tasks

from ballsdex.core.models import Player, BallInstance

from ballsdex.packages.players.countryballs_paginator import (
    CountryballsViewer,
    CountryballsExchangerPaginator,
)
from ballsdex.packages.players.exchange_interaction import ExchangePlayer

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.countryballs")

CACHE_TIME = 30


@dataclass
class UserCountryballsCache:
    time: float
    balls: List[BallInstance]


class CountryballCache:
    def __init__(self):
        self.cache: dict[int, UserCountryballsCache] = {}
        self.clear_cache.start()

    async def get(self, user: discord.abc.User, value: str) -> AsyncIterator[BallInstance]:
        time = datetime.utcnow().timestamp()
        try:
            cache = self.cache[user.id]
            if time - cache.time > 60:
                raise KeyError  # refresh cache after a minute
        except KeyError:
            player, created = await Player.get_or_create(discord_id=user.id)
            if created:
                balls = []
            else:
                balls = await BallInstance.filter(player=player).select_related("ball").all()
            cache = UserCountryballsCache(time, balls)
            self.cache[user.id] = cache

        total = 0
        for ball in cache.balls:
            if value in ball.ball.country.lower():
                yield ball
                total += 1
                if total >= 25:
                    return

    @tasks.loop(seconds=10, reconnect=True)
    async def clear_cache(self):
        time = datetime.utcnow().timestamp()
        to_delete: List[int] = []
        for id, user in self.cache.items():
            if time - user.time > CACHE_TIME:
                to_delete.append(id)
        for id in to_delete:
            del self.cache[id]


class BallInstanceTransformer(app_commands.Transformer):
    def __init__(self):
        self.cache = CountryballCache()

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> List[app_commands.Choice[Union[int, float, str]]]:
        t1 = time.time()
        choices: List[app_commands.Choice] = []
        async for ball in self.cache.get(interaction.user, value):
            choices.append(app_commands.Choice(name=str(ball), value=str(ball.id)))
        t2 = time.time()
        log.debug(f"Autocomplete took {round((t2-t1)*1000)}ms, {len(choices)} results")
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> BallInstance | None:
        # in theory, the selected ball should be in the cache
        # but it's possible that the autocomplete was never invoked
        try:
            balls = self.cache.cache[interaction.user.id].balls
            for ball in balls:
                if ball.id == int(value):
                    return ball
        except KeyError:
            pass
        # at this point, either KeyError or ball not found in cache
        try:
            return await BallInstance.get(id=int(value)).prefetch_related("ball")
        except DoesNotExist:
            await interaction.response.send_message(
                "The ball could not be found. Make sure to use the autocomplete "
                "function on this command."
            )
            return None


class Players(commands.GroupCog, group_name="balls"):
    """
    View and manage your countryballs collection.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    async def list(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        """
        List your countryballs.
        """
        user: discord.User | discord.Member = user or interaction.user

        player, created = await Player.get_or_create(discord_id=user.id)
        if created:
            await interaction.response.send_message("You don't have any countryball yet.")
            return

        await player.fetch_related("balls")
        balls = await player.balls.all().order_by("-favorite").prefetch_related("ball")
        if len(balls) < 1:
            await interaction.response.send_message("You don't have any countryball yet.")
            return

        paginator = CountryballsViewer(interaction, balls)
        if user == interaction.user:
            await paginator.start()
        else:
            await paginator.start(content=f"Viewing {user.name}'s countryballs")

    @app_commands.command()
    @app_commands.describe(countryball="The countryball you want to inspect")
    async def info(
        self,
        interaction: discord.Interaction,
        countryball: app_commands.Transform[BallInstance, BallInstanceTransformer],
    ):
        """
        Display info from a specific countryball.
        """
        if not countryball:
            return
        await interaction.response.defer(thinking=True)
        content, file = await countryball.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file)

    @app_commands.command()
    async def last(self, interaction: discord.Interaction):
        """
        Display info of your last caught countryball.
        """
        await interaction.response.defer(thinking=True)
        try:
            player = await Player.get(discord_id=interaction.user.id)
        except DoesNotExist:
            await interaction.followup.send("You do not have any countryball yet.", ephemeral=True)
            return

        countryball = await player.balls.all().order_by("-id").first().select_related("ball")
        if not countryball:
            await interaction.followup.send("You do not have any countryball yet.", ephemeral=True)
            return

        content, file = await countryball.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file)

    @app_commands.command()
    @app_commands.describe(countryball="The countryball you want to set/unset as favorite")
    async def favorite(
        self,
        interaction: discord.Interaction,
        countryball: app_commands.Transform[BallInstance, BallInstanceTransformer],
    ):
        """
        Set favorite countryballs.
        """
        if not countryball.favorite:

            player = await Player.get(discord_id=interaction.user.id).prefetch_related("balls")
            if await player.balls.filter(favorite=True).count() > 6:
                await interaction.response.send_message(
                    "You cannot set more than 6 favorite countryballs.", ephemeral=True
                )
                return

            countryball.favorite = True  # type: ignore
            await countryball.save()
            emoji = self.bot.get_emoji(countryball.ball.emoji_id) or ""
            await interaction.response.send_message(
                f"{emoji} `{countryball.count}#` {countryball.ball.country} "
                "is now a favorite countryball!",
                ephemeral=True,
            )

        else:
            countryball.favorite = False  # type: ignore
            await countryball.save()
            emoji = self.bot.get_emoji(countryball.ball.emoji_id) or ""
            await interaction.response.send_message(
                f"{emoji} `{countryball.count}#` {countryball.ball.country} "
                "isn't a favorite countryball anymore.",
                ephemeral=True,
            )

    @app_commands.command()
    @app_commands.describe(
        user="The user you want to exchange a countryball with",
        countryball="The countryball you want to exchange",
    )
    async def exchange(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        countryball: app_commands.Transform[BallInstance, BallInstanceTransformer] = None,
    ):
        """
        Exchange a countryball with another player.
        """
        if user.bot:
            await interaction.response.send_message(
                "You cannot exchange with bots.", ephemeral=True
            )
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot exchange with yourself.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True)
        # theorically, the player should always be created by the autocomplete function
        # let's still handle the case where autocomplete wasn't invoked and the player may not
        # have been created yet
        if countryball is None:
            await CountryballsExchangerPaginator.begin_blank_exchange(
                interaction, interaction.user, user
            )
        else:
            player, created = await Player.get_or_create(discord_id=interaction.user.id)
            await CountryballsExchangerPaginator.half_ready_exchange(
                interaction, ExchangePlayer(interaction.user, player, countryball), user
            )
