import discord
import time
import logging

from typing import TYPE_CHECKING, Optional, List, Union, AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from tortoise.exceptions import DoesNotExist

from discord import app_commands
from discord.ext import commands, tasks
from discord.utils import format_dt

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
        balls = await player.balls.all().prefetch_related("ball")
        if len(balls) < 1:
            await interaction.response.send_message("You don't have any countryball yet.")
            return
        paginator = CountryballsViewer(interaction, balls)
        await paginator.start()

    @app_commands.command()
    @app_commands.describe(countryball="The countryball you want to inspect")
    async def info(
        self,
        interaction: discord.Interaction,
        countryball: app_commands.Transform[BallInstance, BallInstanceTransformer],
    ):
        if not countryball:
            return
        embed, buffer = countryball.prepare_for_message()
        await interaction.response.send_message(
            content=f"Caught on {format_dt(countryball.catch_date)} "
            f"({format_dt(countryball.catch_date, style='R')})",
            file=discord.File(buffer, "card.png"),
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
