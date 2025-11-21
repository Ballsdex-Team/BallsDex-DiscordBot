from __future__ import annotations

import random
import re
import warnings
from typing import TYPE_CHECKING, cast

from django.conf import settings as django_settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.signals import post_init
from django.dispatch import receiver
from django.forms import ValidationError
from django.utils.functional import cached_property

COLON_IDS_RE = re.compile(r"^(\d{17,21}(;\d{17,21})*)?$")
SLASH_COMMAND_RE = re.compile(r"^[-_'\S]{1,32}$")
DISCORD_INVITE_RE = re.compile(r"^https?://(discord.gg|discord(app)?.com/invite)/[a-zA-Z0-9]+$")
DISCORD_WEBHOOK_RE = re.compile(r"^https://discord.com/api/webhooks/[0-9]{17,22}/[a-zA-Z0-9-_]{68}$")
SENTRY_ENV_RE = re.compile(r"^(?!None$)[^\s/]{,64}$")
PYTHON_PATH_RE = re.compile(r"^[a-zA-Z_][\\.a-zA-Z0-9_]+$")


class Settings(models.Model):
    # base settings
    bot_token = models.CharField(help_text="Discord bot token", max_length=80, default="")
    prefix = models.CharField(help_text="Prefix for all text commands", max_length=10, default="b.")
    collectible_name = models.TextField(help_text="The singular name of your collectible", default="countryball")
    plural_collectible_name = models.TextField(help_text="The plural name of your collectible", default="countryballs")
    bot_name = models.TextField(help_text="The name of your bot", default="BallsDex")
    balls_slash_name = models.TextField(
        help_text='Overrides "/balls" slash command',
        default="balls",
        validators=(RegexValidator(SLASH_COMMAND_RE, message="Invalid slash command name."),),
    )

    # further customization
    favorited_collectible_emoji = models.CharField(
        help_text="Emoji for the favorited collectibles",
        default="\N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}",
        max_length=3,
    )
    max_favorites = models.PositiveIntegerField(help_text="Maximum number of favorites configurable", default=20)
    max_attack_bonus = models.PositiveIntegerField(
        help_text="Min/max bonus for attack statistic. A value of 20 means it goes from -20% to 20%", default=20
    )
    max_health_bonus = models.PositiveIntegerField(
        help_text="Min/max bonus for health statistic. A value of 20 means it goes from -20% to 20%", default=20
    )
    show_rarity = models.BooleanField(
        help_text="Whether to show the rarity on the card (replaces economy icon)", default=False
    )
    catch_button_label = models.CharField(max_length=80, help_text="Label of the catch button", default="Catch me")

    # spawn algorithm details
    spawn_chance_min = models.PositiveIntegerField(
        help_text="Minimum base chance value to spawn a ball. Lower value leads to more spawn.", default=40
    )
    spawn_chance_max = models.PositiveIntegerField(
        help_text="Maximum base chance value to spawn a ball. Lower value leads to more spawn. "
        "A wide range between min and max leads to a broader difference in spawn times.",
        default=55,
    )
    spawn_manager = models.TextField(
        help_text="Python path to a class that will handle spawn logic.",
        default="ballsdex.packages.countryballs.spawn.SpawnManager",
        validators=(RegexValidator(PYTHON_PATH_RE, message="This is not a valid Python path."),),
    )

    # /about command
    about_description = models.TextField(
        help_text="A small text bot shown in the /about command.",
        default="Collect countryballs on Discord, exchange them and battle with friends!",
    )
    repository = models.URLField(
        help_text="URL to the repository with the source code.",
        default="https://github.com/Ballsdex-Team/BallsDex-DiscordBot",
    )
    discord_invite = models.URLField(
        help_text="Invite to a Discord server that you own. Shown in /about and to blacklisted users.",
        default="",
        validators=(RegexValidator(DISCORD_INVITE_RE, message="This is not a valid Discord invite."),),
    )
    terms_of_service = models.URLField(help_text="Link to your terms of service.", default="")
    privacy_policy = models.URLField(help_text="Link to your privacy policy.", default="")

    # admin command control
    admin_channel_ids = models.TextField(
        help_text="Semicolon-delimited list of channel IDs where admin commands can be used. Ignored for owners. "
        "If empty, then admin commands can be used everywhere.",
        validators=(RegexValidator(COLON_IDS_RE, message="The IDs must be semicolon-separated"),),
        blank=True,
        default="",
    )
    webhook_logging = models.URLField(
        help_text="An optional Discord Webhook where admin events will be logged.",
        validators=(RegexValidator(DISCORD_WEBHOOK_RE, message="Only Discord webhooks are supported."),),
        null=True,
        blank=True,
        default=None,
    )

    # ownership
    team_owners = models.BooleanField(
        help_text="Whether to consider Discord Developer Team members (regardless of their roles) as owner of the bot.",
        default=False,
    )
    coowners = models.TextField(
        help_text="A list of user IDs that must be considered bot owners. This will give them full privilege.",
        validators=(RegexValidator(COLON_IDS_RE, message="The IDs must be semicolon-separated"),),
        null=True,
        blank=True,
        default=None,
    )

    @cached_property
    def co_owners(self):
        return [] if self.coowners is None else [int(x) for x in self.coowners.split(";") if x]

    prometheus_enabled = models.BooleanField(help_text="Enable the Prometheus metrics collection", default=False)
    prometheus_host = models.GenericIPAddressField(help_text="IP to bind for Prometheus server", default="0.0.0.0")
    prometheus_port = models.PositiveIntegerField(help_text="Port to bind for Prometheus server", default=15260)

    # discord OAuth2 details
    client_id = models.PositiveBigIntegerField(
        help_text="OAuth2 Discord application ID", null=True, blank=True, default=None
    )
    client_secret = models.TextField(help_text="OAuth2 Discord application secret", null=True, blank=True, default=None)

    sentry_dsn = models.URLField(help_text="Sentry DSN URL for error reporting", null=True, blank=True, default=None)
    sentry_env = models.CharField(
        max_length=64,
        help_text="Sentry environment key",
        default="production",
        validators=(
            RegexValidator(
                SENTRY_ENV_RE,
                message="Sentry environment key cannot contain spaces, newlines or forward slashes, "
                'can\'t be the string "None", or exceed 64 characters.',
            ),
        ),
    )

    prompts: models.QuerySet[PromptMessage]

    @cached_property
    def catch_messages(self):
        return [x.message for x in self.prompts.all() if x.category == PromptMessage.PromptType.CATCH]

    @cached_property
    def wrong_messages(self):
        return [x.message for x in self.prompts.all() if x.category == PromptMessage.PromptType.WRONG]

    @cached_property
    def spawn_messages(self):
        return [x.message for x in self.prompts.all() if x.category == PromptMessage.PromptType.SPAWN]

    @cached_property
    def slow_messages(self):
        return [x.message for x in self.prompts.all() if x.category == PromptMessage.PromptType.SLOW]

    def get_random_message(self, category: PromptMessage.PromptType):
        match category:
            case PromptMessage.PromptType.CATCH:
                return random.choice(self.catch_messages)
            case PromptMessage.PromptType.WRONG:
                return random.choice(self.wrong_messages)
            case PromptMessage.PromptType.SPAWN:
                return random.choice(self.spawn_messages)
            case PromptMessage.PromptType.SLOW:
                return random.choice(self.slow_messages)

    @property
    @warnings.deprecated("This setting returns nothing, Webhook notifications must be used instead")
    def log_channel(self):
        return None

    @property
    @warnings.deprecated("Literal package list, a new package discovery solution is worked on")
    def packages(self):
        return (
            "ballsdex.packages.admin",
            "ballsdex.packages.balls",
            "ballsdex.packages.guildconfig",
            "ballsdex.packages.countryballs",
            "ballsdex.packages.info",
            "ballsdex.packages.players",
            "ballsdex.packages.trade",
        )

    def clean(self) -> None:
        if Settings.objects.exclude(pk=self.pk).exists():
            raise ValidationError("You can only have one instance of settings.")

    def __str__(self) -> str:
        return "Global bot settings"

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=Q(Q(client_id=None) | Q(client_id=0), Q(client_secret=None) | Q(client_secret=""))
                | Q(client_id__isnull=False, client_secret__isnull=False),
                name="oauth_params_null_together",
                violation_error_message="client_id and client_secret must both be set or null, "
                "you cannot set only one.",
            ),
            models.CheckConstraint(
                condition=Q(spawn_chance_min__lte=F("spawn_chance_max")),
                name="spawn_chance_min_lt_max",
                violation_error_message="Minimum spawn chance value must be lower or equal to maximum chance.",
            ),
        )
        verbose_name_plural = "Settings"


