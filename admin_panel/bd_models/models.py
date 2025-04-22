# pyright: reportIncompatibleVariableOverride=false

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from typing import TYPE_CHECKING, Any, Iterable, Self, cast

import discord
from discord.utils import format_dt
from django.contrib import admin
from django.core.cache import cache
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.safestring import SafeText, mark_safe
from django.utils.timezone import now

from ballsdex.core.image_generator.image_gen import draw_card
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


def transform_media(path: str) -> str:
    return path.replace("/static/uploads/", "").replace(
        "/ballsdex/core/image_generator/src/", "default/"
    )


def image_display(image_link: str) -> SafeText:
    return mark_safe(f'<img src="/media/{transform_media(image_link)}" width="80%" />')


balls: dict[int, Ball] = {}
regimes: dict[int, Regime] = {}
economies: dict[int, Economy] = {}
specials: dict[int, Special] = {}


class Manager[T: models.Model](models.Manager[T]):
    def get_or_none(self, *args: Any, **kwargs: Any) -> T | None:
        try:
            return super().get(*args, **kwargs)
        except self.model.DoesNotExist:
            return None

    async def aget_or_none(self, *args: Any, **kwargs: Any) -> T | None:
        try:
            return await super().aget(*args, **kwargs)
        except self.model.DoesNotExist:
            return None

    async def aall(self) -> list[T]:
        return [x async for x in super().all()]


class GuildConfig(models.Model):
    guild_id = models.BigIntegerField(unique=True, help_text="Discord guild ID")
    spawn_channel = models.BigIntegerField(
        blank=True, null=True, help_text="Discord channel ID where balls will spawn"
    )
    enabled = models.BooleanField(
        help_text="Whether the bot will spawn countryballs in this guild"
    )
    silent = models.BooleanField()

    objects: Manager[Self] = Manager()

    def __str__(self) -> str:
        return str(self.guild_id)

    class Meta:
        managed = True
        db_table = "guildconfig"


class DonationPolicy(models.IntegerChoices):
    ALWAYS_ACCEPT = 1
    REQUEST_APPROVAL = 2
    ALWAYS_DENY = 3
    FRIENDS_ONLY = 4


class PrivacyPolicy(models.IntegerChoices):
    ALLOW = 1
    DENY = 2
    SAME_SERVER = 3
    FRIENDS = 4


class MentionPolicy(models.IntegerChoices):
    ALLOW = 1
    DENY = 2


class FriendPolicy(models.IntegerChoices):
    ALLOW = 1
    DENY = 2


class Player(models.Model):
    discord_id = models.BigIntegerField(unique=True, help_text="Discord user ID")
    money = models.PositiveBigIntegerField(help_text="Money posessed by the player", default=0)
    donation_policy = models.SmallIntegerField(
        choices=DonationPolicy.choices, help_text="How you want to handle donations"
    )
    privacy_policy = models.SmallIntegerField(
        choices=PrivacyPolicy.choices, help_text="How you want to handle inventory privacy"
    )
    mention_policy = models.SmallIntegerField(
        choices=MentionPolicy.choices, help_text="Control the bot's mentions"
    )
    friend_policy = models.SmallIntegerField(
        choices=FriendPolicy.choices, help_text="Open or close your friend requests"
    )
    extra_data = models.JSONField(blank=True, default=dict)

    objects: Manager[Self] = Manager()

    balls: models.QuerySet[BallInstance]

    class Meta:
        managed = True
        db_table = "player"

    def __str__(self) -> str:
        return (
            f"{'\N{NO MOBILE PHONES} ' if self.is_blacklisted() else ''}#"
            f"{self.pk} ({self.discord_id})"
        )

    def is_blacklisted(self) -> bool:
        blacklist = cast(
            list[int],
            cache.get_or_set(
                "blacklist",
                BlacklistedID.objects.all().values_list("discord_id", flat=True),
                timeout=300,
            ),
        )
        return self.discord_id in blacklist

    async def is_friend(self, other_player: "Player") -> bool:
        return await Friendship.objects.filter(
            (Q(player1=self) & Q(player2=other_player))
            | (Q(player1=other_player) & Q(player2=self))
        ).aexists()

    async def is_blocked(self, other_player: "Player") -> bool:
        return await Block.objects.filter((Q(player1=self) & Q(player2=other_player))).aexists()

    @property
    def can_be_mentioned(self) -> bool:
        return self.mention_policy == MentionPolicy.ALLOW

    async def add_money(self, amount: int) -> int:
        if amount <= 0:
            raise ValueError("Amount to add must be positive")
        self.money += amount
        await self.asave(update_fields=("money",))
        return self.money

    async def remove_money(self, amount: int) -> None:
        if self.money < amount:
            raise ValueError("Not enough money")
        self.money -= amount
        await self.asave(update_fields=("money",))

    def can_afford(self, amount: int) -> bool:
        return self.money >= amount


