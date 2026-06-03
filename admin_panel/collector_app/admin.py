from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin

from bd_models.utils import ApproxCountPaginator
from .models import Collector, CollectorRequirement

class RequirementsInline(admin.TabularInline):
    model = CollectorRequirement
    extra = 0
    classes = ("collapse",)
    ordering = ("amount",)

class SpecialFilter(AutocompleteFilter):
    title = "special"
    field_name = "special"


class BallFilter(AutocompleteFilter):
    title = "countryball"
    field_name = "ball"

@admin.register(Collector)
class CollectorAdmin(admin.ModelAdmin):
    save_on_top = True
    autocomplete_fields = ("ball", "special")
    inlines = (RequirementsInline,)
    fieldsets = [
        (None, {"fields": ("name", "ball", "special", "tradeable")}),
        ("Time Range", {"fields": ("start_date", "end_date")})
    ]

    list_display = ("name", "pk")
    list_filter = (BallFilter, "created_at", SpecialFilter)
    ordering = ["-created_at"]
    show_facets = (
        admin.ShowFacets.NEVER  # type: ignore
    )  # hide filtered counts (considerable slowdown)
    show_full_result_count = False
    paginator = ApproxCountPaginator
