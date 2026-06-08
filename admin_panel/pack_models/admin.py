from typing import TYPE_CHECKING

from django.contrib import admin

from .models import PackSettings

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(PackSettings)
class PackSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and PackSettings.objects.first() is None

    def has_delete_permission(self, request: "HttpRequest", obj: PackSettings | None = None) -> bool:
        return False
