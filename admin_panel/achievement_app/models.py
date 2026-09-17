from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings as django_settings
from django.db import models

from bd_models.models import Ball, BallGroup, Player, Special, balls, groups, specials
from settings.models import settings

if TYPE_CHECKING:
    from bd_models.models import BallInstance


class AchievementType(models.TextChoices):
    CATCH = "catch", "Catch treasures"
    OBTAIN = "obtain", "Obtain treasures (catch, trade, pack, claim...)"
    OWN = "own", "Own treasures at the same time"
    COMPLETE_GROUP = "complete_group", "Complete a group"
    COMPLETION = "completion", "Reach a completion percentage"
    TRADE = "trade", "Complete trades"
    FRIENDS = "friends", "Have friends"
    FAVORITES = "favorites", "Have favorite treasures"
    BATTLE_WIN = "battle_win", "Win battles"
    PLAYTIME = "playtime", "Play since the first catch"


class TimeUnit(models.TextChoices):
    DAYS = "days", "Days"
    MONTHS = "months", "Months"
    YEARS = "years", "Years"


DAYS_PER_UNIT = {TimeUnit.DAYS: 1, TimeUnit.MONTHS: 30, TimeUnit.YEARS: 365}


class PrerequisiteLogic(models.TextChoices):
    ALL = "all", "All required"
    ANY = "any", "Any one Required"


class AchievementCategory(models.Model):
    name = models.CharField(max_length=64, unique=True)
    emoji = models.CharField(max_length=64, blank=True, default="", help_text="Optional emoji shown next to the name.")
    position = models.PositiveSmallIntegerField(default=0, help_text="Categories are listed from the lowest position.")

    def __str__(self) -> str:
        return f"{self.emoji} {self.name}".strip()

    class Meta:
        managed = True
        db_table = "achievementcategory"
        ordering = ("position", "name")
        verbose_name_plural = "achievement categories"


class Achievement(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft (proposal, not live)"
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired (can't be unlocked anymore)"

    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(
        null=True, blank=True, help_text="Shown to players. Leave empty to show the goal generated from the settings."
    )
    thumbnail = models.ImageField(max_length=200, help_text="128x128 PNG image", null=True, blank=True)
    category = models.ForeignKey(
        AchievementCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="achievements"
    )
    category_id: int | None
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    hidden = models.BooleanField(
        default=False, help_text="Secret achievement: players only see its name and description once unlocked."
    )
    position = models.PositiveIntegerField(default=0, help_text="Achievements are listed from the lowest position.")

    type = models.CharField(max_length=48, choices=AchievementType.choices)
    target_value = models.PositiveBigIntegerField(
        verbose_name="goal", help_text="How much progress is needed, the unit depends on the type."
    )

    # filters, which ones are used depends on the type
    ball = models.ForeignKey(Ball, null=True, blank=True, on_delete=models.SET_NULL)
    ball_id: int | None
    special = models.ForeignKey(Special, null=True, blank=True, on_delete=models.SET_NULL)
    special_id: int | None
    any_special = models.BooleanField(
        default=False, help_text="Only count treasures with a special, whichever it is. Ignored if a special is set."
    )
    group = models.ForeignKey(BallGroup, null=True, blank=True, on_delete=models.SET_NULL)
    group_id: int | None
    server_id = models.BigIntegerField(
        null=True, blank=True, help_text="Only count treasures caught in this Discord server (ID)."
    )
    min_attack_bonus = models.IntegerField(null=True, blank=True, help_text="Minimum attack bonus, in percent.")
    min_health_bonus = models.IntegerField(null=True, blank=True, help_text="Minimum health bonus, in percent.")
    hex_contains = models.CharField(
        max_length=16, blank=True, default="", help_text="Only count treasures whose ID contains this text (hex)."
    )
    max_catch_seconds = models.FloatField(
        null=True, blank=True, help_text="Only count catches made within this many seconds after the spawn."
    )
    partner_discord_id = models.BigIntegerField(
        null=True, blank=True, help_text="Only count trades with this Discord user (ID)."
    )
    min_currency = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="Only count trades where the player receives at least this much currency."
    )
    must_receive_treasure = models.BooleanField(
        default=False, help_text="Only count trades where the player receives at least one treasure."
    )
    time_unit = models.CharField(max_length=8, choices=TimeUnit.choices, default=TimeUnit.DAYS)

    currency_reward = models.PositiveIntegerField(db_default=0, default=0, help_text="Currency given on unlock.")
    prerequisities: models.ManyToManyField[Achievement, Any] = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        verbose_name="prerequisites",
        help_text="Achievements that must be unlocked before this one starts progressing.",
    )
    prerequisite_logic = models.CharField(
        max_length=3, choices=PrerequisiteLogic.choices, default=PrerequisiteLogic.ALL
    )

    notes = models.TextField(blank=True, default="", help_text="Internal notes, never shown to players.")
    proposed_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    @property
    def cached_ball(self) -> Ball | None:
        return balls.get(self.ball_id) or self.ball if self.ball_id else None

    @property
    def cached_group(self) -> BallGroup | None:
        return groups.get(self.group_id) or self.group if self.group_id else None

    @property
    def cached_special(self) -> Special | None:
        return specials.get(self.special_id) or self.special if self.special_id else None

    @property
    def thumbnail_url(self) -> str | None:
        if not self.thumbnail:
            return None
        return f"{settings.site_base_url.rstrip('/')}/media/{self.thumbnail.name}"

    def matches_instance(self, instance: BallInstance) -> bool:
        """
        Whether a treasure passes the treasure filters of this achievement. The group cache must be loaded.
        """
        if self.ball_id and instance.ball_id != self.ball_id:
            return False
        if self.special_id:
            if instance.special_id != self.special_id:
                return False
        elif self.any_special and instance.special_id is None:
            return False
        if self.group_id:
            group = groups.get(self.group_id)
            if group is None or instance.ball_id not in group._ball_ids:
                return False
        if self.server_id and instance.server_id != self.server_id:
            return False
        if self.min_attack_bonus is not None and instance.attack_bonus < self.min_attack_bonus:
            return False
        if self.min_health_bonus is not None and instance.health_bonus < self.min_health_bonus:
            return False
        if self.hex_contains and self.hex_contains.lower() not in f"{instance.pk:x}":
            return False
        return True

    def __str__(self):
        return self.name

    class Meta:
        managed = True
        db_table = "achievement"
        ordering = ("category__position", "position", "name")


class UserAchievement(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    player_id: int
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    achievement_id: int
    progress = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.achievement_id} for {self.player_id}"

    class Meta:
        managed = True
        db_table = "userachievement"
        unique_together = (("player", "achievement"),)
        indexes = [models.Index(fields=("player_id",)), models.Index(fields=("achievement_id",))]


class PlayerAchievementStats(models.Model):
    """
    Facts about a player used by achievements that can't be read from other tables cheaply.
    """

    player = models.OneToOneField(Player, on_delete=models.CASCADE, related_name="achievement_stats")
    player_id: int
    first_catch_at = models.DateTimeField(
        null=True, blank=True, help_text="When the player caught a treasure themselves for the first time."
    )

    class Meta:
        managed = True
        db_table = "achievementplayerstats"
        verbose_name_plural = "player achievement stats"
