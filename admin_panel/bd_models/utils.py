from typing import TYPE_CHECKING

from django.core.paginator import Paginator
from django.db import connection
from django.http import HttpRequest
from django.utils.functional import cached_property
from nonrelated_inlines.admin import NonrelatedTabularInline

from .models import BlacklistHistory, Player

if TYPE_CHECKING:
    from .models import GuildConfig


class ApproxCountPaginator(Paginator):
    @cached_property
    def count(self) -> int:  # pyright: ignore [reportIncompatibleMethodOverride]
        # if this object isn't empty, then it's a paginator that has been applied filters or search
        if self.object_list.query.where.children:  # type: ignore
            return super().count

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT reltuples AS estimate FROM pg_class where relname = "
                f"'{self.object_list.model._meta.db_table}';"  # type: ignore
            )
            result = int(cursor.fetchone()[0])  # type: ignore
            if result < 100000:
                return super().count
            else:
                return result


class BlacklistTabular(NonrelatedTabularInline):
    model = BlacklistHistory
    extra = 0
    can_delete = False
    verbose_name_plural = "Blacklist history"
    fields = ("date", "reason", "moderator_id", "action_type")
    readonly_fields = ("date", "moderator_id", "action_type")
    classes = ("collapse",)

    def has_add_permission(  # pyright: ignore [reportIncompatibleMethodOverride]
        self, request: "HttpRequest", obj: "Player | GuildConfig"
    ) -> bool:
        return False

    def get_form_queryset(self, obj: "Player | GuildConfig"):
        if isinstance(obj, Player):
            return BlacklistHistory.objects.filter(discord_id=obj.discord_id, id_type="user")
        else:
            return BlacklistHistory.objects.filter(discord_id=obj.guild_id, id_type="guild")
