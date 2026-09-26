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
from bd_models.models import Ball, BallGroup, Economy, Player, Regime, Special, balls, groups, specials
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
    GIVE_TREASURES = "give_treasures", "Give treasures to players"
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


class RewardMode(models.TextChoices):
    ALL = "all", "Give everything below"
    CHOICE = "choice", "The player picks from the lines below"
    RANDOM = "random", "Draw at random from the lines below"


class AccessKind(models.TextChoices):
    """
    One condition a player must meet to take part in a pass.
    """

    ROLE = "role", "Have a Discord role"
    MAX_TREASURES = "max_treasures", "Own at most this many treasures"
    MIN_TREASURES = "min_treasures", "Own at least this many treasures"
    MAX_CURRENCY = "max_currency", "Have at most this many berries"
    MIN_CURRENCY = "min_currency", "Have at least this many berries"


class BonusMode(models.TextChoices):
    RANDOM = "random", "Random, like a catch"
    FIXED = "fixed", "The values set below"
    ZERO = "zero", "No bonus (+0%)"


class RequirementKind(models.TextChoices):
    FINISH_PREVIOUS = "finish_previous", "Finish the previous tier (its mandatory quests)"
    QUESTS_ALL = "quests_all", "Complete these quests"
    QUESTS_COUNT = "quests_count", "Complete a number of quests of the pass"
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
    emoji = models.CharField(
        max_length=64, blank=True, default="", help_text="Only used to recognise the bundle in the admin lists."
    )
    mode = models.CharField(
        max_length=8,
        choices=RewardMode.choices,
        default=RewardMode.ALL,
        help_text="Whether every line is given, the player picks among them, or they are drawn at random.",
    )
    pick = models.PositiveSmallIntegerField(
        default=1, help_text="How many are picked or drawn, for the two modes above. Ignored when everything is given."
    )
    offer = models.PositiveSmallIntegerField(
        default=0,
        help_text="How many options a choice shows when the lines resolve to more than that (a group, a rarity "
        "range...). 0 offers them all, up to the 25 Discord allows.",
    )
    lines: models.QuerySet[RewardLine]

    def clean(self):
        super().clean()
        if self.pick < 1:
            raise ValidationError({"pick": "At least one line must be picked."})
        if self.offer and self.offer < self.pick:
            raise ValidationError({"offer": "A choice must offer at least as many options as it picks."})

    def __str__(self) -> str:
        return f"{self.emoji} {self.name}".strip()

    class Meta:
        managed = True
        db_table = "eventpassreward"
        ordering = ("name",)


