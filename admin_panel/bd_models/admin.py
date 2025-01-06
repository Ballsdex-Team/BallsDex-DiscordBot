from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.forms import Textarea
from django.utils.safestring import mark_safe

from .models import Ball, Economy, Regime, Special

if TYPE_CHECKING:
    from django.db.models import Field
    from django.http.request import HttpRequest


@admin.register(Regime)
class RegimeAdmin(admin.ModelAdmin):
    pass


@admin.register(Economy)
class EconomyAdmin(admin.ModelAdmin):
    pass


@admin.register(Ball)
class BallAdmin(admin.ModelAdmin):
    raw_id_fields = ["regime", "economy"]
    readonly_fields = ("collection_image", "spawn_image", "preview")
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "country",
                    "health",
                    "attack",
                    "rarity",
                    "emoji_id",
                    "economy",
                    "regime",
                ],
            },
        ),
        (
            "Assets",
            {
                "description": "You must have permission from the copyright holder "
                "to use the files you're uploading!",
                "fields": [
                    "spawn_image",
                    "wild_card",
                    "collection_image",
                    "collection_card",
                    "credits",
                ],
            },
        ),
        (
            "Ability",
            {
                "description": "The ability of the countryball",
                "fields": ["capacity_name", "capacity_description"],
            },
        ),
        (
            "Advanced",
            {
                "description": "Advanced settings",
                "classes": ["collapse"],
                "fields": ["enabled", "tradeable", "short_name", "catch_names", "translations"],
            },
        ),
        ("Preview", {"description": "Generate previews", "fields": ["preview"]}),
    ]

    list_display = ["country", "emoji", "rarity", "capacity_name", "health", "attack", "enabled"]
    list_editable = ["enabled", "rarity"]
    list_filter = ["enabled", "tradeable", "regime", "economy", "created_at"]
    ordering = ["-created_at"]

    search_fields = [
        "country",
        "capacity_name",
        "capacity_description",
        "catch_names",
        "translations",
        "credits",
    ]
    search_help_text = (
        "Search for countryball name, abilitie name/content, credits, catch names or translations"
    )

    @admin.display(description="Emoji")
    def emoji(self, obj: Ball):
        return mark_safe(
            f'<img src="https://cdn.discordapp.com/emojis/{obj.emoji_id}.png?size=40" '
            f'title="ID: {obj.emoji_id}" />'
        )

    def formfield_for_dbfield(
        self, db_field: "Field[Any, Any]", request: "HttpRequest | None", **kwargs: Any
    ) -> "Field[Any, Any] | None":
        if db_field.name == "capacity_description":
            kwargs["widget"] = Textarea()
        return super().formfield_for_dbfield(db_field, request, **kwargs)  # type: ignore


@admin.register(Special)
class SpecialAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            None,
            {
                "fields": ["name", "catch_phrase", "rarity", "emoji", "background"],
            },
        ),
        (
            "Time range",
            {
                "fields": ["start_date", "end_date"],
                "description": "An optional time range to make the event limited in time. As soon "
                "as the event is loaded in the bot's cache, it will automatically load and unload "
                "at the specified time.",
            },
        ),
        (
            "Advanced",
            {
                "fields": ["tradeable", "hidden"],
                "classes": ["collapse"],
            },
        ),
    ]

    list_display = ["name", "emoji_display", "start_date", "end_date", "rarity", "hidden"]
    list_editable = ["hidden", "rarity"]
    list_filter = ["hidden", "tradeable"]

    search_fields = ["name", "catch_phrase"]

    @admin.display(description="Emoji")
    def emoji_display(self, obj: Special):
        return (
            mark_safe(
                f'<img src="https://cdn.discordapp.com/emojis/{obj.emoji}.png?size=40" '
                f'title="ID: {obj.emoji}" />'
            )
            if obj.emoji and obj.emoji.isdigit()
            else obj.emoji
        )

    def formfield_for_dbfield(
        self, db_field: "Field[Any, Any]", request: "HttpRequest | None", **kwargs: Any
    ) -> "Field[Any, Any] | None":
        if db_field.name == "catch_phrase":
            kwargs["widget"] = Textarea()
        return super().formfield_for_dbfield(db_field, request, **kwargs)  # type: ignore
