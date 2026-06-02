from typing import Iterable

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.db import models

from bd_models.models import Ball, Player, Special, balls


class CurrencySettings(models.Model):
    name = models.CharField(max_length=64)
    plural_name = models.CharField(max_length=64)
    emoji_id = models.BigIntegerField(help_text="Emoji id of the currency", null=True, blank=True)
    spawn_chance = models.FloatField(default=0.2, help_text="Value between 0 and 1, chances to spawn currency.")
    spawn_amount = models.PositiveIntegerField(default=500, help_text="The amount of currency to give from a spawn.")

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"name": "Coin", "plural_name": "Coins"})
        return obj

    @classmethod
    async def aload(cls):
        return await sync_to_async(cls.load)()

    def display_name(self, amount: int | None) -> str:
        if not amount:
            return ""
        return self.name if amount == 1 else self.plural_name

    class Meta:
        managed = True
        db_table = "currencysettings"

    def __str__(self) -> str:
        return self.name


class Item(models.Model):
    name = models.CharField(max_length=64)
    description = models.TextField(null=True, blank=True, help_text="An optional description for the item")
    prize = models.PositiveBigIntegerField(
        blank=True, null=True, help_text="The prize of the item. If blanks, it will free"
    )
    emoji_id = models.BigIntegerField(null=True, blank=False, help_text="Emoji Id of the item")
    minimum_rarity = models.FloatField(help_text="Minimum rarity range.", blank=True, null=True)
    maximum_rarity = models.FloatField(help_text="Maximum rarity range.", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    special = models.ForeignKey(
        Special, on_delete=models.SET_NULL, blank=True, null=True, help_text="The special of the item (optional)"
    )
    balls: models.QuerySet["ItemBall"]

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        has_min = self.minimum_rarity is not None
        has_max = self.maximum_rarity is not None
        has_rarity = has_min or has_max

        if has_rarity and not (has_min and has_max):
            raise ValidationError("You must define both minimum and maximum rarity.")

        if has_min and has_max and self.minimum_rarity > self.maximum_rarity:  # type: ignore
            raise ValidationError("Minimum rarity cannot be greater than maximum rarity.")

        return super().save(force_insert, force_update, using, update_fields)

    class Meta:
        managed = True
        db_table = "item"

    def __str__(self) -> str:
        return self.name


class ItemBall(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="balls")
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE)
    ball_id: int

    @property
    def cached_ball(self) -> Ball:
        return balls.get(self.ball_id) or self.ball

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        has_rarity = self.item.minimum_rarity and self.item.maximum_rarity
        if has_rarity:
            raise ValidationError("You must define null `minimum_rarity` and `maximum_rarity` in the original item.")

        return super().save(force_insert, force_update, using, update_fields)

    class Meta:
        managed = True
        db_table = "itemball"


class MoneyInstance(models.Model):
    player = models.OneToOneField(Player, on_delete=models.CASCADE)
    amount = models.BigIntegerField(default=0)

    class Meta:
        managed = True
        db_table = "moneyinstance"
