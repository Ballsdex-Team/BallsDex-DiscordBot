from typing import TYPE_CHECKING

from django.contrib import admin

from ..models import VoteRecord

if TYPE_CHECKING:
    from django.http import HttpRequest


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
