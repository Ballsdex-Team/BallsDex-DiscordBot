from __future__ import annotations

from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.contrib import admin, messages
from django_admin_action_forms import action_with_form

from admin_panel.webhook import notify_admins

from ..forms import BlacklistActionForm, BlacklistedListFilter
from ..models import BlacklistedID, BlacklistHistory, Player
from ..utils import BlacklistTabular

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    save_on_top = True
    inlines = (BlacklistTabular,)

    list_display = ("discord_id", "pk", "blacklisted")
    list_filter = (BlacklistedListFilter,)
    show_facets = admin.ShowFacets.NEVER

    search_fields = ("discord_id",)
    search_help_text = "Search for a Discord ID"

    actions = ("blacklist_users",)

    @admin.display(description="Is blacklisted", boolean=True)
    def blacklisted(self, obj: Player):
        return obj.is_blacklisted()

    @action_with_form(
        BlacklistActionForm, description="Blacklist the selected users"
    )  # type: ignore
    def blacklist_users(self, request: "HttpRequest", queryset: "QuerySet[Player]", data: dict):
        reason = (
            data["reason"]
            + f"\nDone through the admin panel by {request.user} ({request.user.pk})"
        )
        blacklists: list[BlacklistedID] = []
        histories: list[BlacklistHistory] = []
        for player in queryset:
            if BlacklistedID.objects.filter(discord_id=player.discord_id).exists():
                self.message_user(
                    request, f"Player {player.discord_id} is already blacklisted!", messages.ERROR
                )
                return
            blacklists.append(
                BlacklistedID(discord_id=player.discord_id, reason=reason, moderator_id=None)
            )
            histories.append(
                BlacklistHistory(discord_id=player.discord_id, reason=reason, moderator_id=0)
            )
        BlacklistedID.objects.bulk_create(blacklists)
        BlacklistHistory.objects.bulk_create(histories)

        self.message_user(
            request,
            f"Created blacklist for {queryset.count()} user{"s" if queryset.count() > 1 else ""}. "
            "This will be applied after reloading the bot's cache.",
        )
        async_to_sync(notify_admins)(
            f"{request.user} blacklisted players "
            f'{", ".join([str(x.discord_id) for x in queryset])} for the reason: {data["reason"]}.'
        )
