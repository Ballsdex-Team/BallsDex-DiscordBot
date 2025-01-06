from django.db import models
from django.template.loader import render_to_string
from django.utils.safestring import SafeText, mark_safe


def image_display(image_link: str) -> SafeText:
    return mark_safe(f'<img src="{image_link}" width="80%" />')


class Guildconfig(models.Model):
    guild_id = models.BigIntegerField(unique=True, help_text="Discord guild ID")
    spawn_channel = models.BigIntegerField(
        blank=True, null=True, help_text="Discord channel ID where balls will spawn"
    )
    enabled = models.BooleanField(
        help_text="Whether the bot will spawn countryballs in this guild"
    )
    silent = models.BooleanField()

    def __str__(self) -> str:
        return str(self.guild_id)

    class Meta:
        managed = False
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

    def __str__(self) -> str:
        return str(self.discord_id)

    class Meta:
        managed = False
        db_table = "player"


class Economy(models.Model):
    name = models.CharField(max_length=64)
    icon = models.ImageField(max_length=200, help_text="512x512 PNG image")

    def __str__(self) -> str:
        return self.name

    class Meta:
        managed = False
        db_table = "economy"
        verbose_name_plural = "economies"


class Regime(models.Model):
    name = models.CharField(max_length=64)
    background = models.ImageField(max_length=200, help_text="1428x2000 PNG image")

    def __str__(self) -> str:
        return self.name

    class Meta:
        managed = False
        db_table = "regime"


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
    tradeable = models.BooleanField(help_text="Whether balls of this event can be traded")
    hidden = models.BooleanField(help_text="Hides the event from user commands")

    def __str__(self) -> str:
        return self.name

    class Meta:
        managed = False
        db_table = "special"


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
    capacity_logic = models.JSONField(help_text="Effect of this capacity", editable=False)
    enabled = models.BooleanField(help_text="Enables spawning and show in completion")
    short_name = models.CharField(
        max_length=12,
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
    tradeable = models.BooleanField(help_text="Whether this ball can be traded with others")
    economy = models.ForeignKey(
        Economy,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Economical regime of this country",
    )
    regime = models.ForeignKey(
        Regime, on_delete=models.CASCADE, help_text="Political regime of this country"
    )
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True, editable=False)
    translations = models.TextField(blank=True, null=True)

    def __str__(self) -> str:
        return self.country

    def collection_image(self) -> SafeText:
        return image_display(str(self.collection_card))

    collection_image.short_description = "Current collection card"

    def spawn_image(self) -> SafeText:
        return image_display(str(self.wild_card))

    spawn_image.short_description = "Current spawn asset"

    def preview(self):
        return render_to_string("ball_preview.html", {"ball_pk": self.pk})

    preview.short_description = "Card preview generator"

    class Meta:
        managed = False
        db_table = "ball"


class BallInstance(models.Model):
    catch_date = models.DateTimeField()
    health_bonus = models.IntegerField()
    attack_bonus = models.IntegerField()
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    trade_player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        related_name="ballinstance_trade_player_set",
        blank=True,
        null=True,
    )
    favorite = models.BooleanField()
    special = models.ForeignKey(Special, on_delete=models.SET_NULL, blank=True, null=True)
    server_id = models.BigIntegerField(
        blank=True, null=True, help_text="Discord server ID where this ball was caught"
    )
    tradeable = models.BooleanField()
    extra_data = models.JSONField()
    locked = models.DateTimeField(
        blank=True, null=True, help_text="If the instance was locked for a trade and when"
    )
    spawned_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "ballinstance"
        unique_together = (("player", "id"),)


class BlacklistedID(models.Model):
    discord_id = models.BigIntegerField(unique=True, help_text="Discord user ID")
    reason = models.TextField(blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    moderator_id = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "blacklistedid"


class BlacklistedGuild(models.Model):
    discord_id = models.BigIntegerField(unique=True, help_text="Discord Guild ID")
    reason = models.TextField(blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    moderator_id = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "blacklistedguild"


class BlacklistHistory(models.Model):
    discord_id = models.BigIntegerField(help_text="Discord ID")
    moderator_id = models.BigIntegerField(help_text="Discord Moderator ID")
    reason = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True, editable=False)
    id_type = models.CharField(max_length=64, default="user")
    action_type = models.CharField(max_length=64, default="blacklist")

    class Meta:
        managed = False
        db_table = "blacklisthistory"
        verbose_name_plural = "blacklisthistories"


class Trade(models.Model):
    date = models.DateTimeField(auto_now_add=True, editable=False)
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE)
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="trade_player2_set")

    class Meta:
        managed = False
        db_table = "trade"


class Tradeobject(models.Model):
    ballinstance = models.ForeignKey(BallInstance, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE)

    class Meta:
        managed = False
        db_table = "tradeobject"


class Friendship(models.Model):
    since = models.DateTimeField(auto_now_add=True, editable=False)
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE)
    player2 = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="friendship_player2_set"
    )

    class Meta:
        managed = False
        db_table = "friendship"


class Block(models.Model):
    date = models.DateTimeField(auto_now_add=True, editable=False)
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE)
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="block_player2_set")

    class Meta:
        managed = False
        db_table = "block"