class Economy(models.Model):
    name = models.CharField(max_length=64)
    icon = models.ImageField(max_length=200, help_text="512x512 PNG image")

    objects: Manager[Self] = Manager()

    class Meta:
        managed = True
        db_table = "economy"
        verbose_name_plural = "economies"

    def __str__(self) -> str:
        return self.name


class Regime(models.Model):
    name = models.CharField(max_length=64)
    background = models.ImageField(max_length=200, help_text="1428x2000 PNG image")

    objects: Manager[Self] = Manager()

    class Meta:
        managed = True
        db_table = "regime"

    def __str__(self) -> str:
        return self.name


class EnabledManager[T: models.Model](Manager[T]):
    def get_queryset(self) -> models.QuerySet[T]:
        return super().get_queryset().filter(enabled=True)


class TradeableManager[T: models.Model](Manager[T]):
    def get_queryset(self) -> models.QuerySet[T]:
        return super().get_queryset().filter(tradeable=True)


class SpecialEnabledManager(Manager["Special"]):
    def get_queryset(self) -> models.QuerySet[Special]:
        return super().get_queryset().filter(hidden=False)


class Special(models.Model):
    name = models.CharField(max_length=64)
    catch_phrase = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Sentence sent in bonus when someone catches a special card",
    )
    start_date = models.DateTimeField(
        blank=True, null=True, help_text="Start time of the event. If blank, starts immediately"
    )
    end_date = models.DateTimeField(
        blank=True, null=True, help_text="End time of the event. If blank, the event is permanent"
    )
    rarity = models.FloatField(
        help_text="Value between 0 and 1, chances of using this special background."
    )
    emoji = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Either a unicode character or a discord emoji ID",
    )
    background = models.ImageField(
        max_length=200, blank=True, null=True, help_text="1428x2000 PNG image"
    )
    tradeable = models.BooleanField(
        help_text="Whether balls of this event can be traded", default=True
    )
    hidden = models.BooleanField(help_text="Hides the event from user commands", default=False)
    credits = models.CharField(
        max_length=64, help_text="Author of the special event artwork", null=True
    )

    objects: Manager[Self] = Manager()
    enabled_objects = SpecialEnabledManager()

    class Meta:
        managed = True
        db_table = "special"

    def __str__(self) -> str:
        return self.name


class Ball(models.Model):
    country = models.CharField(unique=True, max_length=48)
    health = models.IntegerField(help_text="Ball health stat")
    attack = models.IntegerField(help_text="Ball attack stat")
    rarity = models.FloatField(help_text="Rarity of this ball")
    emoji_id = models.BigIntegerField(help_text="Emoji ID for this ball")
    wild_card = models.ImageField(
        max_length=200,
        help_text="Image used when a new ball spawns in the wild",
    )
    collection_card = models.ImageField(
        max_length=200, help_text="Image used when displaying balls"
    )
    credits = models.CharField(max_length=64, help_text="Author of the collection artwork")
    capacity_name = models.CharField(max_length=64, help_text="Name of the countryball's capacity")
    capacity_description = models.CharField(
        max_length=256, help_text="Description of the countryball's capacity"
    )
    capacity_logic = models.JSONField(
        help_text="Effect of this capacity", blank=True, default=dict
    )
    enabled = models.BooleanField(
        help_text="Enables spawning and show in completion", default=True
    )
    short_name = models.CharField(
        max_length=24,
        blank=True,
        null=True,
        help_text="An alternative shorter name used only when generating the card, "
        "if the base name is too long.",
    )
    catch_names = models.TextField(
        blank=True,
        null=True,
        help_text="Additional possible names for catching this ball, separated by semicolons",
    )
    tradeable = models.BooleanField(
        help_text="Whether this ball can be traded with others", default=True
    )
    economy = models.ForeignKey(
        Economy,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Economical regime of this country",
    )
    economy_id: int | None
    regime = models.ForeignKey(
        Regime, on_delete=models.CASCADE, help_text="Political regime of this country"
    )
    regime_id: int
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True, editable=False)
    translations = models.TextField(blank=True, null=True)

    objects: Manager[Self] = Manager()
    enabled_objects: EnabledManager[Self] = EnabledManager()
    tradeable_objects: TradeableManager[Self] = TradeableManager()

    class Meta:
        managed = True
        db_table = "ball"

    @property
    def cached_regime(self) -> Regime:
        return regimes.get(self.regime_id, self.regime)

    @property
    def cached_economy(self) -> Economy | None:
        return economies.get(self.economy_id, self.economy) if self.economy_id else None

    def __str__(self) -> str:
        return self.country

    @admin.display(description="Current collection card")
    def collection_image(self) -> SafeText:
        return image_display(str(self.collection_card))

    @admin.display(description="Current spawn asset")
    def spawn_image(self) -> SafeText:
        return image_display(str(self.wild_card))

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:

        def lower_catch_names(names: str | None) -> str | None:
            if names:
                return ";".join([x.strip() for x in names.split(";")]).lower()

        self.catch_names = lower_catch_names(self.catch_names)
        self.translations = lower_catch_names(self.translations)

        return super().save(force_insert, force_update, using, update_fields)


