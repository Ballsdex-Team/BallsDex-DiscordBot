from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.contrib.admin.utils import quote
from django.forms import Textarea
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.text import capfirst

from ..models import Ball, BallInstance, Economy, Regime, TradeObject, transform_media

if TYPE_CHECKING:
    from django.db.models import Field, Model, QuerySet
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

    def get_deleted_objects(
        self, objs: "QuerySet[Regime]", request: "HttpRequest"
    ) -> tuple[list[Any], dict[str, int], set[Any], list[Any]]:
        regime_ids = [x.pk for x in objs]
        model_count = {
            "regimes": len(regime_ids),
            "balls": Ball.objects.filter(regime_id__in=regime_ids).count(),
            "ball instances": BallInstance.objects.filter(ball__regime_id__in=regime_ids).count(),
            "trade objects": TradeObject.objects.filter(
                ballinstance__ball__regime_id__in=regime_ids
            ).count(),
        }

        def format_callback(obj: "Model"):
            opts = obj._meta
            admin_url = reverse(
                "%s:%s_%s_change" % (self.admin_site.name, opts.app_label, opts.model_name),
                None,
                (quote(obj.pk),),
            )
            # Display a link to the admin page.
            return format_html(
                '{}: <a href="{}">{}</a>', capfirst(opts.verbose_name), admin_url, obj
            )

        text = []
        for regime in objs:
            subtext = []
            for ball in Ball.objects.filter(regime=regime):
                subtext.append(format_callback(ball))
            text.append(format_callback(regime))
            text.append(subtext)

        return (
            [
                "Displaying Ball related objects (instances and trade objects) "
                "is too expensive and has been disabled.",
                *text,
            ],
            model_count,
            set(),
            [],
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

    def get_deleted_objects(
        self, objs: "QuerySet[Ball]", request: "HttpRequest"
    ) -> tuple[list[str], dict[str, int], set[Any], list[Any]]:
        instances = BallInstance.objects.filter(ball_id__in=set(x.pk for x in objs))
        if len(instances) < 500:
            return super().get_deleted_objects(objs, request)  # type: ignore
        model_count = {
            "balls": len(objs),
            "ball instances": len(instances),
            "trade objects": TradeObject.objects.filter(ballinstance_id__in=instances).count(),
        }
        return ["Too long to display"], model_count, set(), []
