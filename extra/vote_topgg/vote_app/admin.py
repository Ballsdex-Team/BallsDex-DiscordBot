from typing import TYPE_CHECKING

from django.contrib import admin

from .models import VoteRecord, VoteSettings

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(VoteSettings)
class VoteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and VoteSettings.objects.first() is None

    def has_delete_permission(self, request: "HttpRequest", obj: VoteSettings | None = None) -> bool:
        return False


@admin.register(VoteRecord)
class VoteRecordAdmin(admin.ModelAdmin):
    list_display = ("player", "voted_at", "reward")
    list_filter = ("voted_at",)
    search_fields = ("player__discord_id",)
    autocomplete_fields = ("player", "reward")
    ordering = ("-voted_at",)

    def has_add_permission(self, request: "HttpRequest") -> bool:
        return False

    def has_change_permission(self, request: "HttpRequest", obj: VoteRecord | None = None) -> bool:
        return False
