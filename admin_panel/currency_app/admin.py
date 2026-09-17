from django.contrib import admin, messages
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from .models import BerryTransaction, CurrencySettings, DailyBonusRole, DailyBonusServer, Item, ItemBall


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    autocomplete_fields = ("special",)
    save_on_top = True
    fieldsets = [
        (None, {"fields": ["name", "description", "prize"]}),
        (
            "Shop display",
            {
                "description": "Reorder the packs directly from the list by editing their position.",
                "fields": ["section", "position"],
            },
        ),
        ("Configure Reward", {"fields": ["minimum_rarity", "maximum_rarity", "special"]}),
    ]
    list_display = ("name", "section", "position", "prize", "minimum_rarity", "maximum_rarity")
    list_editable = ("section", "position", "prize", "minimum_rarity", "maximum_rarity")
    list_filter = ("section", "created_at", "special")
    ordering = ["section", "position", "prize"]
    list_per_page = 100

    search_fields = ("name",)


@admin.register(ItemBall)
class ItemBallAdmin(admin.ModelAdmin):
    list_display = ("item_name", "ball_name")

    @admin.display(description="Name of Item")
    def item_name(self, obj: ItemBall):
        return obj.item.name

    @admin.display(description="Name of Ball")
    def ball_name(self, obj: ItemBall):
        return obj.ball.country


@admin.register(CurrencySettings)
class CurrencySettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Spawn", {"fields": ["spawn_chance", "spawn_amount"]}),
        (
            "Daily streak rewards",
            {
                "fields": [
                    "base_daily_amount",
                    "day1_reward",
                    "day2_reward",
                    "day3_reward",
                    "day4_reward",
                    "day5_reward",
                    "day6_reward",
                    "day7_reward",
                    "streak_grace_hours",
                ]
            },
        ),
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return super().has_add_permission(request) and CurrencySettings.objects.first() is None

    def has_delete_permission(self, request: HttpRequest, obj: CurrencySettings | None = None) -> bool:
        return False


class DailyBonusRoleInline(admin.TabularInline):
    model = DailyBonusRole
    extra = 1


@admin.register(DailyBonusServer)
class DailyBonusServerAdmin(admin.ModelAdmin):
    list_display = ("server_id",)
    search_fields = ("server_id",)
    inlines = [DailyBonusRoleInline]


@admin.register(BerryTransaction)
class BerryTransactionAdmin(admin.ModelAdmin):
    """
    Read-only history of every berry movement. Rows are written by the bot, never here —
    editing them by hand would defeat the point of having an audit trail.
    """

    list_display = ("created_at", "player_link", "signed_amount", "balance_after", "reason", "description", "server_id")
    list_filter = ("reason", "created_at")
    search_fields = ("player__discord_id", "description")
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    list_select_related = ("player",)
    list_per_page = 50
    actions = ["audit_balances"]

    @admin.display(description="Player", ordering="player__discord_id")
    def player_link(self, obj: BerryTransaction):
        """Links to this player's own history — the per-player view."""
        url = reverse("admin:currency_app_berrytransaction_changelist")
        return format_html('<a href="{}?q={}">{}</a>', url, obj.player.discord_id, obj.player)

    @admin.display(description="Amount", ordering="amount")
    def signed_amount(self, obj: BerryTransaction):
        color = "green" if obj.amount >= 0 else "crimson"
        # format_html turns its arguments into strings before formatting them, so the number
        # has to be rendered here rather than through a numeric format spec in the template
        return format_html('<span style="color: {}">{}</span>', color, f"{obj.amount:+,}")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: BerryTransaction | None = None) -> bool:
        return False

    @admin.action(description="Audit berry history of the selected players")
    def audit_balances(self, request: HttpRequest, queryset):
        """
        Replays every ledger row of each selected player, in order, and reports any break.

        This deliberately ignores the current filters and re-reads the player's full history:
        a check against a filtered subset would report gaps that aren't real. Two things are
        verified — that each row's `balance_after` equals the previous one plus the movement,
        and that the last row matches the balance the player actually has now.
        """
        player_ids = set(queryset.values_list("player_id", flat=True))
        for player_id in player_ids:
            rows = list(
                BerryTransaction.objects.filter(player_id=player_id)
                .select_related("player")
                .order_by("created_at", "pk")
            )
            if not rows:
                continue
            player = rows[0].player
            gaps = []
            previous = None
            for row in rows:
                if previous is not None and row.balance_after != previous + row.amount:
                    gaps.append(
                        f"#{row.pk} on {row.created_at:%Y-%m-%d %H:%M}: expected "
                        f"{previous + row.amount:,}, recorded {row.balance_after:,}"
                    )
                previous = row.balance_after

            if gaps:
                self.message_user(
                    request,
                    f"{player}: {len(gaps)} unexplained change(s) — berries moved outside the ledger. "
                    + "; ".join(gaps[:5])
                    + ("; ..." if len(gaps) > 5 else ""),
                    level=messages.ERROR,
                )
            if rows[-1].balance_after != player.money:
                self.message_user(
                    request,
                    f"{player}: current balance is {player.money:,} but the ledger ends at "
                    f"{rows[-1].balance_after:,}.",
                    level=messages.ERROR,
                )
            elif not gaps:
                self.message_user(
                    request, f"{player}: {len(rows)} movement(s), history is consistent.", level=messages.SUCCESS
                )
