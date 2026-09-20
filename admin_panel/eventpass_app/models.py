"""
Event passes: timed sets of quests, grouped in tiers, rewarding players who complete them.

An `EventPass` is one event (the anniversary, a summer event...). It holds `PassTier` rows, the tiers players unlock
one after another, and each tier holds its `Quest` rows. A quest rewards a `Reward`, a reusable bundle of
`RewardLine` (berries, treasures, framed treasures) that players claim themselves.

Nothing here knows how a quest progresses: that is `engine.py`, fed by `ballsdex.core.game_events`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from collector_app.models import Collector, CollectorTierLevel
from currency_app.models import Item
from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from merchant_app.models import MerchantItem

from ballsdex.core.game_events import normalize_command
from bd_models.models import Ball, BallGroup, Player, Special, balls, groups, specials
from settings.models import settings

if TYPE_CHECKING:
    from datetime import datetime

    from bd_models.models import BallInstance


class QuestType(models.TextChoices):
    CATCH = "catch", "Catch treasures"
    OBTAIN = "obtain", "Obtain treasures (catch, trade, pack, craft...)"
    COMMAND = "command", "Use a command"
    TRADE = "trade", "Complete trades"
    TRADE_TREASURES = "trade_treasures", "Exchange treasures in trades"
    FRIEND = "friend", "Add friends"
    BATTLE_WIN = "battle_win", "Win battles"
    GIVE_CURRENCY = "give_currency", "Give berries to players"
    RECEIVE_CURRENCY = "receive_currency", "Receive berries from players"
    CATCH_CURRENCY = "catch_currency", "Earn berries by catching treasures"
    SPEND_CURRENCY = "spend_currency", "Spend berries"
    CRAFT = "craft", "Craft (claim a collector card)"
    PACK_BUY = "pack_buy", "Buy packs"
    MERCHANT_BUY = "merchant_buy", "Buy from the merchant"
    SHOP_BUY = "shop_buy", "Buy from Buggy's shop"
    SELL = "sell", "Sell treasures to Buggy"
    AUCTION_CREATE = "auction_create", "List treasures on the auction house"
    AUCTION_BID = "auction_bid", "Place bids on the auction house"
    AUCTION_WON = "auction_won", "Win auctions"


class Measure(models.TextChoices):
    COUNT = "count", "Number of times"
    AMOUNT = "amount", "Total berries"


class Reset(models.TextChoices):
    NONE = "none", "Once for the whole event"
    DAILY = "daily", "Every day"
    WEEKLY = "weekly", "Every week"


class Logic(models.TextChoices):
    ALL = "all", "All required"
    ANY = "any", "Any one required"


class Announce(models.TextChoices):
    PUBLIC = "public", "In the channel, where everyone sees it"
    EPHEMERAL = "ephemeral", "In the channel, but only the player sees it"
    PRIVATE = "private", "In the player's DMs only"
    NONE = "none", "No message at all"


class RewardKind(models.TextChoices):
    BERRIES = "berries", "Berries"
    TREASURE = "treasure", "Treasure"


class BonusMode(models.TextChoices):
    RANDOM = "random", "Random, like a catch"
    FIXED = "fixed", "The values set below"
    ZERO = "zero", "No bonus (+0%)"


class RequirementKind(models.TextChoices):
    QUESTS_ALL = "quests_all", "Complete these quests"
    QUESTS_COUNT = "quests_count", "Complete a number of quests of the previous tiers"
    PREVIOUS_TIER = "previous_tier", "Unlock the previous tier"
    OWN_TREASURES = "own_treasures", "Own treasures (tokens, a special...)"
    CURRENCY = "currency", "Have berries"
    DATE = "date", "Wait until a date"


class Source(models.TextChoices):
    """
    What a reward was given for, used to make sure it is only ever given once.
    """

    QUEST = "quest", "Quest"
    TIER = "tier", "Tier"
    FINAL = "final", "End of the pass"


TREASURE_FILTERS = (
    "ball",
    "special",
    "any_special",
    "group",
    "min_rarity",
    "max_rarity",
    "min_attack_bonus",
    "min_health_bonus",
    "hex_contains",
)


class Reward(models.Model):
    """
    A bundle of things given at once: berries, treasures, framed treasures, or several of them together.
    """

    name = models.CharField(max_length=64, unique=True, help_text="Internal name, so the bundle can be reused.")
    message = models.TextField(
        blank=True, default="", help_text="Shown to the player when they claim it. Leave empty for the default text."
    )
    emoji = models.CharField(max_length=64, blank=True, default="")
    lines: models.QuerySet[RewardLine]

    def __str__(self) -> str:
        return f"{self.emoji} {self.name}".strip()

    class Meta:
        managed = True
        db_table = "eventpassreward"
        ordering = ("name",)


class RewardLine(models.Model):
    reward = models.ForeignKey(Reward, on_delete=models.CASCADE, related_name="lines")
    reward_id: int
    kind = models.CharField(max_length=16, choices=RewardKind.choices, default=RewardKind.TREASURE)
    position = models.PositiveSmallIntegerField(default=0)

    # berries
    amount = models.PositiveBigIntegerField(default=0, help_text="Berries given, for a berry line.")

    # treasures
    ball = models.ForeignKey(Ball, null=True, blank=True, on_delete=models.CASCADE)
    ball_id: int | None
    quantity = models.PositiveSmallIntegerField(default=1, help_text="How many copies of the treasure are given.")
    special = models.ForeignKey(Special, null=True, blank=True, on_delete=models.SET_NULL)
    special_id: int | None
    frame_key = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text='Frame given to the treasure, as its key in the Frames section ("09-20-2026", or '
        '"09-20-2026:3" for a frame of one special). Leave empty for a normal card.',
    )
    bonus_mode = models.CharField(max_length=8, choices=BonusMode.choices, default=BonusMode.RANDOM)
    attack_bonus = models.IntegerField(default=0, help_text="Used when the bonuses are fixed.")
    health_bonus = models.IntegerField(default=0, help_text="Used when the bonuses are fixed.")
    tradeable = models.BooleanField(
        default=True,
        help_text="Uncheck to give a treasure nobody can trade, sell or auction, whatever its usual rules.",
    )

    @property
    def cached_ball(self) -> Ball | None:
        return balls.get(self.ball_id) or self.ball if self.ball_id else None

    @property
    def cached_special(self) -> Special | None:
        return specials.get(self.special_id) or self.special if self.special_id else None

    def clean(self):
        super().clean()
        if self.kind == RewardKind.BERRIES and not self.amount:
            raise ValidationError({"amount": "A berry reward needs an amount."})
        if self.kind == RewardKind.TREASURE and not self.ball_id:
            raise ValidationError({"ball": "A treasure reward needs a treasure."})

    def __str__(self) -> str:
        if self.kind == RewardKind.BERRIES:
            return f"{self.amount:,} {settings.currency_plural}"
        ball = self.cached_ball
        special = self.cached_special
        text = f"{self.quantity}x {special.name + ' ' if special else ''}{ball.country if ball else '?'}"
        return f"{text} (framed)" if self.frame_key else text

    class Meta:
        managed = True
        db_table = "eventpassrewardline"
        ordering = ("position", "pk")


class EventPass(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft (only staff can see it)"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived (over, nothing can be claimed)"

    name = models.CharField(max_length=64, unique=True)
    emoji = models.CharField(max_length=64, blank=True, default="")
    description = models.TextField(blank=True, default="", help_text="Shown at the top of the pass.")
    banner = models.ImageField(max_length=200, null=True, blank=True, help_text="Optional banner image.")
    colour = models.CharField(
        max_length=7, blank=True, default="", help_text="Accent colour of the pass, like #E63946. Optional."
    )
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)

    starts_at = models.DateTimeField(help_text="Nothing progresses before this date.")
    ends_at = models.DateTimeField(help_text="Quests stop progressing after this date.")
    claim_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Players can still claim what they finished until this date. Leave empty to stop with the event.",
    )

    main_server_id = models.BigIntegerField(
        null=True, blank=True, help_text="Discord ID of the main server, for the quests limited to it."
    )
    main_server_only = models.BooleanField(
        default=False, help_text="Only count what players do in the main server. Quests can also ask for it one by one."
    )
    final_reward = models.ForeignKey(
        Reward,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Given when every tier is unlocked. Leave empty if the pass has no final reward.",
    )
    final_reward_id: int | None
    final_message = models.TextField(blank=True, default="", help_text="Shown when the pass is completed.")
    position = models.PositiveSmallIntegerField(default=0, help_text="Passes are listed from the lowest position.")

    notes = models.TextField(blank=True, default="", help_text="Internal notes, never shown to players.")
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    tiers: models.QuerySet[PassTier]
    quests: models.QuerySet[Quest]

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "The pass must end after it starts."})
        if self.claim_until and self.ends_at and self.claim_until < self.ends_at:
            raise ValidationError({"claim_until": "Claiming can't close before the pass ends."})
        if self.colour and not (self.colour.startswith("#") and len(self.colour) == 7):
            raise ValidationError({"colour": "Use the #RRGGBB form, like #E63946."})
        if self.main_server_only and not self.main_server_id:
            raise ValidationError({"main_server_id": "Set the ID of the main server to limit the pass to it."})

    @property
    def accent_colour(self) -> int:
        if self.colour:
            try:
                return int(self.colour.lstrip("#"), 16)
            except ValueError:
                pass
        return settings.embed_colour

    @property
    def banner_url(self) -> str | None:
        if not self.banner:
            return None
        return f"{settings.site_base_url.rstrip('/')}/media/{self.banner.name}"

    def running(self, now: datetime | None = None) -> bool:
        """
        Whether quests can progress right now.
        """
        now = now or timezone.now()
        return self.status == self.Status.ACTIVE and self.starts_at <= now <= self.ends_at

    def claimable(self, now: datetime | None = None) -> bool:
        """
        Whether players can still claim what they completed.
        """
        now = now or timezone.now()
        if self.status != self.Status.ACTIVE:
            return False
        return now <= (self.claim_until or self.ends_at)

    def __str__(self) -> str:
        return f"{self.emoji} {self.name}".strip()

    class Meta:
        managed = True
        db_table = "eventpass"
        ordering = ("position", "-starts_at")
        verbose_name = "event pass"
        verbose_name_plural = "event passes"


class PassTier(models.Model):
    event_pass = models.ForeignKey(EventPass, on_delete=models.CASCADE, related_name="tiers")
    event_pass_id: int
    name = models.CharField(max_length=64)
    emoji = models.CharField(max_length=64, blank=True, default="")
    description = models.TextField(blank=True, default="")
    position = models.PositiveSmallIntegerField(default=0, help_text="Tiers are listed from the lowest position.")

    unlock_logic = models.CharField(
        max_length=3,
        choices=Logic.choices,
        default=Logic.ALL,
        help_text="Whether every requirement below is needed, or only one of them.",
    )
    locked_message = models.TextField(
        blank=True, default="", help_text="Shown while the tier is locked. Leave empty for the generated text."
    )
    reward = models.ForeignKey(
        Reward,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional reward given for unlocking the tier itself.",
    )
    reward_id: int | None

    requirements: models.QuerySet[TierRequirement]
    quests: models.QuerySet[Quest]

    def __str__(self) -> str:
        return f"{self.event_pass.name} — {self.emoji} {self.name}".strip()

    class Meta:
        managed = True
        db_table = "eventpasstier"
        ordering = ("event_pass__position", "position", "pk")
        unique_together = (("event_pass", "name"),)


class TierRequirement(models.Model):
    """
    One condition to unlock a tier. Several of them combine with the tier's logic (all of them, or any one).
    """

    tier = models.ForeignKey(PassTier, on_delete=models.CASCADE, related_name="requirements")
    tier_id: int
    kind = models.CharField(max_length=16, choices=RequirementKind.choices)

    quests: models.ManyToManyField[Quest, models.Model] = models.ManyToManyField(
        "Quest", blank=True, related_name="unlocks", help_text="The quests to complete, for that kind of requirement."
    )
    count = models.PositiveIntegerField(
        default=0, help_text="How many quests, treasures or berries are needed, depending on the kind."
    )
    ball = models.ForeignKey(
        Ball, null=True, blank=True, on_delete=models.CASCADE, help_text="The treasure players must own."
    )
    ball_id: int | None
    special = models.ForeignKey(Special, null=True, blank=True, on_delete=models.SET_NULL)
    special_id: int | None
    date = models.DateTimeField(null=True, blank=True, help_text="The tier opens at this date.")

    @property
    def cached_ball(self) -> Ball | None:
        return balls.get(self.ball_id) or self.ball if self.ball_id else None

    @property
    def cached_special(self) -> Special | None:
        return specials.get(self.special_id) or self.special if self.special_id else None

    def clean(self):
        super().clean()
        if self.kind in (RequirementKind.QUESTS_COUNT, RequirementKind.OWN_TREASURES, RequirementKind.CURRENCY):
            if not self.count:
                raise ValidationError({"count": "This requirement needs a number."})
        if self.kind == RequirementKind.OWN_TREASURES and not (self.ball_id or self.special_id):
            raise ValidationError({"ball": "Choose the treasure or the special players must own."})
        if self.kind == RequirementKind.DATE and not self.date:
            raise ValidationError({"date": "Choose the date the tier opens."})

    def __str__(self) -> str:
        return self.get_kind_display()

    class Meta:
        managed = True
        db_table = "eventpasstierrequirement"
        ordering = ("pk",)


class Quest(models.Model):
    event_pass = models.ForeignKey(EventPass, on_delete=models.CASCADE, related_name="quests")
    event_pass_id: int
    tier = models.ForeignKey(
        PassTier,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quests",
        help_text="Leave empty for a quest available as soon as the pass starts.",
    )
    tier_id: int | None

    name = models.CharField(max_length=64)
    description = models.TextField(
        blank=True, default="", help_text="Shown to players. Leave empty to use the goal generated from the settings."
    )
    emoji = models.CharField(max_length=64, blank=True, default="")
    thumbnail = models.ImageField(max_length=200, null=True, blank=True, help_text="128x128 PNG image")
    position = models.PositiveSmallIntegerField(default=0, help_text="Quests are listed from the lowest position.")
    enabled = models.BooleanField(default=True, help_text="Uncheck to hide the quest without deleting it.")
    hidden = models.BooleanField(default=False, help_text="Secret quest: players only see it once they completed it.")

    type = models.CharField(max_length=24, choices=QuestType.choices)
    target = models.PositiveBigIntegerField(verbose_name="goal", default=1, help_text="How much progress is needed.")
    measure = models.CharField(
        max_length=8,
        choices=Measure.choices,
        default=Measure.COUNT,
        help_text="Whether the goal counts actions or adds up berries.",
    )
    reset = models.CharField(
        max_length=8, choices=Reset.choices, default=Reset.NONE, help_text="How often the quest comes back."
    )
    claim_required = models.BooleanField(
        default=True, help_text="Players press a button to get the reward. Uncheck to give it as soon as they finish."
    )
    starts_at = models.DateTimeField(null=True, blank=True, help_text="Optional, defaults to the start of the pass.")
    ends_at = models.DateTimeField(null=True, blank=True, help_text="Optional, defaults to the end of the pass.")

    reward = models.ForeignKey(Reward, null=True, blank=True, on_delete=models.SET_NULL, related_name="quests")
    reward_id: int | None
    announce = models.CharField(
        max_length=9,
        choices=Announce.choices,
        default=Announce.PUBLIC,
        verbose_name="completion message",
        help_text="Where the message goes when a player completes this quest. The private one in the channel needs "
        "the player to have used the bot in the last 15 minutes, otherwise it lands in their DMs.",
    )
    completion_message = models.TextField(
        blank=True, default="", help_text="Shown when the quest is completed. Leave empty for the default text."
    )

    # -- filters, which ones are used depends on the type
    ball = models.ForeignKey(Ball, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    ball_id: int | None
    special = models.ForeignKey(Special, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    special_id: int | None
    any_special = models.BooleanField(
        default=False, help_text="Only count treasures with a special, whichever it is. Ignored if a special is set."
    )
    group = models.ForeignKey(BallGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    group_id: int | None
    min_rarity = models.FloatField(
        null=True, blank=True, help_text="Only count treasures at least this rare (the rarity value, 0 to 1)."
    )
    max_rarity = models.FloatField(null=True, blank=True, help_text="Only count treasures up to this rarity value.")
    min_attack_bonus = models.IntegerField(null=True, blank=True, help_text="Minimum attack bonus, in percent.")
    min_health_bonus = models.IntegerField(null=True, blank=True, help_text="Minimum health bonus, in percent.")
    hex_contains = models.CharField(
        max_length=16, blank=True, default="", help_text="Only count treasures whose ID contains this text (hex)."
    )
    max_catch_seconds = models.FloatField(
        null=True, blank=True, help_text="Only count catches made within this many seconds after the spawn."
    )
    main_server_only = models.BooleanField(
        default=False, help_text="Only count what the player does in the main server."
    )
    partner_discord_id = models.BigIntegerField(
        null=True, blank=True, help_text="Only count actions involving this Discord user (ID)."
    )
    min_currency = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="Each action must move at least this many berries to count."
    )
    must_receive_treasure = models.BooleanField(
        default=False, help_text="Only count trades where the player receives at least one treasure."
    )
    in_one_trade = models.BooleanField(
        default=False, help_text="Ask for a single trade exchanging that many treasures, instead of a total."
    )
    command_name = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text='Full name of the slash command, without the slash: "treasures list" to open the inventory.',
    )
    item = models.ForeignKey(
        Item,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Only count this pack. Leave empty for any pack.",
    )
    item_id: int | None
    merchant_item = models.ForeignKey(
        MerchantItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Only count this merchant item. Leave empty for any item.",
    )
    merchant_item_id: int | None
    collector = models.ForeignKey(
        Collector,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Only count crafts of this collector. Leave empty for any.",
    )
    collector_id: int | None
    tier_level = models.ForeignKey(
        CollectorTierLevel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="craft type",
        help_text='Only count crafts of this kind ("Craft", "Elemental"...). Leave empty for any.',
    )
    tier_level_id: int | None

    notes = models.TextField(blank=True, default="", help_text="Internal notes, never shown to players.")

    def clean(self):
        super().clean()
        self.command_name = normalize_command(self.command_name)
        if self.target < 1:
            raise ValidationError({"target": "The goal must be at least 1."})
        if self.tier_id and self.tier.event_pass_id != self.event_pass_id:
            raise ValidationError({"tier": "This tier belongs to another pass."})
        if self.min_rarity is not None and self.max_rarity is not None and self.min_rarity > self.max_rarity:
            raise ValidationError({"max_rarity": "The maximum rarity must be above the minimum."})

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

    def window(self, event_pass: EventPass | None = None) -> tuple[datetime, datetime]:
        """
        When this quest can progress: its own dates, or the dates of the pass.
        """
        event_pass = event_pass or self.event_pass
        return (self.starts_at or event_pass.starts_at, self.ends_at or event_pass.ends_at)

    def matches_instance(self, instance: BallInstance) -> bool:
        """
        Whether a treasure passes the treasure filters of this quest. The caches must be loaded.
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
        if self.min_rarity is not None or self.max_rarity is not None:
            ball = balls.get(instance.ball_id)
            rarity = ball.rarity if ball else None
            if rarity is None:
                return False
            if self.min_rarity is not None and rarity < self.min_rarity:
                return False
            if self.max_rarity is not None and rarity > self.max_rarity:
                return False
        if self.min_attack_bonus is not None and instance.attack_bonus < self.min_attack_bonus:
            return False
        if self.min_health_bonus is not None and instance.health_bonus < self.min_health_bonus:
            return False
        if self.hex_contains and self.hex_contains.lower() not in f"{instance.pk:x}":
            return False
        return True

    def __str__(self) -> str:
        return self.name

    class Meta:
        managed = True
        db_table = "eventpassquest"
        ordering = ("event_pass__position", "tier__position", "position", "pk")
        unique_together = (("event_pass", "name"),)
        indexes = [models.Index(fields=("event_pass", "enabled"), name="eventpass_quest_pass_idx")]


