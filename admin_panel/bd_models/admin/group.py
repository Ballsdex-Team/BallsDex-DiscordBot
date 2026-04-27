from typing import TYPE_CHECKING

from django.contrib import admin

from ..models import Group

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "ball_count", "pk")
    search_fields = ("name",)
    filter_horizontal = ("balls",)
    save_on_top = True

    @admin.display(description="Number of balls")
    def ball_count(self, obj: Group) -> int:
        return obj.balls.count()

    def get_queryset(self, request: "HttpRequest") -> "QuerySet[Group]":
        return super().get_queryset(request).prefetch_related("balls")
