"""
This file contains [discord.py transformers][discord.app_commands.Transformer] used to provide autocompletion,
parsing and validation for various Ballsdex models.
"""

import logging
import time
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterable

import discord
from discord import app_commands
from discord.ext import commands
from django.db.models import Model, Q
from django.db.models.expressions import RawSQL
from django.utils import timezone

from bd_models.models import Ball, BallInstance, Economy, Regime, Special
from settings.models import settings

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.core.utils.transformers")

__all__ = ("BallTransform", "BallInstanceTransform", "SpecialTransform", "RegimeTransform", "EconomyTransform")


class TradeCommandType(Enum):
    """
    If a command is using `BallInstanceTransformer` for trading purposes, it should define this
    enum to filter out values.
    """

    PICK = 0
    REMOVE = 1


class ModelTransformer[T: "Model"](app_commands.Transformer, commands.Converter):
    """
    Base abstract class for autocompletion from on Django models

    This also works with hybrid commands.

    Attributes
    ----------
    name: str
        Name to qualify the object being listed
    column: str
        Column of the model to use for matching text-based conversions. Defaults to "name".
    model: T
        The Django model associated to the class derivation
    base: int
        The base in which database IDs are converted. Defaults to decimal (10).


    Parameters
    ----------
    **filters: Any
        Filters to apply on the model before providing options.
    """

    name: str
    column: str = "name"
    model: type[T]
    base: int = 10

    def __init__(self, **filters: Any):
        self.filters = filters

    def key(self, model: T) -> str:
        """
        Return a string used for searching while sending autocompletion suggestions.
        """
        return getattr(model, self.column)

    def get_queryset(self) -> "QuerySet[T]":
        return self.model.objects.filter(**self.filters)

    async def validate(self, ctx: commands.Context["BallsDexBot"], item: T):
        """
        A function to validate the fetched item before calling back the command.

        Raises
        ------
        commands.BadArgument
            Raised if the item does not pass validation with the message to be displayed
        """
        pass

    async def get_from_pk(self, value: int) -> T:
        """
        Return a Django model instance from a primary key.

        Raises
        ------
        KeyError | django.db.models.Model.DoesNotExist
            Entry does not exist
        """
        return await self.get_queryset().aget(pk=value)

    async def get_from_text(self, value: str) -> T:
        """
        Return a Django model instance from the raw value entered.

        Raises
        ------
        KeyError | django.db.models.Model.DoesNotExist
            Entry does not exist
        """
        return await self.get_queryset().aget(**{f"{self.column}__iexact": value})

    async def get_options(
        self, interaction: discord.Interaction["BallsDexBot"], value: str
    ) -> list[app_commands.Choice[int]]:
        """
        Generate the list of options for autocompletion
        """
        raise NotImplementedError()

    async def autocomplete(
        self, interaction: discord.Interaction["BallsDexBot"], value: str
    ) -> list[app_commands.Choice[int]]:
        t1 = time.time()
        choices: list[app_commands.Choice[int]] = []
        for option in await self.get_options(interaction, value):
            choices.append(option)
        t2 = time.time()
        log.debug(f"{self.name.title()} autocompletion took {round((t2 - t1) * 1000)}ms, {len(choices)} results")
        return choices

    async def transform(self, interaction: discord.Interaction["BallsDexBot"], value: str) -> T:
        if not value:
            raise commands.BadArgument("You need to use the autocomplete function for the economy selection.")
        try:
            instance = await self.get_from_pk(int(value, self.base))
            await self.validate(await commands.Context.from_interaction(interaction), instance)
        except (self.model.DoesNotExist, KeyError, ValueError):
            raise commands.BadArgument(
                f"The {self.name} could not be found. Make sure to use the autocomplete function on this command."
            )
        else:
            return instance

    async def convert(self, ctx: commands.Context["BallsDexBot"], argument: str) -> T:
        try:
            instance = await self.get_from_text(argument)
            await self.validate(ctx, instance)
        except self.model.DoesNotExist as e:
            raise commands.BadArgument(f"The {self.name} could not be found.") from e
        else:
            return instance


