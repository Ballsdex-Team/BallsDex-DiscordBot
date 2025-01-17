from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.contrib import admin, messages
from django_admin_action_forms import action_with_form

from admin_panel.webhook import notify_admins

from ..forms import BlacklistActionForm, BlacklistedListFilter
from ..models import BlacklistedGuild, BlacklistHistory, GuildConfig
from ..utils import BlacklistTabular

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


@admin.register(GuildConfig)
class GuildAdmin(admin.ModelAdmin):
    list_display = ("guild_id", "spawn_channel", "enabled", "silent", "blacklisted")
    list_filter = ("enabled", "silent", BlacklistedListFilter)
    show_facets = admin.ShowFacets.NEVER

    search_fields = ("guild_id", "spawn_channel")
    search_help_text = "Search by guild ID or spawn channel ID"

    inlines = (BlacklistTabular,)
    actions = ("blacklist_guilds",)

    @admin.display(description="Is blacklisted", boolean=True)
    def blacklisted(self, obj: GuildConfig):
        return BlacklistedGuild.objects.filter(discord_id=obj.guild_id).exists()

    @action_with_form(
        BlacklistActionForm, description="Blacklist the selected guilds"
    )  # type: ignore
    def blacklist_guilds(
        self, request: "HttpRequest", queryset: "QuerySet[GuildConfig]", data: dict
    ):
        reason = (
            data["reason"]
            + f"\nDone through the admin panel by {request.user} ({request.user.pk})"
        )
        blacklists: list[BlacklistedGuild] = []
        histories: list[BlacklistHistory] = []
        for guild in queryset:
            if BlacklistedGuild.objects.filter(discord_id=guild.guild_id).exists():
                self.message_user(
                    request, f"Guild {guild.guild_id} is already blacklisted!", messages.ERROR
                )
                return
            blacklists.append(
                BlacklistedGuild(discord_id=guild.guild_id, reason=reason, moderator_id=None)
            )
            histories.append(
                BlacklistHistory(
                    discord_id=guild.guild_id, reason=reason, moderator_id=0, id_type="guild"
                )
            )
        BlacklistedGuild.objects.bulk_create(blacklists)
        BlacklistHistory.objects.bulk_create(histories)

        self.message_user(
            request,
            f"Created blacklist for {queryset.count()} guild{"s" if queryset.count() > 1 else ""}. "
            "This will be applied after reloading the bot's cache.",
        )
        async_to_sync(notify_admins)(
            f"{request.user} blacklisted guilds "
            f'{", ".join([str(x.guild_id) for x in queryset])} for the reason: {data["reason"]}.'
        )