class BallInstance(models.Model):
    catch_date = models.DateTimeField()
    health_bonus = models.IntegerField()
    attack_bonus = models.IntegerField()
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE)
    ball_id: int
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="balls")
    player_id: int
    trade_player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        related_name="ballinstance_trade_player_set",
        blank=True,
        null=True,
    )
    trade_player_id: int | None
    favorite = models.BooleanField()
    special = models.ForeignKey(Special, on_delete=models.SET_NULL, blank=True, null=True)
    special_id: int | None
    server_id = models.BigIntegerField(
        blank=True, null=True, help_text="Discord server ID where this ball was caught"
    )
    tradeable = models.BooleanField()
    extra_data = models.JSONField(blank=True, default=dict)
    locked = models.DateTimeField(
        blank=True, null=True, help_text="If the instance was locked for a trade and when"
    )
    spawned_time = models.DateTimeField(blank=True, null=True)

    objects: Manager[Self] = Manager()
    tradeable_objects: TradeableManager[Self] = TradeableManager()

    class Meta:
        managed = True
        db_table = "ballinstance"
        unique_together = (("player", "id"),)
        indexes = (
            models.Index(fields=("ball_id",)),
            models.Index(fields=("player_id",)),
            models.Index(fields=("special_id",)),
        )

    def __getattribute__(self, name: str) -> Any:
        if name == "ball":
            balls = cast(list[Ball], cache.get_or_set("balls", Ball.objects.all(), timeout=30))
            for ball in balls:
                if ball.pk == self.ball_id:
                    return ball
        return super().__getattribute__(name)

    def __str__(self) -> str:
        text = ""
        if self.locked and self.locked > now() - timedelta(minutes=30):
            text += "🔒"
        if self.favorite:
            text += settings.favorited_collectible_emoji
        if text:
            text += " "
        if self.special:
            text += self.special.emoji or ""
        return f"{text}#{self.pk:0X} {self.ball.country}"

    @property
    def is_tradeable(self) -> bool:
        return (
            self.tradeable
            and self.countryball.tradeable
            and getattr(self.specialcard, "tradeable", True)
        )

    @property
    def attack(self) -> int:
        bonus = int(self.countryball.attack * self.attack_bonus * 0.01)
        return self.countryball.attack + bonus

    @property
    def health(self) -> int:
        bonus = int(self.countryball.health * self.health_bonus * 0.01)
        return self.countryball.health + bonus

    @property
    def special_card(self) -> str | None:
        if self.specialcard:
            return self.specialcard.background.name or self.countryball.collection_card.name

    @property
    def countryball(self) -> Ball:
        return balls.get(self.ball_id, None) or self.ball

    @property
    def specialcard(self) -> Special | None:
        return specials.get(self.special_id, None) if self.special_id else None

    @admin.display(description="Countryball")
    def admin_description(self) -> SafeText:
        text = str(self)
        emoji = f'<img src="https://cdn.discordapp.com/emojis/{self.ball.emoji_id}.png?size=20" />'
        return mark_safe(f"{emoji} {text} ATK:{self.attack_bonus:+d}% HP:{self.health_bonus:+d}%")

    @admin.display(description="Time to catch")
    def catch_time(self):
        if self.spawned_time:
            return str(self.catch_date - self.spawned_time)
        return "-"

    def description(
        self,
        *,
        short: bool = False,
        include_emoji: bool = False,
        bot: "BallsDexBot | None" = None,
        is_trade: bool = False,
    ) -> str:
        text = self.to_string(bot, is_trade=is_trade)
        if not short:
            text += f" ATK:{self.attack_bonus:+d}% HP:{self.health_bonus:+d}%"
        if include_emoji:
            if not bot:
                raise TypeError(
                    "You need to provide the bot argument when using with include_emoji=True"
                )
            if isinstance(self.countryball, Ball):
                emoji = bot.get_emoji(self.countryball.emoji_id)
                if emoji:
                    text = f"{emoji} {text}"
        return text

    def draw_card(self) -> BytesIO:
        image, kwargs = draw_card(self)
        buffer = BytesIO()
        image.save(buffer, **kwargs)
        buffer.seek(0)
        image.close()
        return buffer

    async def prepare_for_message(
        self, interaction: discord.Interaction["BallsDexBot"]
    ) -> tuple[str, discord.File, discord.ui.View]:
        # message content
        trade_content = ""
        if self.trade_player:
            original_player = None
            # we want to avoid calling fetch_user if possible (heavily rate-limited call)
            if interaction.guild:
                try:
                    original_player = await interaction.guild.fetch_member(
                        int(self.trade_player.discord_id)
                    )
                except discord.NotFound:
                    pass
            elif original_player is None:  # try again if not found in guild
                try:
                    original_player = await interaction.client.fetch_user(
                        int(self.trade_player.discord_id)
                    )
                except discord.NotFound:
                    pass

            original_player_name = (
                original_player.name
                if original_player
                else f"user with ID {self.trade_player.discord_id}"
            )
            trade_content = f"Obtained by trade with {original_player_name}.\n"
        content = (
            f"ID: `#{self.pk:0X}`\n"
            f"Caught on {format_dt(self.catch_date)} ({format_dt(self.catch_date, style='R')}).\n"
            f"{trade_content}\n"
            f"ATK: {self.attack} ({self.attack_bonus:+d}%)\n"
            f"HP: {self.health} ({self.health_bonus:+d}%)"
        )

        # draw image
        with ThreadPoolExecutor() as pool:
            buffer = await interaction.client.loop.run_in_executor(pool, self.draw_card)

        view = discord.ui.View()
        return content, discord.File(buffer, "card.webp"), view

    async def lock_for_trade(self):
        self.locked = timezone.now()
        await self.asave(update_fields=("locked",))

    async def unlock(self):
        self.locked = None  # type: ignore
        await self.asave(update_fields=("locked",))

    async def is_locked(self):
        await self.arefresh_from_db(fields=["locked"])
        self.locked
        return self.locked is not None and (self.locked + timedelta(minutes=30)) > timezone.now()


