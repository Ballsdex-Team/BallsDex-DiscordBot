from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.forms import Textarea
from django.utils.safestring import mark_safe

from ..models import Ball, Economy, Regime
from ..utils import transform_media

if TYPE_CHECKING:
    from django.db.models import Field
    from django.http import HttpRequest


@admin.register(Regime)
class RegimeAdmin(admin.ModelAdmin):
    list_display = ("name", "background_image", "pk")
    search_fields = ("name",)

    @admin.display()
    def background_image(self, obj: Regime):
        return mark_safe(
            f'<img src="/media/{transform_media(str(obj.background))}" height=60px />'
        )


@admin.register(Economy)
class EconomyAdmin(admin.ModelAdmin):
    list_display = ("name", "icon_image", "pk")
    search_fields = ("name",)

    @admin.display()
    def icon_image(self, obj: Economy):
        return mark_safe(f'<img src="/media/{transform_media(str(obj.icon))}" height=30px />')


@admin.register(Ball)
class BallAdmin(admin.ModelAdmin):
    autocomplete_fields = ("regime", "economy")
    readonly_fields = ("collection_image", "spawn_image")
    save_on_top = True
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
                "fields": [
                    "enabled",
                    "tradeable",
                    "short_name",
                    "catch_names",
                    "translations",
                    "capacity_logic",
                ],
            },
        ),
    ]

    list_display = [
        "country",
        "pk",
        "emoji",
        "rarity",
        "capacity_name",
        "health",
        "attack",
        "enabled",
    ]
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
        "pk",
    ]
    search_help_text = (
        "Search for countryball name, ID, ability name/content, "
        "credits, catch names or translations"
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
