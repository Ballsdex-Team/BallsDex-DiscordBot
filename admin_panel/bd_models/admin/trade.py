import itertools
import re
from typing import TYPE_CHECKING, Any

from django.contrib import admin, messages
from django.db.models import Prefetch, Q

from ..models import BallInstance, Player, Trade, TradeObject

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest, HttpResponse

DUAL_ID_RE = re.compile(r"^[0-9]{17,20} [0-9]{17,20}$")


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    fields = ("player1", "player2", "date")
    list_display = ("__str__", "player1", "player1_items", "player2", "player2_items")
    readonly_fields = ("date",)
    autocomplete_fields = ("player1", "player2")

    search_help_text = (
        "Search by hexadecimal ID of a trade, Discord ID of a player, "
        "or two Discord IDs separated by a space for further filtering."
    )
    search_fields = ("id",)  # field is ignored, but required for the text area to show up
    show_full_result_count = False

    def get_search_results(
        self, request: "HttpRequest", queryset: "QuerySet[BallInstance]", search_term: str
    ) -> "tuple[QuerySet[BallInstance], bool]":
        if not search_term:
            return super().get_search_results(request, queryset, search_term)  # type: ignore
        if search_term.isdigit() and 17 <= len(search_term) <= 20:
            try:
                player = Player.objects.get(discord_id=int(search_term))
            except Player.DoesNotExist:
                messages.error(request, "Player does not exist in the database.")
                return queryset.none(), False
            return queryset.filter(Q(player1=player) | Q(player2=player)), False
        elif DUAL_ID_RE.match(search_term.strip()):
            id1, id2 = search_term.strip().split(" ")
            try:
                player1 = Player.objects.get(discord_id=int(id1))
            except Player.DoesNotExist:
                messages.error(request, f"First player ({id1}) does not exist")
                return queryset.none(), False
            try:
                player2 = Player.objects.get(discord_id=int(id2))
            except Player.DoesNotExist:
                messages.error(request, f"Second player ({id2}) does not exist")
                return queryset.none(), False
            return (
                queryset.filter(
                    Q(player1=player1, player2=player2) | Q(player2=player1, player1=player2)
                ),
                False,
            )
        try:
            return queryset.filter(id=int(search_term, 16)), False
        except ValueError:
            messages.error(request, "Invalid search query")
            return queryset.none(), False

    def get_queryset(self, request: "HttpRequest") -> "QuerySet[Trade]":
        qs: "QuerySet[Trade]" = super().get_queryset(request)
        return qs.prefetch_related(
            "player1",
            "player2",
            Prefetch(
                "tradeobject_set", queryset=TradeObject.objects.prefetch_related("ballinstance")
            ),
        )

    # It is important to use .all() and manually filter in python rather than using .filter.count
    # since the property is already prefetched and cached. Using .filter forces a new query
    def player1_items(self, obj: Trade):
        return len([None for x in obj.tradeobject_set.all() if x.player_id == obj.player1_id])

    def player2_items(self, obj: Trade):
        return len([None for x in obj.tradeobject_set.all() if x.player_id == obj.player2_id])

    # The Trade model object is needed in `change_view`, but the admin does not provide it yet
    # at this time. To avoid making the same query twice and slowing down the page loading,
    # the model is cached here
    def get_object(self, request: "HttpRequest", object_id: str, from_field: None = None) -> Trade:
        if not hasattr(request, "object"):
            request.object = self.get_queryset(request).get(id=object_id)  # type: ignore
        return request.object  # type: ignore

    # This adds extra context to the template, needed for the display of TradeObject models
    def change_view(
        self,
        request: "HttpRequest",
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> "HttpResponse":
        obj = self.get_object(request, object_id)

        # force queryset evaluation now to avoid double evaluation (with the len below)
        objects = list(obj.tradeobject_set.all())
        player1_objects = [x for x in objects if x.player_id == obj.player1_id]
        player2_objects = [x for x in objects if x.player_id == obj.player2_id]
        objects = itertools.zip_longest(player1_objects, player2_objects)

        extra_context = extra_context or {}
        extra_context["player1"] = obj.player1
        extra_context["player2"] = obj.player2
        extra_context["trade_objects"] = objects
        extra_context["player1_len"] = len(player1_objects)
        extra_context["player2_len"] = len(player2_objects)
        return super().change_view(request, object_id, form_url, extra_context)
