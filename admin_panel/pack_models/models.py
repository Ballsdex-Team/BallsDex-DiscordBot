from datetime import timedelta

from asgiref.sync import sync_to_async
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

    async def is_daily_on_cooldown(self, refresh: bool = True) -> bool:
        if refresh:
            await self.arefresh_from_db(fields=["daily_cooldown"])
        self.daily_cooldown
        return self.daily_cooldown is not None and (self.daily_cooldown + timedelta(days=1)) > timezone.now()

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
