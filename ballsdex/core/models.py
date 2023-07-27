from __future__ import annotations

import discord
from discord.utils import format_dt

from io import BytesIO
from enum import IntEnum
from datetime import datetime
from typing import TYPE_CHECKING, Tuple, Type, Iterable
from concurrent.futures import ThreadPoolExecutor

from tortoise import models, fields, validators, exceptions, signals
from fastapi_admin.models import AbstractAdmin

if TYPE_CHECKING:
    from tortoise.backends.base.client import BaseDBAsyncClient


balls: dict[int, Ball] = {}
regimes: dict[int, Regime] = {}
economies: dict[int, Economy] = {}
specials: dict[int, Special] = {}


async def lower_catch_names(
    model: Type[Ball],
    instance: Ball,
    created: bool,
    using_db: "BaseDBAsyncClient" | None = None,
    update_fields: Iterable[str] | None = None,
):
    instance.catch_names = instance.catch_names.lower()


class DiscordSnowflakeValidator(validators.Validator):
    def __call__(self, value: int):
        if not 17 <= len(str(value)) <= 19:
            raise exceptions.ValidationError("Discord IDs are between 17 and 19 characters long")


class User(AbstractAdmin):
    last_login = fields.DatetimeField(description="Last Login", default=datetime.now)
    avatar = fields.CharField(max_length=200, default="")
    intro = fields.TextField(default="")
    created_at = fields.DatetimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.pk}#{self.username}"


class GuildConfig(models.Model):
    guild_id = fields.BigIntField(
        description="Discord guild ID", unique=True, validators=[DiscordSnowflakeValidator()]
    )
    spawn_channel = fields.BigIntField(
        description="Discord channel ID where balls will spawn", null=True
    )
    enabled = fields.BooleanField(
        description="Whether the bot will spawn countryballs in this guild", default=True
    )


class Regime(models.Model):
    name = fields.CharField(max_length=64)
    background = fields.CharField(max_length=200, description="1428x2000 PNG image")

    def __str__(self):
        return self.name


class Economy(models.Model):
    name = fields.CharField(max_length=64)
    icon = fields.CharField(max_length=200, description="512x512 PNG image")

    def __str__(self):
        return self.name


class Special(models.Model):
    name = fields.CharField(max_length=64)
    catch_phrase = fields.CharField(
        max_length=128,
        description="Sentence sent in bonus when someone catches a special card",
        null=True,
        default=None,
    )
    start_date = fields.DatetimeField()
    end_date = fields.DatetimeField()
    rarity = fields.FloatField(
        description="Value between 0 and 1, chances of using this special background."
    )
    background = fields.CharField(max_length=200, description="1428x2000 PNG image", null=True)
    emoji = fields.CharField(
        max_length=20,
        description="Either a unicode character or a discord emoji ID",
        null=True,
    )

    def __str__(self) -> str:
        return self.name


class Ball(models.Model):
    country = fields.CharField(max_length=48, unique=True)
    short_name = fields.CharField(max_length=12, null=True, default=None)
    catch_names = fields.TextField(
        null=True,
        default=None,
        description="Additional possible names for catching this ball, separated by semicolons",
    )
    regime: fields.ForeignKeyRelation[Regime] = fields.ForeignKeyField(
        "models.Regime", description="Political regime of this country", on_delete=fields.CASCADE
    )
    economy: fields.ForeignKeyRelation[Economy] = fields.ForeignKeyField(
        "models.Economy",
        description="Economical regime of this country",
        on_delete=fields.SET_NULL,
        null=True,
    )
    health = fields.IntField(description="Ball health stat")
    attack = fields.IntField(description="Ball attack stat")
    rarity = fields.FloatField(description="Rarity of this ball")
    enabled = fields.BooleanField(default=True)
    tradeable = fields.BooleanField(default=True)
    emoji_id = fields.BigIntField(
        description="Emoji ID for this ball", validators=[DiscordSnowflakeValidator()]
    )
    wild_card = fields.CharField(
        max_length=200, description="Image used when a new ball spawns in the wild"
    )
    collection_card = fields.CharField(
        max_length=200, description="Image used when displaying balls"
    )
    credits = fields.CharField(max_length=64, description="Author of the collection artwork")
    capacity_name = fields.CharField(
        max_length=64, description="Name of the countryball's capacity"
    )
    capacity_description = fields.CharField(
        max_length=256, description="Description of the countryball's capacity"
    )
    capacity_logic = fields.JSONField(description="Effect of this capacity", default={})

    instances: fields.BackwardFKRelation[BallInstance]

    def __str__(self) -> str:
        return self.country

    @property
    def cached_regime(self) -> Regime:
        return regimes.get(self.regime_id, self.regime)

    @property
    def cached_economy(self) -> Economy:
        return economies.get(self.economy_id, self.economy)


Ball.register_listener(signals.Signals.pre_save, lower_catch_names)