class BallInstanceTransformer(ModelTransformer[BallInstance]):
    name = settings.collectible_name
    model = BallInstance
    base = 16

    def get_queryset(self) -> "QuerySet[BallInstance]":
        return super().get_queryset().prefetch_related("player")

    async def get_from_pk(self, value: int) -> BallInstance:
        return await self.get_queryset().prefetch_related("player", "trade_player").aget(pk=value)

    async def get_from_text(self, value: str) -> BallInstance:
        return await self.get_queryset().aget(pk=int(value, 16))

    async def validate(self, ctx: commands.Context["BallsDexBot"], item: BallInstance):
        # checking if the ball does belong to user, and a custom ID wasn't forced
        if item.player.discord_id != ctx.author.id:
            raise commands.BadArgument(f"That {settings.collectible_name} doesn't belong to you.")

    async def get_options(
        self, interaction: discord.Interaction["BallsDexBot"], value: str
    ) -> list[app_commands.Choice[int]]:
        balls_queryset = self.get_queryset().filter(player__discord_id=interaction.user.id)

        if (special := getattr(interaction.namespace, "special", None)) and special.isdigit():
            balls_queryset = balls_queryset.filter(special_id=int(special))

        if interaction.command and (trade_type := interaction.command.extras.get("trade", None)):
            if trade_type == TradeCommandType.PICK:
                balls_queryset = balls_queryset.filter(
                    Q(Q(locked__isnull=True) | Q(locked__lt=timezone.now() - timedelta(minutes=30)))
                )
            else:
                balls_queryset = balls_queryset.filter(
                    locked__isnull=False, locked__gt=timezone.now() - timedelta(minutes=30)
                )

        if value.startswith("="):
            ball_name = value[1:]
            balls_queryset = balls_queryset.filter(ball__country__iexact=ball_name)
        else:
            balls_queryset = (
                balls_queryset.select_related("ball")
                .annotate(
                    searchable=RawSQL(
                        "to_hex(ballinstance.id) || ' ' || ball.country || ' ' || "
                        "COALESCE(ball.catch_names, '') || ' ' || "
                        "COALESCE(ball.translations, '')",
                        (),
                    )
                )
                .filter(searchable__icontains=value.replace(".", ""))
            )
        balls_queryset = balls_queryset[:25]

        choices: list[app_commands.Choice] = [
            app_commands.Choice(name=x.description(bot=interaction.client), value=f"{x.pk:X}")
            async for x in balls_queryset
        ]
        return choices


class TTLModelTransformer[T: "Model"](ModelTransformer[T]):
    """
    Base class for simple Django model autocompletion with TTL cache.

    This is used in most cases except for BallInstance which requires special handling depending
    on the interaction passed.

    Attributes
    ----------
    ttl: float
        Delay in seconds for `items` to live until refreshed with `load_items`, defaults to 300
    """

    ttl: float = 300

    def __init__(self, **filters: Any):
        super().__init__(**filters)
        self.items: dict[int, T] = {}
        self.search_map: dict[T, str] = {}
        self.last_refresh: float = 0
        log.debug(f"Inited transformer for {self.name}")

    async def load_items(self) -> Iterable[T]:
        """
        Query values to fill `items` with.
        """
        return [x async for x in self.model.objects.all()]

    async def maybe_refresh(self):
        t = time.time()
        if t - self.last_refresh > self.ttl:
            self.items = {x.pk: x for x in await self.load_items()}
            self.last_refresh = t
            self.search_map = {x: self.key(x).lower() for x in self.items.values()}

    async def get_options(
        self, interaction: discord.Interaction["BallsDexBot"], value: str
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
    column = "country"
    model = Ball


class SpecialTransformer(TTLModelTransformer[Special]):
    name = "special event"
    model = Special


class RegimeTransformer(TTLModelTransformer[Regime]):
    name = "regime"
    model = Regime


class EconomyTransformer(TTLModelTransformer[Economy]):
    name = "economy"
    model = Economy


BallTransform = app_commands.Transform[Ball, BallTransformer]
BallInstanceTransform = app_commands.Transform[BallInstance, BallInstanceTransformer]
SpecialTransform = app_commands.Transform[Special, SpecialTransformer]
RegimeTransform = app_commands.Transform[Regime, RegimeTransformer]
EconomyTransform = app_commands.Transform[Economy, EconomyTransformer]
SpecialEnabledTransform = app_commands.Transform[Special, SpecialTransformer(hidden=False)]
BallEnabledTransform = app_commands.Transform[Ball, BallTransformer(enabled=True)]