class RewardLine(models.Model):
    reward = models.ForeignKey(Reward, on_delete=models.CASCADE, related_name="lines")
    reward_id: int
    kind = models.CharField(
        max_length=16,
        choices=RewardKind.choices,
        default=RewardKind.TREASURE,
        help_text="Berries are always given whatever the bundle's mode; only treasures are picked or drawn.",
    )
    position = models.PositiveSmallIntegerField(
        default=0, help_text="Lines are given, offered and listed from the lowest position."
    )

    # berries
    amount = models.PositiveBigIntegerField(default=0, help_text="Berries given, for a berry line.")

    # treasures: either one named treasure, or a pool the treasure is taken from
    ball = models.ForeignKey(
        Ball,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text="The treasure given. Leave empty to draw one from the pool below instead.",
    )
    ball_id: int | None
    quantity = models.PositiveSmallIntegerField(default=1, help_text="How many copies of the treasure are given.")

    # -- pool, used when no treasure is named: every enabled treasure matching all of these
    group = models.ForeignKey(
        BallGroup, null=True, blank=True, on_delete=models.CASCADE, related_name="+", help_text="Pool: this group."
    )
    group_id: int | None
    regime = models.ForeignKey(
        Regime, null=True, blank=True, on_delete=models.CASCADE, related_name="+", help_text="Pool: this regime."
    )
    regime_id: int | None
    economy = models.ForeignKey(
        Economy, null=True, blank=True, on_delete=models.CASCADE, related_name="+", help_text="Pool: this economy."
    )
    economy_id: int | None
    min_rarity = models.FloatField(
        null=True,
        blank=True,
        help_text="Pool: lowest rarity value kept. A lower value is rarer, so this drops the "
        "rarest treasures — 10 leaves out everything rarer than T10.",
    )
    max_rarity = models.FloatField(
        null=True, blank=True, help_text="Pool: highest rarity value kept, which drops the most common treasures."
    )
    exclude_balls: models.ManyToManyField[Ball, models.Model] = models.ManyToManyField(
        Ball, blank=True, related_name="+", help_text="Pool: treasures never drawn, whatever the filters above say."
    )
    special = models.ForeignKey(
        Special,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Special put on the treasure given. Leave empty for a regular one.",
    )
    special_id: int | None
    frame_key = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text='Frame given to the treasure: its name ("Haki Aura") or the key it is stored under '
        '("09-20-2026", or "09-20-2026:3" for a frame of one special). A name is easier to read and does not '
        "change when the event moves. Leave empty for a normal card.",
    )
    bonus_mode = models.CharField(
        max_length=8,
        choices=BonusMode.choices,
        default=BonusMode.RANDOM,
        help_text="How the attack and health bonuses of the treasure are rolled.",
    )
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

    POOL_FIELDS = ("group_id", "regime_id", "economy_id", "min_rarity", "max_rarity")

    @property
    def is_pool(self) -> bool:
        """
        Whether this line draws from a pool instead of naming one treasure.
        """
        return self.kind == RewardKind.TREASURE and not self.ball_id

    def clean(self):
        super().clean()
        if self.kind == RewardKind.BERRIES and not self.amount:
            raise ValidationError({"amount": "A berry reward needs an amount."})
        if self.kind == RewardKind.TREASURE and not self.ball_id:
            if not any(getattr(self, name) is not None for name in self.POOL_FIELDS):
                raise ValidationError(
                    {
                        "ball": "A treasure reward needs a treasure, or a pool to draw one from (a group, a regime, "
                        "an economy or a rarity range)."
                    }
                )
        if self.min_rarity is not None and self.max_rarity is not None and self.min_rarity > self.max_rarity:
            raise ValidationError({"max_rarity": "The maximum rarity must be above the minimum."})

    def pool_description(self) -> str:
        """
        The pool as players read it: "a Straw Hats treasure", "a treasure between T18 and T33".
        """
        parts = []
        if self.group_id:
            group = groups.get(self.group_id) or self.group
            parts.append(group.name if group else "a group")
        if self.regime_id and self.regime:
            parts.append(self.regime.name)
        if self.economy_id and self.economy:
            parts.append(self.economy.name)
        if self.min_rarity is not None and self.max_rarity is not None:
            parts.append(f"T{self.min_rarity:g}-T{self.max_rarity:g}")
        elif self.min_rarity is not None:
            parts.append(f"T{self.min_rarity:g} or more common")
        elif self.max_rarity is not None:
            parts.append(f"T{self.max_rarity:g} or rarer")
        return " ".join(parts) or "any treasure"

    def __str__(self) -> str:
        if self.kind == RewardKind.BERRIES:
            return f"{self.amount:,} {settings.currency_plural}"
        special = self.cached_special
        prefix = f"{self.quantity}x {special.name + ' ' if special else ''}"
        if self.is_pool:
            return f"{prefix}{self.pool_description()}"
        ball = self.cached_ball
        text = f"{prefix}{ball.country if ball else '?'}"
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

    name = models.CharField(
        max_length=64, unique=True, help_text="Shown as the title of the pass, and how it is named in /pass view."
    )
    emoji = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Shown before the name. A server emoji is written in full, like <:StrawHat:1477078273078067252>.",
    )
    description = models.TextField(blank=True, default="", help_text="Shown at the top of the pass.")
    banner = models.ImageField(max_length=200, null=True, blank=True, help_text="Optional banner image.")
    colour = models.CharField(
        max_length=7, blank=True, default="", help_text="Accent colour of the pass, like #E63946. Optional."
    )
    status = models.CharField(
        max_length=8,
        choices=Status.choices,
        default=Status.DRAFT,
        help_text="A draft is only visible to staff and nothing progresses in it. Publish it to let players "
        "play, and archive it to close it for good.",
    )

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
        help_text="Given when every tier is finished. Leave empty if the pass has no final reward.",
    )
    final_reward_id: int | None
    final_message = models.TextField(blank=True, default="", help_text="Shown when the pass is completed.")
    position = models.PositiveSmallIntegerField(default=0, help_text="Passes are listed from the lowest position.")

    access_logic = models.CharField(
        max_length=3,
        choices=Logic.choices,
        default=Logic.ALL,
        help_text="Whether a player must meet every condition below, or only one of them.",
    )
    access_message = models.TextField(
        blank=True, default="", help_text="Shown to a player who can't take part. Leave empty for the generated text."
    )

    notes = models.TextField(blank=True, default="", help_text="Internal notes, never shown to players.")
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    tiers: models.QuerySet[PassTier]
    quests: models.QuerySet[Quest]
    access: models.QuerySet[PassRequirement]

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