class BallInstance(models.Model):
    ball: fields.ForeignKeyRelation[Ball] = fields.ForeignKeyField("models.Ball")
    player: fields.ForeignKeyRelation[Player] = fields.ForeignKeyRelation(
        "models.Player", related_name="balls"
    )  # type: ignore
    catch_date = fields.DatetimeField(auto_now_add=True)
    shiny = fields.BooleanField(default=False)
    special: fields.ForeignKeyRelation[Special] = fields.ForeignKeyField(
        "models.Special", null=True, default=None, on_delete=fields.SET_NULL
    )
    health_bonus = fields.IntField(default=0)
    attack_bonus = fields.IntField(default=0)
    trade_player: fields.ForeignKeyRelation[Player] = fields.ForeignKeyField(
        "models.Player", null=True, default=None, on_delete=fields.SET_NULL
    )
    favorite = fields.BooleanField(default=False)

    class Meta:
        unique_together = ("player", "id")

    @property
    def attack(self) -> int:
        bonus = int(self.countryball.attack * self.attack_bonus * 0.01)
        return self.countryball.attack + bonus

    @property
    def health(self) -> int:
        bonus = int(self.countryball.health * self.health_bonus * 0.01)
        return self.countryball.health + bonus

    @property
    def special_card(self) -> str | None:
        if self.specialcard:
            return self.specialcard.background or self.countryball.collection_card

    @property
    def countryball(self) -> Ball:
        return balls.get(self.ball_id, self.ball)

    @property
    def specialcard(self) -> Special:
        return specials.get(self.special_id, self.special)

    def __str__(self) -> str:
        return self.to_string()

    def to_string(self, bot: discord.Client | None = None) -> str:
        emotes = ""
        if self.favorite:
            emotes += "❤️"
        if self.shiny:
            emotes += "✨"
        if emotes:
            emotes += " "
        if self.specialcard:
            emotes += self.special_emoji(bot)
        country = (
            self.countryball.country
            if isinstance(self.countryball, Ball)
            else f"<Ball {self.ball_id}>"
        )
        return f"{emotes}#{self.pk:0X} {country} "

    def special_emoji(self, bot: discord.Client | None, use_custom_emoji: bool = True) -> str:
        if self.specialcard:
            special_emoji = ""
            try:
                emoji_id = int(self.specialcard.emoji)
                special_emoji = bot.get_emoji(emoji_id) if bot else "⚡ "
                if not use_custom_emoji:
                    return "⚡ "
            except ValueError:
                special_emoji = self.specialcard.emoji
            except TypeError:
                return ""
            if special_emoji:
                return f"{special_emoji} "
        return ""

    def description(
        self,
        *,
        short: bool = False,
        include_emoji: bool = False,
        bot: discord.Client | None = None,
    ) -> str:
        text = self.to_string(bot)
        if not short:
            text += f" ATK:{self.attack_bonus:+d}% HP:{self.health_bonus:+d}%"
        if include_emoji:
            if not bot:
                raise TypeError(
                    "You need to provide the bot argument when using with include_emoji=True"
                )
            if isinstance(self.countryball, Ball):
                emoji = bot.get_emoji(self.countryball.emoji_id)
                if emoji:
                    text = f"{emoji} {text}"
        return text

    def draw_card(self) -> BytesIO:
        from ballsdex.core.image_generator.image_gen import draw_card

        image = draw_card(self)
        buffer = BytesIO()
        image.save(buffer, format="png")
        buffer.seek(0)
        image.close()
        return buffer

    async def prepare_for_message(
        self, interaction: discord.Interaction
    ) -> Tuple[str, discord.File]:
        # message content
        trade_content = ""
        await self.fetch_related("trade_player", "special")
        if self.trade_player:
            original_player = None
            # we want to avoid calling fetch_user if possible (heavily rate-limited call)
            if interaction.guild:
                try:
                    original_player = await interaction.guild.fetch_member(
                        int(self.trade_player.discord_id)
                    )
                except discord.NotFound:
                    pass
            elif original_player is None:  # try again if not found in guild
                try:
                    original_player = await interaction.client.fetch_user(
                        int(self.trade_player.discord_id)
                    )
                except discord.NotFound:
                    pass

            original_player_name = (
                original_player.name
                if original_player
                else f"user with ID {self.trade_player.discord_id}"
            )
            trade_content = f"Obtained by trade with {original_player_name}.\n"
        content = (
            f"ID: `#{self.pk:0X}`\n"
            f"Caught on {format_dt(self.catch_date)} ({format_dt(self.catch_date, style='R')}).\n"
            f"{trade_content}\n"
            f"ATK: {self.attack} ({self.attack_bonus:+d}%)\n"
            f"HP: {self.health} ({self.health_bonus:+d}%)"
        )

        # draw image
        with ThreadPoolExecutor() as pool:
            buffer = await interaction.client.loop.run_in_executor(pool, self.draw_card)

        return content, discord.File(buffer, "card.png")


class DonationPolicy(IntEnum):
    ALWAYS_ACCEPT = 1
    REQUEST_APPROVAL = 2
    ALWAYS_DENY = 3


class Player(models.Model):
    discord_id = fields.BigIntField(
        description="Discord user ID", unique=True, validators=[DiscordSnowflakeValidator()]
    )
    donation_policy = fields.IntEnumField(
        DonationPolicy,
        description="How you want to handle donations",
        default=DonationPolicy.ALWAYS_ACCEPT,
    )
    balls: fields.BackwardFKRelation[BallInstance]

    def __str__(self) -> str:
        return str(self.discord_id)


class BlacklistedID(models.Model):
    discord_id = fields.BigIntField(
        description="Discord user ID", unique=True, validators=[DiscordSnowflakeValidator()]
    )
    reason = fields.TextField(null=True, default=None)
    date = fields.DatetimeField(null=True, default=None, auto_now_add=True)

    def __str__(self) -> str:
        return str(self.discord_id)


class BlacklistedGuild(models.Model):
    discord_id = fields.BigIntField(
        description="Discord Guild ID", unique=True, validators=[DiscordSnowflakeValidator()]
    )
    reason = fields.TextField(null=True, default=None)
    date = fields.DatetimeField(null=True, default=None, auto_now_add=True)

    def __str__(self) -> str:
        return str(self.discord_id)
