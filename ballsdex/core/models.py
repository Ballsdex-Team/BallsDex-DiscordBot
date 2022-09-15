from __future__ import annotations

import discord

from io import BytesIO
from enum import IntEnum
from datetime import datetime
from typing import Tuple

from tortoise import models, fields, validators, exceptions
from fastapi_admin.models import AbstractAdmin


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


class Regime(IntEnum):
    DEMOCRACY = 1
    DICTATORSHIP = 2
    UNION = 3


class Economy(IntEnum):
    CAPITALIST = 1
    COMMUNIST = 2
    ANARCHY = 3


class Ball(models.Model):
    country = fields.CharField(max_length=48, unique=True)
    regime = fields.IntEnumField(Regime, description="Political regime of this country")
    economy = fields.IntEnumField(Economy, description="Economical regime of this country")
    health = fields.IntField(description="Ball health stat")
    attack = fields.IntField(description="Ball attack stat")
    rarity = fields.FloatField(description="Rarity of this ball")
    enabled = fields.BooleanField(default=True)
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


class BallInstance(models.Model):
    ball: fields.ForeignKeyRelation[Ball] = fields.ForeignKeyField("models.Ball")
    player: fields.ForeignKeyRelation[Player] = fields.ForeignKeyRelation(
        "models.Player", related_name="balls"
    )  # type: ignore
    count = fields.IntField()
    catch_date = fields.DatetimeField(auto_now_add=True)
    special = fields.IntField(description="Defines rare instances, like a shiny", default=0)
    health_bonus = fields.IntField(default=0)
    attack_bonus = fields.IntField(default=0)
    trade_player: fields.ForeignKeyRelation[Player] = fields.ForeignKeyField(
        "models.Player", null=True, default=None
    )
    favorite = fields.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.ball.country} #{self.count}"

    class Meta:
        unique_together = ("player", "id")

    @property
    def attack(self) -> int:
        bonus = int(self.ball.attack * self.attack_bonus * 0.01)
        return self.ball.attack + bonus

    @property
    def health(self) -> int:
        bonus = int(self.ball.health * self.health_bonus * 0.01)
        return self.ball.health + bonus

    def prepare_for_message(self) -> Tuple[discord.Embed, BytesIO]:
        from ballsdex.core.image_generator.image_gen import draw_card

        ball = self.ball
        embed = discord.Embed()

        if ball.regime == Regime.DEMOCRACY:
            embed.colour = discord.Colour.blue()
        elif ball.regime == Regime.DICTATORSHIP:
            embed.colour = discord.Colour.red()
        elif ball.regime == Regime.UNION:
            embed.colour = discord.Colour.green()

        embed.title = f"{self.count}# {ball.country}"
        embed.description = (
            f"Caught on {self.catch_date}\n"
            f"Special: {self.special}\n"
            f"Attack: `{self.attack_bonus + ball.attack}`\n"
            f"Health: `{self.health_bonus + ball.health}`"
        )
        image = draw_card(self)
        buffer = BytesIO()
        image.save(buffer, format="png")
        buffer.seek(0)

        return embed, buffer


class Player(models.Model):
    discord_id = fields.BigIntField(
        description="Discord user ID", unique=True, validators=[DiscordSnowflakeValidator()]
    )
    balls: fields.BackwardFKRelation[BallInstance]

    def __str__(self) -> str:
        return str(self.discord_id)