class BlacklistedID(models.Model):
    discord_id = models.BigIntegerField(unique=True, help_text="Discord user ID")
    reason = models.TextField(blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    moderator_id = models.BigIntegerField(blank=True, null=True)

    objects: Manager[Self] = Manager()

    class Meta:
        managed = True
        db_table = "blacklistedid"


class BlacklistedGuild(models.Model):
    discord_id = models.BigIntegerField(unique=True, help_text="Discord Guild ID")
    reason = models.TextField(blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    moderator_id = models.BigIntegerField(blank=True, null=True)

    objects: Manager[Self] = Manager()

    class Meta:
        managed = True
        db_table = "blacklistedguild"


class BlacklistHistory(models.Model):
    discord_id = models.BigIntegerField(help_text="Discord ID")
    moderator_id = models.BigIntegerField(help_text="Discord Moderator ID")
    reason = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True, editable=False)
    id_type = models.CharField(max_length=64, default="user")
    action_type = models.CharField(max_length=64, default="blacklist")

    objects: Manager[Self] = Manager()

    class Meta:
        managed = True
        db_table = "blacklisthistory"
        verbose_name_plural = "blacklisthistories"


class Trade(models.Model):
    date = models.DateTimeField(auto_now_add=True, editable=False)
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE)
    player1_id: int
    player1_money = models.PositiveBigIntegerField(default=0)
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="trade_player2_set")
    player2_id: int
    player2_money = models.PositiveBigIntegerField(default=0)
    tradeobject_set: models.QuerySet[TradeObject]

    objects: Manager[Self] = Manager()

    def __str__(self) -> str:
        return f"Trade #{self.pk:0X}"

    class Meta:
        managed = True
        db_table = "trade"
        indexes = (
            models.Index(fields=("player1_id",)),
            models.Index(fields=("player2_id",)),
        )


class TradeObject(models.Model):
    ballinstance = models.ForeignKey(BallInstance, on_delete=models.CASCADE)
    ballinstance_id: int
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    player_id: int
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE)
    trade_id: int

    objects: Manager[Self] = Manager()

    class Meta:
        managed = True
        db_table = "tradeobject"
        indexes = (
            models.Index(fields=("ballinstance_id",)),
            models.Index(fields=("player_id",)),
            models.Index(fields=("trade_id",)),
        )


class Friendship(models.Model):
    since = models.DateTimeField(auto_now_add=True, editable=False)
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE)
    player1_id: int
    player2 = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="friendship_player2_set"
    )
    player2_id: int

    objects: Manager[Self] = Manager()

    class Meta:
        managed = True
        db_table = "friendship"


class Block(models.Model):
    date = models.DateTimeField(auto_now_add=True, editable=False)
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE)
    player1_id: int
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="block_player2_set")
    player2_id: int

    objects: Manager[Self] = Manager()

    class Meta:
        managed = True
        db_table = "block"
