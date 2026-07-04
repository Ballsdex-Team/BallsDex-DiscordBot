from django.contrib import admin
from django.http import HttpRequest

from .models import CurrencySettings, Item, ItemBall


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    autocomplete_fields = ("special",)
    save_on_top = True
    fieldsets = [
        (None, {"fields": ["name", "description", "prize"]}),
        ("Configure Reward", {"fields": ["minimum_rarity", "maximum_rarity", "special"]}),
    ]
    list_display = ("name", "prize", "minimum_rarity", "maximum_rarity")
    list_editable = ("prize", "minimum_rarity", "maximum_rarity")
    list_filter = ("created_at", "special")
    ordering = ["-created_at"]

    search_fields = ("name",)


@admin.register(ItemBall)
class ItemBallAdmin(admin.ModelAdmin):
    list_display = ("item_name", "ball_name")

    @admin.display(description="Name of Item")
    def item_name(self, obj: ItemBall):
        return obj.item.name

    @admin.display(description="Name of Ball")
    def ball_name(self, obj: ItemBall):
        return obj.ball.country


@admin.register(CurrencySettings)
class CurrencySettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return super().has_add_permission(request) and CurrencySettings.objects.first() is None

    def has_delete_permission(self, request: HttpRequest, obj: CurrencySettings | None = None) -> bool:
        return False
