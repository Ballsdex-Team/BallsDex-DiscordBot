from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.contrib import admin, messages
from django.contrib.admin.utils import quote
from django.urls import reverse
from django.utils.html import format_html
from django_admin_action_forms import action_with_form
from django_admin_inline_paginator.admin import InlinePaginated
from nonrelated_inlines.admin import NonrelatedInlineMixin

from admin_panel.webhook import notify_admins

from ..forms import BlacklistActionForm, BlacklistedListFilter
from ..models import BallInstance, BlacklistedGuild, BlacklistHistory, GuildConfig
from ..utils import BlacklistTabular

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


class BallInstanceGuildTabular(InlinePaginated, NonrelatedInlineMixin, admin.TabularInline):
    model = BallInstance
    fk_name = "player"
    per_page = 50
    ordering = ("-catch_date",)
    fields = ("description", "player", "catch_time", "catch_date")
    readonly_fields = ("description", "player", "catch_time", "catch_date")
    show_change_link = True
    classes = ("collapse",)
    can_delete = False

    def get_form_queryset(self, obj: GuildConfig):
        return BallInstance.objects.filter(server_id=obj.guild_id).prefetch_related("player")

    @admin.display(description="Time to catch")
    def catch_time(self, obj: BallInstance):
        if obj.spawned_time:
            return str(obj.spawned_time - obj.catch_date)
        return "-"

    # adding a countryball cannot work from here since all fields are readonly
    def has_add_permission(self, request: "HttpRequest", obj: GuildConfig) -> bool:
        return False

    @admin.display(description="Player")
    def player(self, obj: BallInstance):
        opts = obj.player._meta
        admin_url = reverse(
            "%s:%s_%s_change" % (self.admin_site.name, opts.app_label, opts.model_name),
            None,
            (quote(obj.player.pk),),
        )
        # Display a link to the admin page.
        return format_html(f'<a href="{admin_url}">{obj.player}</a>')


@admin.register(GuildConfig)
class GuildAdmin(admin.ModelAdmin):
    list_display = ("guild_id", "spawn_channel", "enabled", "silent", "blacklisted")
    list_filter = ("enabled", "silent", BlacklistedListFilter)
    show_facets = admin.ShowFacets.NEVER  # type: ignore

    search_fields = ("guild_id", "spawn_channel")
    search_help_text = "Search by guild ID or spawn channel ID"

    inlines = (BlacklistTabular, BallInstanceGuildTabular)
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
            f"Created blacklist for {queryset.count()} guild"
            f"{"s" if queryset.count() > 1 else ""}. This will be applied after "
            "reloading the bot's cache.",
        )
        async_to_sync(notify_admins)(
            f"{request.user} blacklisted guilds "
            f'{", ".join([str(x.guild_id) for x in queryset])} for the reason: {data["reason"]}.'
        )