class PlayerPass(models.Model):
    """
    A player taking part in a pass: when they were first seen, and what they got at the end.
    """

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="event_passes")
    player_id: int
    event_pass = models.ForeignKey(EventPass, on_delete=models.CASCADE, related_name="players")
    event_pass_id: int
    joined_at = models.DateTimeField(auto_now_add=True)
    final_claimed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = "eventpassplayer"
        unique_together = (("player", "event_pass"),)
        indexes = [models.Index(fields=("event_pass",), name="eventpass_player_pass_idx")]


class PlayerQuest(models.Model):
    """
    The progress of one player on one quest. Quests that come back have one row per period.
    """

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="event_pass_quests")
    player_id: int
    quest = models.ForeignKey(Quest, on_delete=models.CASCADE, related_name="progress")
    quest_id: int
    period = models.CharField(
        max_length=16, blank=True, default="", help_text='Empty for a one-off quest, "2026-09-20" for a daily one.'
    )
    progress = models.PositiveBigIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)

    @property
    def completed(self) -> bool:
        return self.completed_at is not None

    @property
    def claimed(self) -> bool:
        return self.claimed_at is not None

    def __str__(self) -> str:
        return f"{self.quest_id} for {self.player_id}"

    class Meta:
        managed = True
        db_table = "eventpassplayerquest"
        unique_together = (("player", "quest", "period"),)
        indexes = [
            models.Index(fields=("player", "quest"), name="eventpass_pq_player_idx"),
            models.Index(fields=("quest", "completed_at"), name="eventpass_pq_done_idx"),
        ]


class RewardGrant(models.Model):
    """
    One row per reward actually given, which is what makes claiming safe: the unique constraint below is what stops
    a double click from giving the same reward twice.
    """

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="+")
    player_id: int
    event_pass = models.ForeignKey(EventPass, on_delete=models.CASCADE, related_name="grants")
    event_pass_id: int
    reward = models.ForeignKey(Reward, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reward_id: int | None
    source = models.CharField(max_length=8, choices=Source.choices)
    source_id = models.PositiveBigIntegerField(help_text="The quest or tier the reward came from.")
    period = models.CharField(max_length=16, blank=True, default="")
    summary = models.TextField(blank=True, default="", help_text="What was given, as it was shown to the player.")
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "eventpassrewardgrant"
        unique_together = (("player", "source", "source_id", "period"),)
        indexes = [models.Index(fields=("event_pass", "granted_at"), name="eventpass_grant_idx")]
