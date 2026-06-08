from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
from django.db import models
from django.utils import timezone

from bd_models.models import Ball, Player, Special, balls, specials

merchant_items: dict[int, "MerchantItem"] = {}
global_shops: dict[int, "GlobalShop"] = {}


class MerchantSettings(models.Model):
    rotation = models.PositiveIntegerField(
        help_text="Duration of the items in minutes. Default to 24 hours.", default=1440
    )
    items = models.PositiveBigIntegerField(
        help_text="How many items will be in the store. Default to 3 items.", default=3
    )
    token_ball = models.OneToOneField(
        Ball,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="for /merchant convert_token, set the ball to use as a token",
    )
    token_ball_id: int | None
    token_conversion_rate = models.PositiveIntegerField(
        help_text=(
            "Coins received for each token converted when using /merchant convert_token\nExample: 1 token = 100 coins"
        ),
        default=1500,
    )

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    async def aload(cls):
        return await sync_to_async(cls.load)()

    @property
    def cached_token_ball(self) -> "Ball | None":
        return balls.get(self.token_ball_id) or self.token_ball if self.token_ball_id else None

    @property
    def rotation_delta(self) -> timedelta:
        return timedelta(minutes=self.rotation)

    class Meta:
        managed = True
        db_table = "merchantsettings"

    def __str__(self) -> str:
        return "Merchant Settings"


class MerchantItem(models.Model):
    name = models.CharField(unique=True, max_length=64)
    prize = models.PositiveIntegerField(null=True, blank=True)
    start_date = models.DateTimeField(
        help_text="Start time of the item. If blank, starts immediately", null=True, blank=True
    )
    end_date = models.DateTimeField(
        help_text="End time of the item. If blank, the item is permanent", null=True, blank=True
    )
    rarity = models.FloatField(help_text="Value between 0 and 1, determine if a item is rarest than other")
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE)
    ball_id: int
    special = models.ForeignKey(Special, null=True, blank=True, on_delete=models.SET_NULL)
    special_id: int | None
    created_at = models.DateTimeField(editable=False, auto_now_add=True)

    @property
    def cached_ball(self) -> "Ball":
        return balls.get(self.ball_id) or self.ball

    @property
    def cached_special(self) -> "Special | None":
        return specials.get(self.special_id) or self.special if self.special_id else None

    @property
    def enabled(self) -> bool:
        """
        Checks if this item is active.
        """
        return (
            (self.start_date or datetime.min.replace(tzinfo=timezone.get_default_timezone()))
            <= timezone.now()
            <= (self.end_date or datetime.max.replace(tzinfo=timezone.get_default_timezone()))
        )

    def __str__(self) -> str:
        return self.name

    class Meta:
        managed = True
        db_table = "merchantitem"


class MerchantInstance(models.Model):
    player = models.OneToOneField(Player, on_delete=models.CASCADE, related_name="merchant")
    items = models.ManyToManyField(MerchantItem, blank=True)
    rotation_ends_at = models.DateTimeField()

    @property
    def rotation_expired(self) -> bool:
        """
        Check if the rotation has ended.
        """
        return self.rotation_ends_at <= timezone.now()

    class Meta:
        managed = True
        db_table = "merchantinstance"


class GlobalShop(models.Model):
    name = models.CharField(max_length=64, unique=True)
    banner = models.ImageField(null=True, blank=True, help_text="An optional promotional banner for this shop.")
    items = models.ManyToManyField(MerchantItem, blank=True)

    class Meta:
        managed = True
        db_table = "globalshop"
