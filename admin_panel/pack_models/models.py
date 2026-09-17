from datetime import timedelta

from asgiref.sync import sync_to_async
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from bd_models.models import Player


class PackResource(models.Model):
    player = models.OneToOneField(Player, on_delete=models.CASCADE, related_name="pack_resource")
    daily_uses = models.PositiveIntegerField(default=0)
    weekly_uses = models.PositiveIntegerField(default=0)
    daily_cooldown = models.DateTimeField(null=True, blank=True)
    weekly_cooldown = models.DateTimeField(null=True, blank=True)

    # a "daily cycle" starts with the first daily pack opened after the cooldown is over
    daily_cycle_started_at = models.DateTimeField(null=True, blank=True)
    daily_streak = models.PositiveIntegerField(
        default=0, help_text="How many daily cycles in a row the player opened daily packs."
    )
    daily_bonus_uses = models.PositiveIntegerField(
        default=0, help_text="Bonus daily packs earned during the current cycle (luck or streak)."
    )
    daily_bonus_rolled = models.BooleanField(
        default=False, help_text="Whether the chance of a bonus daily pack was already rolled this cycle."
    )

    async def set_daily_cooldown(self):
        self.daily_cooldown = timezone.now()
        await self.asave(update_fields=("daily_cooldown",))

    async def set_weekly_cooldown(self):
        self.weekly_cooldown = timezone.now()
        await self.asave(update_fields=("weekly_cooldown",))

    async def remove_daily_cooldown(self):
        self.daily_cooldown = None
        self.daily_uses = 0
        await self.asave(update_fields=("daily_cooldown", "daily_uses"))

    async def remove_weekly_cooldown(self):
        self.weekly_cooldown = None
        self.weekly_uses = 0
        await self.asave(update_fields=("weekly_cooldown", "weekly_uses"))

    def daily_cooldown_active(self) -> bool:
        return self.daily_cooldown is not None and (self.daily_cooldown + timedelta(days=1)) > timezone.now()

    async def is_daily_on_cooldown(self, refresh: bool = True) -> bool:
        if refresh:
            await self.arefresh_from_db(fields=["daily_cooldown"])
        return self.daily_cooldown_active()

    async def is_weekly_on_cooldown(self, refresh: bool = True) -> bool:
        if refresh:
            await self.arefresh_from_db(fields=["weekly_cooldown"])
        self.weekly_cooldown
        return self.weekly_cooldown is not None and (self.weekly_cooldown + timedelta(weeks=1)) > timezone.now()

    class Meta:
        db_table = "packresource"
        managed = True


class PackSettings(models.Model):
    min_rarity_daily = models.FloatField(help_text="Lowest rarity that can appear in daily packs.")
    max_rarity_daily = models.FloatField(help_text="Highest rarity that can appear in daily packs.")
    min_rarity_weekly = models.FloatField(help_text="Lowest rarity that can appear in weekly packs.")
    max_rarity_weekly = models.FloatField(help_text="Highest rarity that can appear in weekly packs.")

    daily_uses = models.PositiveIntegerField(
        default=3, help_text="How many daily packs every player can open before the 24 hours cooldown."
    )
    bonus_daily_chance = models.FloatField(
        default=0,
        validators=(MaxValueValidator(100),),
        help_text="Chance, in percent, to unlock a bonus daily pack when opening the last daily pack of the day. "
        "Rolled once per day. Set to 0 to disable.",
    )
    streak_bonus_days = models.PositiveIntegerField(
        default=0,
        help_text="Every time a player's daily pack streak reaches a multiple of this many days (7 = on day 7, 14, "
        "21...), they get a bonus daily pack that day. Set to 0 to disable.",
    )
    streak_grace_hours = models.PositiveIntegerField(
        default=48,
        help_text="Players must open a daily pack again within this many hours after starting their previous day "
        "to keep their streak going. Past this window, the streak starts over.",
    )

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "min_rarity_daily": 50.0,
                "max_rarity_daily": 100.0,
                "min_rarity_weekly": 1.0,
                "max_rarity_weekly": 50.0,
            },
        )
        return obj

    @classmethod
    async def aload(cls):
        return await sync_to_async(cls.load)()

    class Meta:
        db_table = "packsettings"
        managed = True
        constraints = [
            models.CheckConstraint(condition=Q(min_rarity_daily__gte=0), name="packsettings_min_rarity_daily_gte_0"),
            models.CheckConstraint(condition=Q(max_rarity_daily__gte=0), name="packsettings_max_rarity_daily_gte_0"),
            models.CheckConstraint(condition=Q(min_rarity_weekly__gte=0), name="packsettings_min_rarity_weekly_gte_0"),
            models.CheckConstraint(condition=Q(max_rarity_weekly__gte=0), name="packsettings_max_rarity_weekly_gte_0"),
            models.CheckConstraint(
                condition=Q(min_rarity_daily__lte=F("max_rarity_daily")), name="packsettings_daily_min_lte_max"
            ),
            models.CheckConstraint(
                condition=Q(min_rarity_weekly__lte=F("max_rarity_weekly")), name="packsettings_weekly_min_lte_max"
            ),
        ]


class PackBonusRole(models.Model):
    """
    A Discord role giving extra daily packs. A player with several of these roles gets every bonus added together,
    but only when opening their daily packs in the server the role belongs to.
    """

    server_id = models.BigIntegerField(help_text="Discord server ID the role belongs to.")
    role_id = models.BigIntegerField(help_text="Role ID giving extra daily packs.")
    bonus_daily_uses = models.PositiveIntegerField(
        default=1, help_text="How many extra daily packs this role gives every day."
    )

    class Meta:
        db_table = "packbonusrole"
        managed = True
        unique_together = (("server_id", "role_id"),)

    def __str__(self) -> str:
        return f"Role {self.role_id} (+{self.bonus_daily_uses} daily packs)"
