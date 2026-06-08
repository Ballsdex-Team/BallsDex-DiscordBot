from typing import TYPE_CHECKING

import yaml
from django import forms
from django.contrib import admin, messages
from django.db import models
from django.forms import widgets
from django_admin_action_forms import AdminActionForm, action_with_form

from .models import PromptMessage, Settings
from .services.yml_import import import_settings_from_yaml

if TYPE_CHECKING:
    from django.core.files.uploadedfile import UploadedFile
    from django.db.models import QuerySet
    from django.http import HttpRequest


class YAMLImportForm(AdminActionForm):
    file = forms.FileField(widget=forms.ClearableFileInput(attrs={"accept": ".yml,.yaml"}), allow_empty_file=False)


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
                "fields": (
                    "collectible_name",
                    "plural_collectible_name",
                    "bot_name",
                    "balls_slash_name",
                    "site_base_url",
                ),
            },
        ),
        (
            "Currency support",
            {
                "description": "The bot provides a basic currency feature but is disabled by default, "
                "unless you configure the values below. It is recommended that you keep it disabled unless you have "
                "3rd-party integrations that will make use of the currency.\n"
                "Only admin commands and trade support are included in the core bot for now.",
                "fields": ("currency_name", "currency_plural_name", "currency_symbol", "currency_symbol_before"),
                "classes": ("collapse",),
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
                    "spawn_chance_min",
                    "spawn_chance_max",
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
    actions = ("import_yaml",)

    # disallow creating more than one instance
    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and Settings.objects.first() is None

    # and disallow deleting the singleton
    def has_delete_permission(self, request: "HttpRequest", obj: Settings | None = None) -> bool:
        return False

    @action_with_form(YAMLImportForm, description="Import YAML settings")
    def import_yaml(self, request: "HttpRequest", queryset: "QuerySet[Settings]", data: dict):
        if queryset.count() != 1:
            self.message_user(request, "You cannot select multiple entries", messages.ERROR)
            return
        s = queryset.get()

        file: "UploadedFile" = data["file"]
        content: dict = yaml.load(file, yaml.Loader)
        import_settings_from_yaml(content, s)

        self.message_user(request, "Settings imported!", messages.SUCCESS)
