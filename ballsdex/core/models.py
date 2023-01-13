from __future__ import annotations

import discord
from discord.utils import format_dt

from io import BytesIO
from enum import IntEnum
from datetime import datetime
from typing import Tuple
from concurrent.futures import ThreadPoolExecutor

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
    democracy_card = fields.CharField(max_length=200)
    dictatorship_card = fields.CharField(max_length=200)
    union_card = fields.CharField(max_length=200)

    def __str__(self) -> str:
        return self.name

    def get_background(self, regime: Regime) -> str | None:
        if regime == Regime.DEMOCRACY:
            return self.democracy_card
        elif regime == Regime.DICTATORSHIP:
            return self.dictatorship_card
        elif regime == Regime.UNION:
            return self.union_card
        else:
            return None


class Ball(models.Model):
    country = fields.CharField(max_length=48, unique=True)
    short_name = fields.CharField(max_length=12, null=True, default=None)
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

    @property
    def special_card(self) -> str | None:
        if self.special:
            return self.special.get_background(self.ball.regime) or self.ball.collection_card

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
        await self.fetch_related("trade_player", "ball", "special")
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
            f"Caught on {format_dt(self.catch_date)} "
            f"({format_dt(self.catch_date, style='R')}).\n"
            f"{trade_content}\n"
            f"ATK: {self.attack} ({self.attack_bonus:+d}%)\n"
            f"HP: {self.health} ({self.health_bonus:+d}%)"
        )

        # draw image
        with ThreadPoolExecutor() as pool:
            buffer = await interaction.client.loop.run_in_executor(pool, self.draw_card)

        return content, discord.File(buffer, "card.png")


class Player(models.Model):
    discord_id = fields.BigIntField(
        description="Discord user ID", unique=True, validators=[DiscordSnowflakeValidator()]
    )
    balls: fields.BackwardFKRelation[BallInstance]

    def __str__(self) -> str:
        return str(self.discord_id)


class BlacklistedID(models.Model):
    discord_id = fields.BigIntField(
        description="Discord user ID", unique=True, validators=[DiscordSnowflakeValidator()]
    )

    def __str__(self) -> str:
        return str(self.discord_id)
