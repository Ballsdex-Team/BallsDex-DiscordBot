import logging
import time
from typing import TYPE_CHECKING, Generic, Iterable, NamedTuple, TypeVar

import discord
from cachetools import TTLCache
from discord import app_commands
from discord.interactions import Interaction
from tortoise.exceptions import DoesNotExist
from tortoise.models import Model

from ballsdex.core.models import (
    Ball,
    BallInstance,
    Economy,
    Regime,
    Special,
    balls,
    economies,
    regimes,
)
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.core.utils.transformers")
T = TypeVar("T", bound=Model)

__all__ = (
    "BallTransform",
    "BallInstanceTransform",
    "SpecialTransform",
    "RegimeTransform",
    "EconomyTransform",
)


class CachedBallInstance(NamedTuple):
    pk: int
    searchable: str
    description: str


class ValidationError(Exception):
    """
    Raised when an autocomplete result is forbidden and should raise a user message.
    """

    def __init__(self, message: str):
        self.message = message


class ModelTransformer(app_commands.Transformer, Generic[T]):
    """
    Base abstract class for autocompletion from on Tortoise models

    Attributes
    ----------
    name: str
        Name to qualify the object being listed
    model: T
        The Tortoise model associated to the class derivation
    """

    name: str
    model: T

    def key(self, model: T) -> str:
        """
        Return a string used for searching while sending autocompletion suggestions.
        """
        raise NotImplementedError()

    async def validate(self, interaction: discord.Interaction["BallsDexBot"], item: T):
        """
        A function to validate the fetched item before calling back the command.

        Raises
        ------
        ValidationError
            Raised if the item does not pass validation with the message to be displayed
        """
        pass

    async def get_from_pk(self, value: int) -> T:
        """
        Return a Tortoise model instance from a primary key.

        Raises
        ------
        KeyError | tortoise.exceptions.DoesNotExist
            Entry does not exist
        """
        return await self.model.get(pk=value)

    async def get_options(
        self, interaction: discord.Interaction["BallsDexBot"], value: str
    ) -> list[app_commands.Choice[int]]:
        """
        Generate the list of options for autocompletion
        """
        raise NotImplementedError()

    async def autocomplete(
        self, interaction: Interaction["BallsDexBot"], value: str
    ) -> list[app_commands.Choice[int]]:
        t1 = time.time()
        choices: list[app_commands.Choice[int]] = []
        for option in await self.get_options(interaction, value):
            choices.append(option)
        t2 = time.time()
        log.debug(
            f"{self.name.title()} autocompletion took "
            f"{round((t2-t1)*1000)}ms, {len(choices)} results"
        )
        return choices

    async def transform(self, interaction: Interaction["BallsDexBot"], value: str) -> T | None:
        if not value:
            await interaction.response.send_message(
                "You need to use the autocomplete function for the economy selection."
            )
            return None
        try:
            instance = await self.get_from_pk(int(value))
            await self.validate(interaction, instance)
        except (DoesNotExist, KeyError, ValueError):
            await interaction.response.send_message(
                f"The {self.name} could not be found. Make sure to use the autocomplete "
                "function on this command.",
                ephemeral=True,
            )
            return None
        except ValidationError as e:
            await interaction.response.send_message(e.message, ephemeral=True)
            return None
        else:
            return instance


