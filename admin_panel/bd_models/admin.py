import itertools
from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.contrib.messages import SUCCESS
from django.db.models import Prefetch, Q
from django.forms import Textarea
from django.utils.safestring import mark_safe
from nonrelated_inlines.admin import NonrelatedTabularInline

from .models import (
    Ball,
    BallInstance,
    BlacklistedID,
    BlacklistHistory,
    Economy,
    Player,
    Regime,
    Special,
    Trade,
    TradeObject,
)
from .utils import ApproxCountPaginator, transform_media

if TYPE_CHECKING:
    from django.db.models import Field, QuerySet
    from django.http import HttpRequest, HttpResponse


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


@admin.register(Regime)
class RegimeAdmin(admin.ModelAdmin):
    list_display = ("name", "background_image", "pk")
    search_fields = ("name",)

    @admin.display()
    def background_image(self, obj: Regime):
        return mark_safe(
            f'<img src="/media/{transform_media(str(obj.background))}" height=60px />'
        )


@admin.register(Economy)
class EconomyAdmin(admin.ModelAdmin):
    list_display = ("name", "icon_image", "pk")
    search_fields = ("name",)

    @admin.display()
    def icon_image(self, obj: Economy):
        return mark_safe(f'<img src="/media/{transform_media(str(obj.icon))}" height=30px />')


@admin.register(Ball)
class BallAdmin(admin.ModelAdmin):
    autocomplete_fields = ("regime", "economy")
    readonly_fields = ("collection_image", "spawn_image")
    save_on_top = True
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "country",
                    "health",
                    "attack",
                    "rarity",
                    "emoji_id",
                    "economy",
                    "regime",
                ],
            },
        ),
        (
            "Assets",
            {
                "description": "You must have permission from the copyright holder "
                "to use the files you're uploading!",
                "fields": [
                    "spawn_image",
                    "wild_card",
                    "collection_image",
                    "collection_card",
                    "credits",
                ],
            },
        ),
        (
            "Ability",
            {
                "description": "The ability of the countryball",
                "fields": ["capacity_name", "capacity_description"],
            },
        ),
        (
            "Advanced",
            {
                "description": "Advanced settings",
                "classes": ["collapse"],
                "fields": [
                    "enabled",
                    "tradeable",
                    "short_name",
                    "catch_names",
                    "translations",
                    "capacity_logic",
                ],
            },
        ),
    ]

    list_display = [
        "country",
        "pk",
        "emoji",
        "rarity",
        "capacity_name",
        "health",
        "attack",
        "enabled",
    ]
    list_editable = ["enabled", "rarity"]
    list_filter = ["enabled", "tradeable", "regime", "economy", "created_at"]
    ordering = ["-created_at"]

    search_fields = [
        "country",
        "capacity_name",
        "capacity_description",
        "catch_names",
        "translations",
        "credits",
    ]
    search_help_text = (
        "Search for countryball name, abilitie name/content, credits, catch names or translations"
    )

    @admin.display(description="Emoji")
    def emoji(self, obj: Ball):
        return mark_safe(
            f'<img src="https://cdn.discordapp.com/emojis/{obj.emoji_id}.png?size=40" '
            f'title="ID: {obj.emoji_id}" />'
        )

    def formfield_for_dbfield(
        self, db_field: "Field[Any, Any]", request: "HttpRequest | None", **kwargs: Any
    ) -> "Field[Any, Any] | None":
        if db_field.name == "capacity_description":
            kwargs["widget"] = Textarea()
        return super().formfield_for_dbfield(db_field, request, **kwargs)  # type: ignore


@admin.register(Special)
class SpecialAdmin(admin.ModelAdmin):
    save_on_top = True
    fieldsets = [
        (
            None,
            {
                "fields": ["name", "catch_phrase", "rarity", "emoji", "background"],
            },
        ),
        (
            "Time range",
            {
                "fields": ["start_date", "end_date"],
                "description": "An optional time range to make the event limited in time. As soon "
                "as the event is loaded in the bot's cache, it will automatically load and unload "
                "at the specified time.",
            },
        ),
        (
            "Advanced",
            {
                "fields": ["tradeable", "hidden"],
                "classes": ["collapse"],
            },
        ),
    ]

    list_display = ["name", "pk", "emoji_display", "start_date", "end_date", "rarity", "hidden"]
    list_editable = ["hidden", "rarity"]
    list_filter = ["hidden", "tradeable"]

    search_fields = ["name", "catch_phrase"]

    @admin.display(description="Emoji")
    def emoji_display(self, obj: Special):
        return (
            mark_safe(
                f'<img src="https://cdn.discordapp.com/emojis/{obj.emoji}.png?size=40" '
                f'title="ID: {obj.emoji}" />'
            )
            if obj.emoji and obj.emoji.isdigit()
            else obj.emoji
        )

    def formfield_for_dbfield(
        self, db_field: "Field[Any, Any]", request: "HttpRequest | None", **kwargs: Any
    ) -> "Field[Any, Any] | None":
        if db_field.name == "catch_phrase":
            kwargs["widget"] = Textarea()
        return super().formfield_for_dbfield(db_field, request, **kwargs)  # type: ignore


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

    list_display = ("description", "ball__country", "player", "health_bonus", "attack_bonus")
    list_select_related = ("ball", "special", "player")
    # TODO: filter by special or ball (needs extension)
    list_filter = ("tradeable", "favorite")
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


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    fields = ("player1", "player2", "date")
    list_display = ("__str__", "player1", "player1_items", "player2", "player2_items")
    readonly_fields = ("date",)
    autocomplete_fields = ("player1", "player2")

    search_help_text = "Search by hexadecimal ID or Discord ID"
    search_fields = ("id",)  # field is ignored, but required for the text area to show up
    show_full_result_count = False

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
            return queryset.filter(Q(player1=player) | Q(player2=player)), False
        try:
            return queryset.filter(id=int(search_term, 16)), False
        except ValueError:
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
