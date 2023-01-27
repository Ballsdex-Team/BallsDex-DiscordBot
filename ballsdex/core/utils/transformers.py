import discord
import time
import logging

from discord import app_commands
from discord.ext import tasks
from datetime import datetime
from dataclasses import dataclass
from tortoise.exceptions import DoesNotExist
from typing import TypeVar, Generic, AsyncIterator

from ballsdex.core.models import Ball, BallInstance, Player, Special

log = logging.getLogger("ballsdex.core.utils.transformers")

CACHE_TIME = 30
T = TypeVar("T")


@dataclass
class ListCache(Generic[T]):
    time: float
    balls: list[T]


class BallInstanceCache:
    def __init__(self):
        self.cache: dict[int, ListCache[BallInstance]] = {}
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
            cache = ListCache(time, balls)
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
        self.cache = BallInstanceCache()

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


class BallTransformer(app_commands.Transformer):
    def __init__(self):
        self.cache: ListCache[Ball] | None = None

    async def load_cache(self):
        balls = await Ball.all()
        self.cache = ListCache(time.time(), balls)

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> list[app_commands.Choice[int | float | str]]:
        if self.cache is None or time.time() - self.cache.time > 300:
            await self.load_cache()
        choices: list[app_commands.Choice] = []
        for ball in self.cache.balls:
            if value.lower() in ball.country.lower():
                choices.append(app_commands.Choice(name=ball.country, value=str(ball.pk)))
                if len(choices) == 25:
                    break
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> Ball | None:
        if not value:
            await interaction.response.send_message(
                "You need to use the autocomplete function for the ball selection."
            )
            return None
        try:
            return await Ball.get(pk=int(value))
        except (ValueError, DoesNotExist):
            await interaction.response.send_message(
                "The ball could not be found. Make sure to use the autocomplete "
                "function on this command."
            )
            return None


BallTransform = app_commands.Transform[Ball, BallTransformer]


class SpecialTransformer(app_commands.Transformer):
    def __init__(self):
        self.cache: ListCache[Special] | None = None

    async def load_cache(self):
        events = await Special.all()
        self.cache = ListCache(time.time(), events)

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> list[app_commands.Choice[int | float | str]]:
        if self.cache is None or time.time() - self.cache.time > 300:
            await self.load_cache()
        choices: list[app_commands.Choice] = []
        for event in self.cache.balls:
            if value.lower() in event.name.lower():
                choices.append(app_commands.Choice(name=event.name, value=str(event.pk)))
                if len(choices) == 25:
                    break
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> Special | None:
        if not value:
            await interaction.response.send_message(
                "You need to use the autocomplete function for the special background selection."
            )
            return None
        try:
            return await Special.get(pk=int(value))
        except (ValueError, DoesNotExist):
            await interaction.response.send_message(
                "The special event could not be found. Make sure to use the autocomplete "
                "function on this command."
            )
            return None


SpecialTransform = app_commands.Transform[Special, SpecialTransformer]
