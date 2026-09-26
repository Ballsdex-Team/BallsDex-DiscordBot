from typing import TYPE_CHECKING

from django.contrib import admin

from bd_models.models import Special

from .models import (
    AuctionAdminRole,
    AuctionBidBlacklist,
    AuctionBidBlacklistRole,
    AuctionBoosterRole,
    AuctionGuildConfig,
    AuctionListing,
    AuctionOffer,
    AuctionSettings,
    DirectSaleRecord,
    FeaturedAuction,
    FeaturedAuctionBid,
    FeaturedAuctionItem,
    GiveawayLog,
    HotelStock,
    ServerActivity,
    SpecialPriceModifier,
    StatBonusModifier,
)

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(AuctionSettings)
class AuctionSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Pricing", {"fields": ["base_price", "min_price", "max_price", "excluded_rarity", "excluded_balls"]}),
        (
            "Direct sales & listings",
            {"fields": ["direct_sale_daily_limit", "max_active_listings"]},
        ),
        ("Resale shop", {"fields": ["resale_markup_percent", "max_shop_rarity", "shop_listing_hours"]}),
        ("Listing duration", {"fields": ["min_listing_minutes", "max_listing_minutes"]}),
        (
            "Featured auctions",
            {
                "description": "Last-minute bids extend featured auctions, so nobody can snipe them right before "
                "they end.",
                "fields": ["featured_extension_window_minutes", "featured_extension_minutes"],
            },
        ),
        (
            "Giveaway",
            {"fields": ["giveaway_interval_hours", "giveaway_activity_window_hours", "giveaway_server_id"]},
        ),
    ]
    filter_horizontal = ("excluded_balls",)

    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and AuctionSettings.objects.first() is None

    def has_delete_permission(self, request: "HttpRequest", obj: AuctionSettings | None = None) -> bool:
        return False


@admin.register(AuctionGuildConfig)
class AuctionGuildConfigAdmin(admin.ModelAdmin):
    list_display = ("server_id", "notification_channel_id")
    search_fields = ("server_id",)


@admin.register(AuctionBoosterRole)
class AuctionBoosterRoleAdmin(admin.ModelAdmin):
    list_display = ("server_id", "role_id", "buy_discount_percent", "sell_bonus_percent")
    list_editable = ("buy_discount_percent", "sell_bonus_percent")
    list_filter = ("server_id",)
    search_fields = ("server_id", "role_id")


@admin.register(AuctionAdminRole)
class AuctionAdminRoleAdmin(admin.ModelAdmin):
    list_display = ("server_id", "role_id")
    list_filter = ("server_id",)
    search_fields = ("server_id", "role_id")


@admin.register(AuctionBidBlacklist)
class AuctionBidBlacklistAdmin(admin.ModelAdmin):
    list_display = ("discord_id", "reason")
    search_fields = ("discord_id",)


@admin.register(AuctionBidBlacklistRole)
class AuctionBidBlacklistRoleAdmin(admin.ModelAdmin):
    list_display = ("server_id", "role_id")
    list_filter = ("server_id",)
    search_fields = ("server_id", "role_id")


@admin.register(SpecialPriceModifier)
class SpecialPriceModifierAdmin(admin.ModelAdmin):
    list_display = ("special", "percent")
    list_editable = ("percent",)
    ordering = ["special__name"]

    def changelist_view(self, request: "HttpRequest", extra_context=None):
        configured_ids = set(SpecialPriceModifier.objects.values_list("special_id", flat=True))
        missing = Special.objects.exclude(id__in=configured_ids)
        SpecialPriceModifier.objects.bulk_create(
            [SpecialPriceModifier(special=special, percent=0) for special in missing]
        )
        return super().changelist_view(request, extra_context)


@admin.register(StatBonusModifier)
class StatBonusModifierAdmin(admin.ModelAdmin):
    list_display = ("value", "percent")
    list_editable = ("percent",)
    list_per_page = 100
    ordering = ["value"]

    def has_add_permission(self, request: "HttpRequest") -> bool:
        return False

    def has_delete_permission(self, request: "HttpRequest", obj: StatBonusModifier | None = None) -> bool:
        return False


@admin.register(AuctionListing)
class AuctionListingAdmin(admin.ModelAdmin):
    list_display = ("id", "seller", "server_id", "asking_price", "status", "created_at", "expires_at")
    list_filter = ("status", "server_id")
    search_fields = ("seller__discord_id",)
    autocomplete_fields = ("seller", "instance")


@admin.register(AuctionOffer)
class AuctionOfferAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "buyer", "amount", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("buyer__discord_id",)
    autocomplete_fields = ("buyer", "listing")


@admin.register(HotelStock)
class HotelStockAdmin(admin.ModelAdmin):
    list_display = ("id", "server_id", "buyout_price", "resale_price", "status", "acquired_at")
    list_filter = ("status", "server_id")
    autocomplete_fields = ("instance",)


@admin.register(DirectSaleRecord)
class DirectSaleRecordAdmin(admin.ModelAdmin):
    list_display = (
        "player",
        "server_id",
        "sold_at",
        "instance_id",
        "ball_name",
        "special_name",
        "attack_bonus",
        "health_bonus",
        "price",
    )
    list_filter = ("server_id", "sold_at")
    search_fields = ("player__discord_id", "ball_name", "instance_id")
    ordering = ["-sold_at"]


@admin.register(ServerActivity)
class ServerActivityAdmin(admin.ModelAdmin):
    list_display = ("player", "server_id", "last_seen")
    list_filter = ("server_id",)
    search_fields = ("player__discord_id",)


@admin.register(GiveawayLog)
class GiveawayLogAdmin(admin.ModelAdmin):
    list_display = ("server_id", "winner", "instance", "drawn_at")
    list_filter = ("server_id",)
    search_fields = ("winner__discord_id",)


class FeaturedAuctionItemInline(admin.TabularInline):
    model = FeaturedAuctionItem
    extra = 0
    autocomplete_fields = ("instance",)


class FeaturedAuctionBidInline(admin.TabularInline):
    model = FeaturedAuctionBid
    extra = 0
    autocomplete_fields = ("bidder",)
    readonly_fields = ("bidder", "amount", "created_at")

    def has_add_permission(self, request: "HttpRequest", obj=None) -> bool:
        return False


@admin.register(FeaturedAuction)
class FeaturedAuctionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "server_id", "creator", "current_bid", "bid_count", "status", "expires_at")
    list_filter = ("status", "server_id")
    search_fields = ("title", "creator__discord_id")
    autocomplete_fields = ("creator", "current_bidder")
    inlines = [FeaturedAuctionItemInline, FeaturedAuctionBidInline]