class PassRequirement(models.Model):
    """
    One condition a player must meet to take part in a pass, so an event can be reserved to a role or to newcomers.

    A pass with no requirement is open to everyone, which is what every pass written before this was.
    """

    event_pass = models.ForeignKey(EventPass, on_delete=models.CASCADE, related_name="access")
    event_pass_id: int
    kind = models.CharField(
        max_length=16, choices=AccessKind.choices, help_text="What the player must have to take part."
    )
    role_id = models.BigIntegerField(null=True, blank=True, help_text="Discord ID of the role, for a role condition.")
    role_name = models.CharField(
        max_length=64, blank=True, default="", help_text="Only used to name the role in the message players read."
    )
    count = models.PositiveBigIntegerField(default=0, help_text="The number of treasures or berries, for the others.")

    @property
    def counts_live(self) -> bool:
        """
        Whether this condition can be rechecked without a Discord member, which is what repeating quests need.
        """
        return self.kind != AccessKind.ROLE

    def describe(self) -> str:
        """
        The condition as players read it.
        """
        match self.kind:
            case AccessKind.ROLE:
                return f"Have the {self.role_name or 'required'} role"
            case AccessKind.MAX_TREASURES:
                return f"Own {self.count:,} {settings.plural_collectible_name} or fewer"
            case AccessKind.MIN_TREASURES:
                return f"Own at least {self.count:,} {settings.plural_collectible_name}"
            case AccessKind.MAX_CURRENCY:
                return f"Have {self.count:,} {settings.currency_plural} or fewer"
            case AccessKind.MIN_CURRENCY:
                return f"Have at least {self.count:,} {settings.currency_plural}"
        return ""

    def clean(self):
        super().clean()
        if self.kind == AccessKind.ROLE and not self.role_id:
            raise ValidationError({"role_id": "Give the Discord ID of the role."})
        if self.kind != AccessKind.ROLE and not self.count:
            raise ValidationError({"count": "This condition needs a number."})

    def __str__(self) -> str:
        return self.describe()

    class Meta:
        managed = True
        db_table = "eventpassaccess"
        ordering = ("pk",)
        verbose_name = "access condition"
        verbose_name_plural = "access conditions"


