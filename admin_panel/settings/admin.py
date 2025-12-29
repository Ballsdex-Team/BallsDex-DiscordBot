from typing import TYPE_CHECKING

import yaml
from django import forms
from django.contrib import admin, messages
from django.db import models
from django.forms import widgets
from django_admin_action_forms import AdminActionForm, action_with_form

from .models import PromptMessage, Settings

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
                "fields": ("collectible_name", "plural_collectible_name", "bot_name", "balls_slash_name"),
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

    @action_with_form(YAMLImportForm, description="Import YAML settings")
    def import_yaml(self, request: "HttpRequest", queryset: "QuerySet[Settings]", data: dict):
        if queryset.count() != 1:
            self.message_user(request, "You cannot select multiple entries", messages.ERROR)
            return
        s = queryset.get()

        file: "UploadedFile" = data["file"]
        content: dict = yaml.load(file, yaml.Loader)

        s.bot_token = content.get("discord-token") or s.bot_token
        s.prefix = content.get("text-prefix") or s.prefix
        owners: dict
        if owners := content.get("owners", {}):
            s.team_owners = owners.get("team-members-are-owners", False)
            s.coowners = ";".join(str(x) for x in owners.get("co-owners", []))

        s.collectible_name = content.get("collectible-name") or s.collectible_name
        s.plural_collectible_name = content.get("plural-collectible-name") or s.plural_collectible_name
        s.bot_name = content.get("bot-name") or s.bot_name
        s.balls_slash_name = content.get("players-group-cog-name") or s.balls_slash_name
        s.favorited_collectible_emoji = content.get("favorited-collectible-emoji") or s.favorited_collectible_emoji
        s.max_favorites = content.get("max-favorites") or s.max_favorites
        s.max_attack_bonus = content.get("max-attack-bonus") or s.max_attack_bonus
        s.max_health_bonus = content.get("max-health-bonus") or s.max_health_bonus
        s.show_rarity = content.get("show-rarity", False)
        s.admin_channel_ids = (
            ";".join(str(x) for x in content.get("admin-command", {}).get("admin-channels-ids", []))
            or s.admin_channel_ids
        )

        about: dict
        if about := content.get("about", {}):
            s.about_description = about.get("description") or s.about_description
            s.repository = about.get("github-link") or s.repository
            s.discord_invite = about.get("discord-invite") or s.discord_invite
            s.terms_of_service = about.get("terms-of-service") or s.terms_of_service
            s.privacy_policy = about.get("privacy-policy") or s.privacy_policy

        prometheus: dict
        if prometheus := content.get("prometheus", {}):
            s.prometheus_enabled = prometheus.get("enabled") or s.prometheus_enabled
            s.prometheus_host = prometheus.get("host") or s.prometheus_host
            s.prometheus_port = prometheus.get("port") or s.prometheus_port

        spawn_range: tuple[int, int]
        if spawn_range := content.get("spawn-chance-range", ()):
            s.spawn_chance_min = spawn_range[0]
            s.spawn_chance_max = spawn_range[1]

        admin_panel: dict
        if admin_panel := content.get("admin-panel", {}):
            s.client_id = admin_panel.get("client-id") or s.client_id
            s.client_secret = admin_panel.get("client-secret") or s.client_secret
            s.webhook_logging = admin_panel.get("webhook-url") or s.webhook_logging

        sentry: dict
        if sentry := content.get("sentry", {}):
            s.sentry_dsn = sentry.get("dsn") or s.sentry_dsn
            s.sentry_env = sentry.get("environment") or s.sentry_env

        catch: dict
        if catch := content.get("catch", {}):
            s.catch_button_label = catch.get("catch_button_label") or s.catch_button_label
            objects: list[PromptMessage] = []
            for msg in catch.get("spawn_msgs", []):
                objects.append(PromptMessage(category=PromptMessage.PromptType.SPAWN, message=msg, settings=s))
            for msg in catch.get("caught_msgs", []):
                objects.append(PromptMessage(category=PromptMessage.PromptType.CATCH, message=msg, settings=s))
            for msg in catch.get("wrong_msgs", []):
                objects.append(PromptMessage(category=PromptMessage.PromptType.WRONG, message=msg, settings=s))
            for msg in catch.get("slow_msgs", []):
                objects.append(PromptMessage(category=PromptMessage.PromptType.SLOW, message=msg, settings=s))
            PromptMessage.objects.bulk_create(objects, ignore_conflicts=True)

        s.save()
        self.message_user(request, "Settings imported!", messages.SUCCESS)
