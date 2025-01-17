from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin
from django.db.models import Exists, OuterRef
from django_admin_action_forms import AdminActionForm

from .models import BlacklistedGuild, BlacklistedID, Player

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest

    from .admin import GuildAdmin, PlayerAdmin
    from .models import GuildConfig


class BlacklistActionForm(AdminActionForm):
    reason = forms.CharField(label="Reason", required=True)


class BlacklistedListFilter(admin.SimpleListFilter):
    title = "blacklisted"
    parameter_name = "blacklisted"

    def lookups(
        self, request: "HttpRequest", model_admin: "PlayerAdmin | GuildAdmin"
    ) -> list[tuple[Any, str]]:
        return [(True, "True"), (False, "False")]

    def queryset(
        self, request: "HttpRequest", queryset: "QuerySet[Player | GuildConfig]"
    ) -> "QuerySet[Player | GuildConfig]":
        if self.value() is None:
            return queryset
        if queryset.model == Player:
            annotation = Exists(BlacklistedID.objects.filter(discord_id=OuterRef("discord_id")))
        else:
            annotation = Exists(BlacklistedGuild.objects.filter(discord_id=OuterRef("guild_id")))

        return queryset.annotate(listed=annotation).filter(listed=self.value())
