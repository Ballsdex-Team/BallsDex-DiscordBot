from asgiref.sync import sync_to_async
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from bd_models.models import BallInstance, Player


class VoteSettings(models.Model):
    vote_url = models.URLField(
        help_text="Link shown to users to vote for the bot.",
        default="https://top.gg/bot/1428438991203598467",
    )
    webhook_secret = models.CharField(
        max_length=128,
        help_text="Secret configured on your Top.gg webhook page, used to verify the "
        "x-topgg-signature header of incoming vote webhooks. Leave empty to keep the "
        "webhook server disabled.",
        blank=True,
        default="",
    )
    webhook_port = models.PositiveIntegerField(
        default=15261, help_text="Port the vote webhook server listens on."
    )
    min_rarity = models.FloatField(help_text="Lowest rarity that can be granted as a vote reward.", default=1.0)
    max_rarity = models.FloatField(help_text="Highest rarity that can be granted as a vote reward.", default=100.0)
    special_chance = models.FloatField(
        help_text="Chance (between 0 and 1) that the vote reward is a currently active special instead of "
        "a regular countryball.",
        default=0.05,
        validators=(MinValueValidator(0.0), MaxValueValidator(1.0)),
    )

    @classmethod
    def load(cls) -> "VoteSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    async def aload(cls) -> "VoteSettings":
        return await sync_to_async(cls.load)()

    def __str__(self) -> str:
        return "Vote settings"

    class Meta:
        db_table = "votesettings"
        managed = True
        verbose_name_plural = "Vote settings"
        constraints = (
            models.CheckConstraint(
                condition=Q(min_rarity__lte=F("max_rarity")),
                name="vote_min_rarity_lte_max",
                violation_error_message="Minimum rarity must be lower or equal to maximum rarity.",
            ),
        )


class VoteRecord(models.Model):
    """
    One entry per Top.gg vote webhook received, used to grant/track vote rewards and to
    prevent a replayed webhook from granting a reward again within the same 12h vote window.
    """

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="vote_records")
    voted_at = models.DateTimeField(auto_now_add=True, editable=False)
    reward = models.ForeignKey(BallInstance, on_delete=models.SET_NULL, null=True, blank=True)

    objects = models.Manager()

    def __str__(self) -> str:
        return f"Vote from {self.player} at {self.voted_at}"

    class Meta:
        db_table = "voterecord"
        managed = True
        ordering = ("-voted_at",)
        indexes = (models.Index(fields=("player_id", "voted_at")),)
