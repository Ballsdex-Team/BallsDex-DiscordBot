import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Generic, TypeVar

import discord
from discord import app_commands
from discord.ext import tasks
from tortoise.exceptions import DoesNotExist

from ballsdex.core.models import (
    Ball,
    BallInstance,
    Economy,
    Player,
    Regime,
    Special,
    balls,
    economies,
    regimes,
)
from ballsdex.settings import settings

log = logging.getLogger("ballsdex.core.utils.transformers")

CACHE_TIME = 30
T = TypeVar("T")


@dataclass
class CachedBallInstance:
    """
    Used to compute the searchable terms for a countryball only once.
    """

    model: BallInstance
    searchable: str = ""

    def __post_init__(self):
        self.searchable = " ".join(
            (
                self.model.countryball.country.lower(),
                "{:0x}".format(self.model.pk),
                *(
                    self.model.countryball.catch_names.split(";")
                    if self.model.countryball.catch_names
                    else []
                ),
            )
        )


@dataclass
class ListCache(Generic[T]):
    time: float
    balls: list[T]


class BallInstanceCache:
    def __init__(self):
        self.cache: dict[int, ListCache[CachedBallInstance]] = {}
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
                balls = await BallInstance.filter(player_id=player.pk).all()
                for ball in balls:
                    ball.player = player
            cache = ListCache(time, [CachedBallInstance(x) for x in balls])
            self.cache[user.id] = cache

        total = 0
        for ball in cache.balls:
            if value.lower() in ball.searchable:
                yield ball.model
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

    async def validate(
        self, interaction: discord.Interaction, ball: BallInstance
    ) -> BallInstance | None:
        # checking if the ball does belong to user, and a custom ID wasn't forced
        if ball.player.discord_id != interaction.user.id:
            await interaction.response.send_message(
                f"That {settings.collectible_name} doesn't belong to you.", ephemeral=True
            )
            return None
        else:
            return ball

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> list[app_commands.Choice[int | float | str]]:
        t1 = time.time()
        choices: list[app_commands.Choice] = []
        async for ball in self.cache.get(interaction.user, value):
            choices.append(app_commands.Choice(name=ball.description(), value=str(ball.pk)))
        t2 = time.time()
        log.debug(
            f"BallInstance autocomplete took {round((t2-t1)*1000)}ms, {len(choices)} results"
        )
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> BallInstance | None:
        # in theory, the selected ball should be in the cache
        # but it's possible that the autocomplete was never invoked
        try:
            try:
                balls = self.cache.cache[interaction.user.id].balls
                for ball in balls:
                    if ball.model.pk == int(value):
                        return await self.validate(interaction, ball.model)
            except KeyError:
                # maybe the cache didn't have time to build, let's try anyway to fetch the value
                try:
                    ball = await BallInstance.get(id=int(value)).prefetch_related("player")
                    return await self.validate(interaction, ball)
                except DoesNotExist:
                    await interaction.response.send_message(
                        "The ball could not be found. Make sure to use the autocomplete "
                        "function on this command.",
                        ephemeral=True,
                    )
                    return None

        except ValueError:
            # autocomplete didn't work and user tried to force a custom value
            await interaction.response.send_message(
                "The ball could not be found. Make sure to use the autocomplete "
                "function on this command.",
                ephemeral=True,
            )
            return None


BallInstanceTransform = app_commands.Transform[BallInstance, BallInstanceTransformer]


class BallTransformer(app_commands.Transformer):
    def __init__(self):
        self.cache: ListCache[Ball] | None = None

    async def load_cache(self) -> ListCache[Ball]:
        return ListCache(time.time(), list(balls.values()))

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> list[app_commands.Choice[int | float | str]]:
        t1 = time.time()
        if self.cache is None or time.time() - self.cache.time > 300:
            self.cache = await self.load_cache()
        choices: list[app_commands.Choice] = []
        for ball in self.cache.balls:
            if value.lower() in ball.country.lower():
                choices.append(app_commands.Choice(name=ball.country, value=str(ball.pk)))
                if len(choices) == 25:
                    break
        t2 = time.time()
        log.debug(f"Ball autocomplete took {round((t2-t1)*1000)}ms, {len(choices)} results")
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> Ball | None:
        if not value:
            await interaction.response.send_message(
                "You need to use the autocomplete function for the ball selection."
            )
            return None
        try:
            return balls[int(value)]
        except (StopIteration, ValueError):
            await interaction.response.send_message(
                "The ball could not be found. Make sure to use the autocomplete "
                "function on this command.",
                ephemeral=True,
            )
            return None

BallTransform = app_commands.Transform[Ball, BallTransformer]

class BallEnabledTransformer(app_commands.Transformer):
    def __init__(self):
        self.cache: ListCache[Ball] | None = None

    async def load_cache(self):
        self.cache = ListCache(time.time(), [x for x in balls.values() if x.tradeable])

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> list[app_commands.Choice[int | float | str]]:
        t1 = time.time()
        if self.cache is None or time.time() - self.cache.time > 300:
            await self.load_cache()
        choices: list[app_commands.Choice] = []
        for ball in self.cache.balls:
            if value.lower() in ball.country.lower():
                choices.append(app_commands.Choice(name=ball.country, value=str(ball.pk)))
                if len(choices) == 25:
                    break
        t2 = time.time()
        log.debug(f"Ball autocomplete took {round((t2-t1)*1000)}ms, {len(choices)} results")
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> Ball | None:
        await interaction.response.defer()
        if not value:
            await interaction.followup.send(
                "You need to use the autocomplete function for the ball selection."
            )
            return None
        try:
            return balls[int(value)]
        except (StopIteration, ValueError, TypeError):
            await interaction.followup.send(
                "The ball could not be found. Make sure to use the autocomplete "
                "function on this command.",
                ephemeral=True,
            )
            return None

