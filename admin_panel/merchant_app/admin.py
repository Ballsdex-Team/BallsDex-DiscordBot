from typing import TYPE_CHECKING

from django.contrib import admin
from django.http import HttpRequest

from .models import GlobalShop, MerchantSettings, MerchantItem

if TYPE_CHECKING:
    from django.db.models import QuerySet


@admin.register(MerchantSettings)
class MerchantSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return super().has_add_permission(request) and MerchantSettings.objects.first() is None

    def has_delete_permission(self, request: HttpRequest, obj: MerchantSettings | None = None) -> bool:
        return False


@admin.register(MerchantItem)
class MerchantItemAdmin(admin.ModelAdmin):
    autocomplete_fields = ("ball", "special")
    save_on_top = True
    fieldsets = [
        (None, {"fields": ["name", "prize", "rarity"]}),
        (
            "Time range",
            {
                "fields": ["start_date", "end_date"],
                "description": "An optional time range to make the item limited in time. As soon "
                "as the item is loaded in the bot's cache, it will automatically load and unload "
                "at the specified time.",
            },
        ),
        ("Rewards", {"fields": ["ball", "special"]}),
    ]

    list_display = ("name", "prize", "rarity", "ball_name", "special_name")
    list_editable = ("rarity", "prize")
    list_filter = ("created_at", "start_date", "end_date")

    search_fields = ["name", "pk"]

    @admin.display(description="Name of the ball")
    def ball_name(self, obj: MerchantItem):
        return obj.ball.country

    @admin.display(description="Name of the special")
    def special_name(self, obj: MerchantItem):
        return obj.special.name if obj.special else "-"


@admin.register(GlobalShop)
class GlobalShopAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "item_count")
    search_fields = ("name",)
    filter_horizontal = ("items",)
    save_on_top = True

    @admin.display(description="Number of items")
    def item_count(self, obj: GlobalShop) -> int:
        return obj.items.count()

    def get_queryset(self, request: "HttpRequest") -> "QuerySet[GlobalShop]":
        return super().get_queryset(request).prefetch_related("items")
