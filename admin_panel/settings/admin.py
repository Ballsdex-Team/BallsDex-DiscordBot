from typing import TYPE_CHECKING

from django.contrib import admin
from django.db import models
from django.forms import widgets

from .models import PromptMessage, Settings

if TYPE_CHECKING:
    from django.http import HttpRequest


class PromptInline(admin.TabularInline):
    model = PromptMessage
    formfield_overrides = {models.TextField: {"widget": widgets.Textarea({"rows": 2, "cols": 60})}}
    extra = 0
    classes = ("collapse",)
    ordering = ("category",)


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    save_on_top = True
    formfield_overrides = {models.TextField: {"widget": widgets.TextInput}}
    inlines = (PromptInline,)
    fieldsets = [
        (None, {"fields": ("bot_token", "prefix")}),
        (
            "Bot personalization",
            {
                "description": "Important fields you should customize to make this bot your own",
                "fields": ("collectible_name", "plural_collectible_name", "bot_name", "balls_slash_name"),
            },
        ),
        (
            "Advanced personalization",
            {
                "description": "Advanced options to further personalize your bot",
                "fields": (
                    "catch_button_label",
                    "favorited_collectible_emoji",
                    "max_favorites",
                    "max_attack_bonus",
                    "max_health_bonus",
                    "show_rarity",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "/about",
            {
                "description": "These fields will personalize the /about command",
                "fields": ("about_description", "discord_invite", "terms_of_service", "privacy_policy", "repository"),
            },
        ),
        (
            "Ownership and administration",
            {
                "description": "Configure how administrative actions must be handled.",
                "fields": ("admin_channel_ids", "webhook_logging", "team_owners", "coowners"),
            },
        ),
        (
            "Login with Discord",
            {
                "description": "Configure this to login to this panel using Discord OAuth2",
                "fields": ("client_id", "client_secret"),
            },
        ),
        (
            "Advanced",
            {
                "description": "Advanced settings, only use if you know what those settings mean",
                "classes": ("collapse",),
                "fields": ("sentry_dsn", "sentry_env"),
            },
        ),
    ]

    # disallow creating more than one instance
    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and Settings.objects.first() is None