BallEnabledTransform = app_commands.Transform[Ball, BallEnabledTransformer]

class SpecialTransformer(app_commands.Transformer):
    def __init__(self):
        self.cache: ListCache[Special] | None = None

    async def load_cache(self) -> ListCache[Special]:
        events = await Special.all()
        return ListCache(time.time(), events)

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> list[app_commands.Choice[int | float | str]]:
        t1 = time.time()
        if self.cache is None or time.time() - self.cache.time > 300:
            self.cache = await self.load_cache()
        choices: list[app_commands.Choice] = []
        for event in self.cache.balls:
            if value.lower() in event.name.lower():
                choices.append(app_commands.Choice(name=event.name, value=str(event.pk)))
                if len(choices) == 25:
                    break
        t2 = time.time()
        log.debug(f"Special autocomplete took {round((t2-t1)*1000)}ms, {len(choices)} results")
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

class SpecialEnabledTransformer(app_commands.Transformer):
    def __init__(self):
        self.cache: ListCache[Special] | None = None

    async def load_cache(self):
        events = await Special.filter(hidden=False)
        self.cache = ListCache(time.time(), events)

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> list[app_commands.Choice[int | float | str]]:
        t1 = time.time()
        if self.cache is None or time.time() - self.cache.time > 300:
            await self.load_cache()
        choices: list[app_commands.Choice] = []
        for event in self.cache.balls:
            if value.lower() in event.name.lower():
                choices.append(app_commands.Choice(name=event.name, value=str(event.pk)))
                if len(choices) == 25:
                    break
        t2 = time.time()
        log.debug(f"Special autocomplete took {round((t2-t1)*1000)}ms, {len(choices)} results")
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> Special | None:
        await interaction.response.defer()
        if not value:
            await interaction.followup.send(
                "You need to use the autocomplete function for the special background selection."
            )
            return None
        try:
            return await Special.get(pk=int(value))
        except (ValueError, DoesNotExist, TypeError):
            await interaction.followup.send(
                "The special event could not be found. Make sure to use the autocomplete "
                "function on this command."
            )
            return None

SpecialEnabledTransform = app_commands.Transform[Special, SpecialEnabledTransformer]

class RegimeTransformer(app_commands.Transformer):
    def __init__(self):
        self.cache: ListCache[Regime] | None = None

    async def load_cache(self) -> ListCache[Regime]:
        return ListCache(time.time(), list(regimes.values()))

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> list[app_commands.Choice[int | float | str]]:
        t1 = time.time()
        if self.cache is None or time.time() - self.cache.time > 300:
            self.cache = await self.load_cache()
        choices: list[app_commands.Choice] = []
        for regime in self.cache.balls:
            if value.lower() in regime.name.lower():
                choices.append(app_commands.Choice(name=regime.name, value=str(regime.pk)))
                if len(choices) == 25:
                    break
        t2 = time.time()
        log.debug(f"Regime autocomplete took {round((t2-t1)*1000)}ms, {len(choices)} results")
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> Regime | None:
        if not value:
            await interaction.response.send_message(
                "You need to use the autocomplete function for the regime selection."
            )
            return None
        try:
            return regimes[int(value)]
        except (StopIteration, ValueError):
            await interaction.response.send_message(
                "The regime could not be found. Make sure to use the autocomplete "
                "function on this command.",
                ephemeral=True,
            )
            return None

RegimeTransform = app_commands.Transform[Regime, RegimeTransformer]

class EconomyTransformer(app_commands.Transformer):
    def __init__(self):
        self.cache: ListCache[Economy] | None = None

    async def load_cache(self) -> ListCache[Economy]:
        return ListCache(time.time(), list(economies.values()))

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> list[app_commands.Choice[int | float | str]]:
        t1 = time.time()
        if self.cache is None or time.time() - self.cache.time > 300:
            self.cache = await self.load_cache()
        choices: list[app_commands.Choice] = []
        for economy in self.cache.balls:
            if value.lower() in economy.name.lower():
                choices.append(app_commands.Choice(name=economy.name, value=str(economy.pk)))
                if len(choices) == 25:
                    break
        t2 = time.time()
        log.debug(f"Economy autocomplete took {round((t2-t1)*1000)}ms, {len(choices)} results")
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> Economy | None:
        if not value:
            await interaction.response.send_message(
                "You need to use the autocomplete function for the economy selection."
            )
            return None
        try:
            return economies[int(value)]
        except (StopIteration, ValueError):
            await interaction.response.send_message(
                "The economy could not be found. Make sure to use the autocomplete "
                "function on this command.",
                ephemeral=True,
            )
            return None


EconomyTransform = app_commands.Transform[Economy, EconomyTransformer]
