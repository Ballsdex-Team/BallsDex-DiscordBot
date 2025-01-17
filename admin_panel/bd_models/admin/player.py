from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.contrib.messages import SUCCESS
from nonrelated_inlines.admin import NonrelatedTabularInline

from ..models import BlacklistedID, BlacklistHistory, Player

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


class BlacklistTabular(NonrelatedTabularInline):
    model = BlacklistHistory
    extra = 0
    can_delete = False
    verbose_name_plural = "Blacklist history"
    fields = ("date", "reason", "moderator_id", "action_type")
    readonly_fields = ("date", "moderator_id", "action_type")

    def has_add_permission(self, request: "HttpRequest", obj: Any) -> bool:  # type: ignore
        return False

    def get_form_queryset(self, obj: Player):
        return BlacklistHistory.objects.filter(discord_id=obj.discord_id)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ("discord_id", "pk")
    search_fields = ("discord_id",)
    search_help_text = "Search for a Discord ID"
    actions = ("blacklist_users",)
    inlines = (BlacklistTabular,)

    # TODO: permissions and form
    @admin.action(description="Blacklist users")
    async def blacklist_users(self, request: "HttpRequest", queryset: "QuerySet[Player]"):
        result = await BlacklistedID.objects.abulk_create(
            (
                BlacklistedID(
                    discord_id=x.discord_id,
                    reason=f"Blacklisted via admin panel by {request.user}",
                )
                for x in queryset
            )
        )
        self.message_user(request, f"Successfully created {len(result)} blacklists", SUCCESS)
