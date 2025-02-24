from typing import TYPE_CHECKING, Any

from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin, messages
from django.db.models import Prefetch

from ..models import BallInstance, Player, Trade, TradeObject
from ..utils import ApproxCountPaginator

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest, HttpResponse


class SpecialFilter(AutocompleteFilter):
    title = "special"
    field_name = "special"


class BallFilter(AutocompleteFilter):
    title = "countryball"
    field_name = "ball"


class PlayerFilter(AutocompleteFilter):
    title = "player"
    field_name = "player"


@admin.register(BallInstance)
class BallInstanceAdmin(admin.ModelAdmin):
    autocomplete_fields = ("player", "trade_player", "ball", "special")
    save_on_top = True
    fieldsets = [
        (None, {"fields": ("ball", "health_bonus", "attack_bonus", "special")}),
        ("Ownership", {"fields": ("player", "favorite", "catch_date", "trade_player")}),
        (
            "Advanced",
            {
                "classes": ("collapse",),
                "fields": ("tradeable", "server_id", "spawned_time", "locked", "extra_data"),
            },
        ),
    ]

    list_display = ("description", "player", "server_id", "catch_time")
    list_select_related = ("ball", "special", "player")
    list_filter = (SpecialFilter, BallFilter, PlayerFilter, "tradeable", "favorite")
    show_facets = admin.ShowFacets.NEVER  # hide filtered counts (considerable slowdown)
    show_full_result_count = False
    paginator = ApproxCountPaginator

    search_help_text = "Search by hexadecimal ID or Discord ID"
    search_fields = ("id",)  # field is ignored, but required for the text area to show up

    def get_search_results(
        self, request: "HttpRequest", queryset: "QuerySet[BallInstance]", search_term: str
    ) -> "tuple[QuerySet[BallInstance], bool]":
        if not search_term:
            return super().get_search_results(request, queryset, search_term)  # type: ignore
        if search_term.isdigit() and 17 <= len(search_term) <= 22:
            try:
                player = Player.objects.get(discord_id=int(search_term))
            except Player.DoesNotExist:
                return queryset.none(), False
            return queryset.filter(player=player), False
        try:
            return queryset.filter(id=int(search_term, 16)), False
        except ValueError:
            messages.error(request, "Invalid search query")
            return queryset.none(), False

    def change_view(
        self,
        request: "HttpRequest",
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> "HttpResponse":
        obj = BallInstance.objects.prefetch_related("player").get(id=object_id)

        def _get_trades():
            trade_ids = TradeObject.objects.filter(ballinstance=obj).values_list(
                "trade_id", flat=True
            )
            for trade in (
                Trade.objects.filter(id__in=trade_ids)
                .order_by("-date")
                .prefetch_related(
                    "player1",
                    "player2",
                    Prefetch(
                        "tradeobject_set",
                        queryset=TradeObject.objects.prefetch_related(
                            "ballinstance", "ballinstance__ball", "player"
                        ),
                    ),
                )
            ):
                player1_proposal = [
                    x for x in trade.tradeobject_set.all() if x.player_id == trade.player1_id
                ]
                player2_proposal = [
                    x for x in trade.tradeobject_set.all() if x.player_id == trade.player2_id
                ]
                yield {
                    "model": trade,
                    "proposals": (player1_proposal, player2_proposal),
                }

        extra_context = extra_context or {}
        extra_context["trades"] = list(_get_trades())
        return super().change_view(request, object_id, form_url, extra_context)
