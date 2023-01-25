import discord
import time
import logging

from discord import app_commands
from discord.ext import tasks
from datetime import datetime
from dataclasses import dataclass
from tortoise.exceptions import DoesNotExist
from typing import AsyncIterator

from ballsdex.core.models import BallInstance, Player

log = logging.getLogger("ballsdex.core.utils.transformers")

CACHE_TIME = 30


@dataclass
class UserCountryballsCache:
    time: float
    balls: list[BallInstance]


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
            try:
                player = await Player.get(discord_id=user.id)
            except DoesNotExist:
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
        to_delete: list[int] = []
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
    ) -> list[app_commands.Choice[int | float | str]]:
        t1 = time.time()
        choices: list[app_commands.Choice] = []
        async for ball in self.cache.get(interaction.user, value):
            choices.append(app_commands.Choice(name=str(ball), value=str(ball.pk)))
        t2 = time.time()
        log.debug(f"Autocomplete took {round((t2-t1)*1000)}ms, {len(choices)} results")
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> BallInstance | None:
        # in theory, the selected ball should be in the cache
        # but it's possible that the autocomplete was never invoked
        try:
            try:
                balls = self.cache.cache[interaction.user.id].balls
                for ball in balls:
                    if ball.pk == int(value):
                        return ball
            except KeyError:
                # maybe the cache didn't have time to build, let's try anyway to fetch the value
                try:
                    return await BallInstance.get(id=int(value)).prefetch_related("ball")
                except DoesNotExist:
                    await interaction.response.send_message(
                        "The ball could not be found. Make sure to use the autocomplete "
                        "function on this command."
                    )
                    return None

        except ValueError:
            # autocomplete didn't work and user tried to force a custom value
            await interaction.response.send_message(
                "The ball could not be found. Make sure to use the autocomplete "
                "function on this command."
            )
            return None


BallInstanceTransform = app_commands.Transform[BallInstance, BallInstanceTransformer]