class BallInstanceTransformer(ModelTransformer[BallInstance]):
    name = settings.collectible_name
    model = BallInstance  # type: ignore

    def __init__(self):
        self.cache: TTLCache[int, list[CachedBallInstance]] = TTLCache(maxsize=999, ttl=30)

    async def get_from_pk(self, value: int) -> BallInstance:
        return await self.model.get(pk=value).prefetch_related("player")

    async def validate(self, interaction: discord.Interaction["BallsDexBot"], item: BallInstance):
        # checking if the ball does belong to user, and a custom ID wasn't forced
        if item.player.discord_id != interaction.user.id:
            raise ValidationError(f"That {settings.collectible_name} doesn't belong to you.")

    async def get_options(
        self, interaction: Interaction["BallsDexBot"], value: str
    ) -> list[app_commands.Choice[int]]:
        try:
            cached = self.cache[interaction.user.id]
        except KeyError:
            balls = (
                await BallInstance.filter(player__discord_id=interaction.user.id)
                .only(
                    "id",
                    "ball_id",
                    "special_id",
                    "attack_bonus",
                    "health_bonus",
                    "favorite",
                    "shiny",
                )
                .all()
            )
            cached = []
            for ball in balls:
                searchable = " ".join(
                    (
                        ball.countryball.country.lower(),
                        "{:0x}".format(ball.pk),
                        *(
                            ball.countryball.catch_names.split(";")
                            if ball.countryball.catch_names
                            else []
                        ),
                    )
                )
                cached.append(CachedBallInstance(ball.pk, searchable, ball.description()))
            self.cache[interaction.user.id] = cached

        choices: list[app_commands.Choice] = []
        for ball in cached:
            if value.lower() in ball.searchable:
                choices.append(app_commands.Choice(name=ball.description, value=str(ball.pk)))
                if len(choices) >= 25:
                    return choices
        return choices


class TTLModelTransformer(ModelTransformer[T]):
    """
    Base class for simple Tortoise model autocompletion with TTL cache.

    This is used in most cases except for BallInstance which requires special handling depending
    on the interaction passed.

    Attributes
    ----------
    ttl: float
        Delay in seconds for `items` to live until refreshed with `load_items`, defaults to 300
    """

    ttl: float = 300

    def __init__(self):
        self.items: dict[int, T] = {}
        self.search_map: dict[T, str] = {}
        self.last_refresh: float = 0
        log.debug(f"Inited transformer for {self.name}")

    async def load_items(self) -> Iterable[T]:
        """
        Query values to fill `items` with.
        """
        return await self.model.all()

    async def maybe_refresh(self):
        t = time.time()
        if t - self.last_refresh > self.ttl:
            self.items = {x.pk: x for x in await self.load_items()}
            self.last_refresh = t
            self.search_map = {x: self.key(x).lower() for x in self.items.values()}

    async def get_options(
        self, interaction: Interaction["BallsDexBot"], value: str
    ) -> list[app_commands.Choice[str]]:
        await self.maybe_refresh()

        i = 0
        choices: list[app_commands.Choice] = []
        for item in self.items.values():
            if value.lower() in self.search_map[item]:
                choices.append(app_commands.Choice(name=self.key(item), value=str(item.pk)))
                i += 1
                if i == 25:
                    break
        return choices


class BallTransformer(TTLModelTransformer[Ball]):
    name = settings.collectible_name
    model = Ball()

    def key(self, model: Ball) -> str:
        return model.country

    async def load_items(self) -> Iterable[Ball]:
        return balls.values()


class BallEnabledTransformer(BallTransformer):
    async def load_items(self) -> Iterable[Ball]:
        return {k: v for k, v in balls.items() if v.enabled}.values()


class SpecialTransformer(TTLModelTransformer[Special]):
    name = "special event"
    model = Special()

    def key(self, model: Special) -> str:
        return model.name


class SpecialEnabledTransformer(SpecialTransformer):
    async def load_items(self) -> Iterable[Special]:
        return await Special.filter(hidden=False).all()


class RegimeTransformer(TTLModelTransformer[Regime]):
    name = "regime"
    model = Regime()

    def key(self, model: Regime) -> str:
        return model.name

    async def load_items(self) -> Iterable[Regime]:
        return regimes.values()


class EconomyTransformer(TTLModelTransformer[Economy]):
    name = "economy"
    model = Economy()

    def key(self, model: Economy) -> str:
        return model.name

    async def load_items(self) -> Iterable[Economy]:
        return economies.values()


BallTransform = app_commands.Transform[Ball, BallTransformer]
BallInstanceTransform = app_commands.Transform[BallInstance, BallInstanceTransformer]
SpecialTransform = app_commands.Transform[Special, SpecialTransformer]
RegimeTransform = app_commands.Transform[Regime, RegimeTransformer]
EconomyTransform = app_commands.Transform[Economy, EconomyTransformer]
SpecialEnabledTransform = app_commands.Transform[Special, SpecialEnabledTransformer]
BallEnabledTransform = app_commands.Transform[Ball, BallEnabledTransformer]
