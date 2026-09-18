from typing import TYPE_CHECKING

from django.contrib import admin

from .models import PackBonusRole, PackSettings

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(PackSettings)
class PackSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Daily packs", {"fields": ["daily_uses", "min_rarity_daily", "max_rarity_daily"]}),
        (
            "Bonus daily packs",
            {
                "description": "Ways for players to open more daily packs. Extra packs can also be given to Discord "
                "roles from the Pack bonus roles page.",
                "fields": ["bonus_daily_chance", "streak_bonus_days", "streak_grace_hours"],
            },
        ),
        ("Weekly packs", {"fields": ["min_rarity_weekly", "max_rarity_weekly"]}),
    ]

    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and PackSettings.objects.first() is None

    def has_delete_permission(self, request: "HttpRequest", obj: PackSettings | None = None) -> bool:
        return False


@admin.register(PackBonusRole)
class PackBonusRoleAdmin(admin.ModelAdmin):
    list_display = ("role_id", "server_id", "bonus_daily_uses")
    list_editable = ("bonus_daily_uses",)
    list_filter = ("server_id",)
    search_fields = ("server_id", "role_id")
