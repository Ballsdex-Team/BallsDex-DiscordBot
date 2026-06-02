from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin
from django.utils.safestring import mark_safe

from .models import Collectible


class SpecialFilter(AutocompleteFilter):
    title = "special"
    field_name = "special"


class BallFilter(AutocompleteFilter):
    title = "countryball"
    field_name = "ball"


@admin.register(Collectible)
class CollectibleAdmin(admin.ModelAdmin):
    autocomplete_fields = ("ball", "special")
    save_on_top = True
    fieldsets = [
        (None, {"fields": ["name", "description", "price", "emoji_id"]}),
        (
            "Collectible Requirement Values",
            {
                "description": (
                    "Configure the requirements for this collectible. If all fields are blank, "
                    "the collectible can be obtained without any requirements. The fields "
                    "total_amount and balls_amount cannot be enabled at the same time."
                ),
                "fields": ["ball", "special", "amount"],
            },
        ),
    ]
    list_display = ("name", "price", "emoji")
    list_editable = ("price",)
    list_filter = (BallFilter, "created_at", SpecialFilter)
    ordering = ["-created_at"]

    search_fields = ("name",)

    @admin.display(description="Emoji")
    def emoji(self, obj: Collectible):
        return mark_safe(
            f'<img src="https://cdn.discordapp.com/emojis/{obj.emoji_id}.png?size=40" title="ID: {obj.emoji_id}" />'
        )
