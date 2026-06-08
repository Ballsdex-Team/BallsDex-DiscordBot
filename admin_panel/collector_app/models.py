from __future__ import annotations

from django.db import models

from bd_models.models import Ball, Player, Special, balls, specials


class Collector(models.Model):
    name = models.CharField(max_length=64, unique=True)
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE, null=True, blank=True)
    ball_id: int | None
    special = models.ForeignKey(Special, on_delete=models.SET_NULL, null=True, blank=True)
    special_id: int | None
    start_date = models.DateTimeField(
        help_text="Start date of this collector. If blank, it starts immediately", null=True, blank=True
    )
    end_date = models.DateTimeField(
        help_text="End date of this collector. If blank, collector is permanent", null=True, blank=True
    )
    tradeable = models.BooleanField(
        default=True, help_text="Marks if all CC instances can be traded or not (default: true)"
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    requirements: models.QuerySet[CollectorRequirement]

    @property
    def cached_ball(self) -> "Ball | None":
        return balls.get(self.ball_id) or self.ball if self.ball_id else None

    @property
    def cached_special(self) -> "Special | None":
        return specials.get(self.special_id) or self.special if self.special_id else None

    def __str__(self):
        return self.name

    class Meta:
        managed = True
        db_table = "collector"
        indexes = [models.Index(fields=("ball",)), models.Index(fields=("special",))]


class CollectorRequirement(models.Model):
    collector = models.ForeignKey(Collector, on_delete=models.CASCADE, related_name="requirements")
    ball = models.ForeignKey(Ball, on_delete=models.SET_NULL, null=True, blank=True)
    ball_id: int | None
    special = models.ForeignKey(Special, on_delete=models.SET_NULL, null=True, blank=True)
    special_id: int | None
    amount = models.PositiveIntegerField(default=1)
    delete_balls = models.BooleanField(
        default=False, help_text="If a user meets all requirements, will the required balls be removed? "
    )

    @property
    def cached_ball(self) -> "Ball | None":
        return balls.get(self.ball_id) or self.ball if self.ball_id else None

    @property
    def cached_special(self) -> "Special | None":
        return specials.get(self.special_id) or self.special if self.special_id else None

    def __str__(self):
        title = f"{self.collector.name} requirement: X{self.amount} "
        if self.ball:
            title += f"{self.ball.country} "
        if self.special:
            title += f"{self.special.name}"
        return title

    class Meta:
        managed = True
        db_table = "collectorrequirement"
        indexes = [
            models.Index(fields=("collector",)),
            models.Index(fields=("ball",)),
            models.Index(fields=("special",)),
            models.Index(fields=("amount",)),
        ]


class CollectorInstance(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    collector = models.ForeignKey(Collector, on_delete=models.CASCADE)

    class Meta:
        managed = True
        db_table = "collectorinstance"
        unique_together = (("player", "collector"),)
        indexes = [models.Index(fields=("player",)), models.Index(fields=("collector",))]
