from django.db import models

from bd_models.models import Ball, Player, Special, balls, specials


class Collectible(models.Model):
    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(null=True, blank=True, help_text="An optional descripcion for this collectible")
    emoji_id = models.BigIntegerField(help_text="Emoji ID of this collectible")
    price = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="The price of this collectible. If blanks, it will free."
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    # Requirement Values
    ball = models.ForeignKey(
        Ball,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="An optional requirement that specifies a required ball.",
    )
    ball_id: int | None
    special = models.ForeignKey(
        Special,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="An optional requirement that specifies a required special.",
    )
    special_id: int | None
    amount = models.IntegerField(null=True, blank=True)

    @property
    def has_requirements(self) -> bool:
        return self.amount is not None or self.ball_id is not None or self.special_id is not None

    @property
    def cached_ball(self) -> Ball | None:
        return balls.get(self.ball_id) or self.ball if self.ball_id is not None else None

    @property
    def cached_special(self) -> Special | None:
        return specials.get(self.special_id) or self.special if self.special_id is not None else None

    def __str__(self):
        return self.name

    class Meta:
        managed = True
        db_table = "collectible"
        verbose_name_plural = "Collectibles"
        indexes = [models.Index(fields=["name"]), models.Index(fields=["ball"]), models.Index(fields=["special"])]


class CollectibleInstance(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="collectibles")
    collectible = models.ForeignKey(Collectible, on_delete=models.CASCADE)
    obtained_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = True
        db_table = "collectibleinstance"
        indexes = [models.Index(fields=["player"]), models.Index(fields=["collectible"])]