class PromptMessage(models.Model):
    class PromptType(models.IntegerChoices):
        CATCH = 1
        WRONG = 2
        SPAWN = 3
        SLOW = 4

    settings = models.ForeignKey(Settings, on_delete=models.CASCADE, related_name="prompts")
    message = models.TextField(help_text="The message to send")
    category = models.PositiveSmallIntegerField(help_text="Message category", choices=PromptType)

    def __str__(self) -> str:
        return ""


@receiver(post_init, sender=Settings)
def load_details(sender: type[Settings], instance: Settings, **kwargs):
    from bd_models.apps import BdModelsConfig
    from bd_models.models import Ball, BallInstance

    django_settings.SOCIAL_AUTH_DISCORD_KEY = instance.client_id
    django_settings.SOCIAL_AUTH_DISCORD_SECRET = instance.client_secret

    BdModelsConfig.verbose_name = f"{instance.bot_name} models"
    Ball._meta.verbose_name = instance.collectible_name
    Ball._meta.verbose_name_plural = instance.plural_collectible_name
    BallInstance._meta.verbose_name = f"{instance.collectible_name} instance"
    BallInstance._meta.verbose_name_plural = f"{instance.collectible_name} instances"


class SettingsProxy:
    instance: Settings | None = None

    def __getattr__(self, name: str):
        if self.instance is None:
            raise RuntimeError("Settings aren't loaded yet")
        return getattr(self.instance, name)

    def __setattr__(self, name: str, value):
        if name == "instance":
            super().__setattr__(name, value)
        else:
            setattr(self.instance, name, value)


if TYPE_CHECKING:
    settings: Settings
else:
    settings = SettingsProxy()


def load_settings():
    instance = Settings.objects.prefetch_related("prompts").first()
    if not instance:
        raise RuntimeError("No Settings instance found!")
    singleton = cast(SettingsProxy, settings)
    singleton.instance = instance