class PassTier(models.Model):
    event_pass = models.ForeignKey(EventPass, on_delete=models.CASCADE, related_name="tiers")
    event_pass_id: int
    name = models.CharField(max_length=64, help_text="Shown as the title of the tier's page, and in its unlock text.")
    emoji = models.CharField(
        max_length=64, blank=True, default="", help_text="Shown before the name, written in full for a server emoji."
    )
    description = models.TextField(
        blank=True, default="", help_text="Shown under the title, on the first page of the tier."
    )
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
        help_text="Optional reward for finishing the tier: every mandatory quest completed, or every visible quest "
        "when none is mandatory.",
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
    kind = models.CharField(
        max_length=16,
        choices=RequirementKind.choices,
        help_text="What opens the tier. Only the fields that kind uses are read.",
    )

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
    special = models.ForeignKey(
        Special,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="The special the owned treasures must have, for that kind of requirement.",
    )
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

    name = models.CharField(max_length=64, help_text="Shown to players, and used to point at the quest in a file.")
    description = models.TextField(
        blank=True, default="", help_text="Shown to players. Leave empty to use the goal generated from the settings."
    )
    emoji = models.CharField(
        max_length=64, blank=True, default="", help_text="Shown before the name, written in full for a server emoji."
    )
    thumbnail = models.ImageField(max_length=200, null=True, blank=True, help_text="128x128 PNG image")
    position = models.PositiveSmallIntegerField(default=0, help_text="Quests are listed from the lowest position.")
    enabled = models.BooleanField(default=True, help_text="Uncheck to hide the quest without deleting it.")
    hidden = models.BooleanField(default=False, help_text="Secret quest: players only see it once they completed it.")
    mandatory = models.BooleanField(
        default=False,
        help_text="Needed to finish the tier: its reward, and the tiers asking to finish it, wait for every mandatory "
        "quest. A tier with no mandatory quest needs all its visible quests instead.",
    )

    type = models.CharField(
        max_length=24,
        choices=QuestType.choices,
        help_text="What the player has to do. It decides which of the filters below are used.",
    )
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

    reward = models.ForeignKey(
        Reward,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quests",
        help_text="Given when the quest is completed. A quest with no reward just counts towards the tier.",
    )
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
    ball = models.ForeignKey(
        Ball,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Only count this treasure. Leave empty for any.",
    )
    ball_id: int | None
    special = models.ForeignKey(
        Special,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Only count treasures of this special. Leave empty for any.",
    )
    special_id: int | None
    any_special = models.BooleanField(
        default=False, help_text="Only count treasures with a special, whichever it is. Ignored if a special is set."
    )
    group = models.ForeignKey(
        BallGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Only count treasures of this group. Leave empty for any.",
    )
    group_id: int | None
    min_rarity = models.FloatField(
        null=True,
        blank=True,
        help_text="Lowest rarity value counted. A lower value is rarer: 50 leaves out everything rarer than T50.",
    )
    max_rarity = models.FloatField(
        null=True, blank=True, help_text="Highest rarity value counted: 60 keeps T60 and everything rarer."
    )
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
    require_command_effect = models.BooleanField(
        verbose_name="only count when it worked",
        help_text="Only count the command when it actually did something. A /daily run while it is still on "
        "cooldown, a shop with nothing left or a purchase the player could not afford then do not count. "
        "Commands that never report an outcome are always counted.",
        default=False,
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
    eligible = models.BooleanField(
        default=True,
        help_text="Whether the player still meets the conditions of the pass. Rechecked every time they open it; "
        "when it goes false, the quests that come back stop progressing, but what they already finished is theirs.",
    )
    eligible_checked_at = models.DateTimeField(null=True, blank=True)
    passed = models.JSONField(
        default=list,
        blank=True,
        help_text="The access conditions the player met at that check, as their ids. The ones that need Discord (a "
        "role) can only be read there, so the engine reuses this answer for them and counts the rest itself.",
    )

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
    progress = models.PositiveBigIntegerField(default=0, help_text="How far the player is, against the goal.")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="When the goal was reached.")
    claimed_at = models.DateTimeField(null=True, blank=True, help_text="When the reward was handed over.")

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
    source = models.CharField(max_length=8, choices=Source.choices, help_text="What the reward was given for.")
    source_id = models.PositiveBigIntegerField(help_text="The quest or tier the reward came from.")
    period = models.CharField(max_length=16, blank=True, default="")
    summary = models.TextField(blank=True, default="", help_text="What was given, as it was shown to the player.")
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "eventpassrewardgrant"
        unique_together = (("player", "source", "source_id", "period"),)
        indexes = [models.Index(fields=("event_pass", "granted_at"), name="eventpass_grant_idx")]


class RewardChoice(models.Model):
    """
    A reward the player still has to pick, kept between two uses of the pass.

    A choice is written at the same moment as its `RewardGrant`, inside the same transaction, so a reward is reserved
    exactly once even if the player never comes back to pick it. Nothing is handed out until `resolved_at` is set.
    """

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="+")
    player_id: int
    event_pass = models.ForeignKey(EventPass, on_delete=models.CASCADE, related_name="choices")
    event_pass_id: int
    grant = models.OneToOneField("RewardGrant", on_delete=models.CASCADE, related_name="choice")
    grant_id: int
    reward = models.ForeignKey(Reward, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reward_id: int | None
    label = models.CharField(max_length=128, blank=True, default="", help_text="The quest or tier it came from.")
    options = models.JSONField(default=list, help_text="The treasures offered, as their ids.")
    picks = models.PositiveSmallIntegerField(default=1, help_text="How many of them the player takes.")
    chosen = models.JSONField(default=list, blank=True, help_text="What they took, as treasure ids.")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    @property
    def pending(self) -> bool:
        return self.resolved_at is None

    def option_balls(self) -> list[Ball]:
        """
        The offered treasures, in the order they were offered. The caches must be loaded.
        """
        found = []
        for ball_id in self.options:
            ball = balls.get(ball_id)
            if ball is not None:
                found.append(ball)
        return found

    def __str__(self) -> str:
        return f"{self.label or self.event_pass_id} for {self.player_id}"

    class Meta:
        managed = True
        db_table = "eventpassrewardchoice"
        ordering = ("pk",)
        indexes = [models.Index(fields=("player", "resolved_at"), name="eventpass_choice_pending_idx")]
