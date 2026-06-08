from typing import Iterable

from asgiref.sync import sync_to_async
from django.db import models
from django.forms import ValidationError

from bd_models.models import Ball, BallInstance, Special, balls, specials


class Buff(models.Model):
    ball = models.OneToOneField(
        Ball, on_delete=models.CASCADE, null=True, blank=True, help_text="Ball that will receive an increase"
    )
    ball_id: int | None
    special = models.OneToOneField(
        Special, on_delete=models.CASCADE, null=True, blank=True, help_text="Specials that will receive an increase"
    )
    special_id: int | None
    health = models.IntegerField(default=0, help_text="Amount of health to add")
    attack = models.IntegerField(default=0, help_text="Amount of attack to add")

    @classmethod
    def get_buff(cls, instance: "BallInstance"):
        buff = cls.objects.filter(ball=instance.countryball).first()
        if not buff:
            special = instance.specialcard
            if special:
                buff = cls.objects.filter(special=special).first()
        return buff

    @classmethod
    async def aget_buff(cls, instance: "BallInstance"):
        return await sync_to_async(cls.get_buff)(instance)

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        has_ball = self.ball is not None
        has_special = self.special is not None
        if not has_ball and not has_special:
            raise ValidationError("You must provide either a ball or a special.")

        if has_ball and has_special:
            raise ValidationError("You cannot set both a ball and a special.")

        return super().save(force_insert, force_update, using, update_fields)

    @property
    def cached_ball(self):
        return balls.get(self.ball_id) or self.ball if self.ball_id else None

    @property
    def cached_special(self):
        return specials.get(self.special_id) or self.special if self.special_id else None

    class Meta:
        managed = True
        db_table = "buff"

    def display(self):
        if self.cached_ball:
            text = f"{self.cached_ball.country} "
        elif self.cached_special:
            text = f"{self.cached_special.name} "
        else:
            text = ""
        return f"{text} buff"

    def __str__(self):
        return self.display()
