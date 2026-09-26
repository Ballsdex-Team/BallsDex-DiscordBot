from asgiref.sync import sync_to_async
from django.db import models
from django.db.models import F, Q

from bd_models.models import Ball, BallInstance, Player, Special

HOTEL_PLAYER_DISCORD_ID = 0


class AuctionSettings(models.Model):
    """
    Bot-wide tuning for the Hotel de Vente. Role IDs live on AuctionGuildConfig instead,
    since a Discord role only means something inside one specific server.
    """

    base_price = models.PositiveBigIntegerField(
        default=70000,
        help_text="Reference price used by the pricing formula. Kept for parity with the original "
        "pricing tool this formula was ported from.",
    )
    min_price = models.PositiveBigIntegerField(
        default=200, help_text="Floor applied to the computed price of any card (the most common cards)."
    )
    max_price = models.PositiveBigIntegerField(
        default=300000, help_text="Cap applied to the computed price of any card (the rarest cards, T1)."
    )
    excluded_rarity = models.FloatField(
        default=0.0,
        help_text="Cards with this exact rarity value can never be sold to the Hotel or listed for auction.",
    )
    max_shop_rarity = models.FloatField(
        null=True,
        blank=True,
        help_text="If set, only cards with a rarity between excluded_rarity and this value show up in Buggy's "
        "resale shop (e.g. setting 50 means the shop only lists cards with rarity between 0 and 50). Buggy still "
        "buys every non-special card directly regardless of this setting — this only limits what he resells. "
        "Leave blank for no limit.",
    )

    direct_sale_daily_limit = models.PositiveIntegerField(
        default=10, help_text="Maximum number of cards a player can sell directly to the Hotel per day."
    )
    max_active_listings = models.PositiveIntegerField(
        default=5, help_text="Maximum number of cards a player can have listed for auction at once."
    )
    resale_markup_percent = models.PositiveIntegerField(
        default=10, help_text="Markup applied when the Hotel relists a card it bought directly from a player."
    )

    min_listing_minutes = models.PositiveIntegerField(
        default=60, help_text="Minimum duration a player can choose when listing a card for auction, in minutes."
    )
    max_listing_minutes = models.PositiveIntegerField(
        default=4320, help_text="Maximum duration a player can choose when listing a card for auction, in minutes."
    )

    giveaway_interval_hours = models.PositiveIntegerField(
        default=12, help_text="How often the Hotel raffles off one of its unsold cards, per server."
    )
    giveaway_activity_window_hours = models.PositiveIntegerField(
        default=24, help_text="A player must have used a bot command within this window to be eligible to win."
    )
    giveaway_server_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Restrict giveaways to this server: only players active here can win, and the announcement is "
        "posted here. Leave empty to draw from players across every server the bot is in.",
    )

    shop_listing_hours = models.PositiveIntegerField(
        default=72,
        help_text="How long a card stays in Buggy's resale shop before it expires. Unsold cards are deleted "
        "for good when this runs out, not held back for the giveaway.",
    )

    featured_extension_window_minutes = models.PositiveIntegerField(
        default=10,
        help_text="A bid placed on a featured auction when less than this many minutes remain extends the "
        "auction. Set to 0 to disable extensions.",
    )
    featured_extension_minutes = models.PositiveIntegerField(
        default=10,
        help_text="How many minutes are added to a featured auction when a last-minute bid comes in. There is no "
        "limit, every last-minute bid extends it again.",
    )
    excluded_balls = models.ManyToManyField(
        Ball,
        blank=True,
        related_name="auction_excluded",
        help_text="Treasures that can never be sold to Buggy or listed for auction, regardless of rarity "
        "(e.g. utility/token balls).",
    )

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    async def aload(cls):
        return await sync_to_async(cls.load)()

    class Meta:
        managed = True
        db_table = "auctionsettings"
        constraints = [
            models.CheckConstraint(
                condition=Q(min_price__lte=F("max_price")), name="auctionsettings_price_min_lte_max"
            ),
            models.CheckConstraint(
                condition=Q(min_listing_minutes__lte=F("max_listing_minutes")),
                name="auctionsettings_listing_minutes_min_lte_max",
            ),
        ]

    def __str__(self) -> str:
        return "Auction House Settings"


class AuctionGuildConfig(models.Model):
    """Per-server configuration, since role IDs and the Hotel's stock are server-scoped."""

    server_id = models.BigIntegerField(unique=True, help_text="Discord server ID this configuration applies to.")
    notification_channel_id = models.BigIntegerField(
        null=True, blank=True, help_text="Channel where sale notifications (accepted offers) are posted."
    )

    class Meta:
        managed = True
        db_table = "auctionguildconfig"

    def __str__(self) -> str:
        return f"Guild config for {self.server_id}"


class AuctionBoosterRole(models.Model):
    """
    A role that grants a booster discount/bonus on Hotel transactions. Multiple roles can be
    configured per server, each with its own percentages (e.g. tiered supporter roles).
    """

    server_id = models.BigIntegerField(help_text="Discord server ID this role applies to.")
    role_id = models.BigIntegerField(help_text="Role ID granting this booster tier.")
    buy_discount_percent = models.PositiveIntegerField(
        default=5, help_text="Discount this role gets when buying from the Hotel's resale shop."
    )
    sell_bonus_percent = models.PositiveIntegerField(
        default=5, help_text="Bonus this role gets when selling directly to the Hotel."
    )

    class Meta:
        managed = True
        db_table = "auctionboosterrole"
        unique_together = (("server_id", "role_id"),)
        indexes = (models.Index(fields=("server_id",)),)

    def __str__(self) -> str:
        return (
            f"Booster role {self.role_id} in {self.server_id} "
            f"(+{self.sell_bonus_percent}%/-{self.buy_discount_percent}%)"
        )


class SpecialPriceModifier(models.Model):
    special = models.OneToOneField(Special, on_delete=models.CASCADE, related_name="auction_price_modifier")
    special_id: int
    percent = models.IntegerField(default=0, help_text="Price bonus/malus for this special, in percent.")

    class Meta:
        managed = True
        db_table = "auctionspecialpricemodifier"

    def __str__(self) -> str:
        return f"{self.special} ({self.percent:+d}%)"


class StatBonusModifier(models.Model):
    value = models.IntegerField(unique=True, help_text="Average of a card's attack and health bonus.")
    percent = models.IntegerField(default=0, help_text="Price bonus/malus applied for this stat average, in percent.")

    class Meta:
        managed = True
        db_table = "auctionstatbonusmodifier"
        ordering = ["value"]
        constraints = [
            models.CheckConstraint(
                condition=Q(value__gte=-40) & Q(value__lte=40), name="auctionstatbonusmodifier_range"
            )
        ]

    def __str__(self) -> str:
        return f"{self.value:+d} ({self.percent:+d}%)"


class AuctionListing(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SOLD = "sold", "Sold"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    # Deliberately a plain FK, not a OneToOne: expired/cancelled/sold listings are kept as history,
    # and a treasure that came back unsold must be listable again. Only one *active* listing per
    # treasure is allowed, which the partial unique constraint below enforces at the DB level.
    instance = models.ForeignKey(BallInstance, on_delete=models.CASCADE, related_name="auction_listings")
    seller = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="auction_listings")
    server_id = models.BigIntegerField()
    asking_price = models.PositiveBigIntegerField()
    duration_minutes = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    offers: models.QuerySet["AuctionOffer"]

    class Meta:
        managed = True
        db_table = "auctionlisting"
        indexes = (
            models.Index(fields=("server_id", "status")),
            models.Index(fields=("seller", "status")),
            models.Index(fields=("status", "expires_at")),
        )
        constraints = [
            models.UniqueConstraint(
                fields=("instance",), condition=Q(status="active"), name="auctionlisting_one_active_per_instance"
            )
        ]

    def __str__(self) -> str:
        return f"Listing #{self.pk} ({self.status})"


class AuctionOffer(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        CANCELLED = "cancelled", "Cancelled"
        REJECTED = "rejected", "Rejected"
        REFUNDED = "refunded", "Refunded"

    listing = models.ForeignKey(AuctionListing, on_delete=models.CASCADE, related_name="offers")
    buyer = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="auction_offers")
    amount = models.PositiveBigIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "auctionoffer"
        indexes = (models.Index(fields=("listing", "status")), models.Index(fields=("buyer", "status")))

    def __str__(self) -> str:
        return f"Offer #{self.pk} on listing #{self.listing_id} ({self.status})"


class HotelStock(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        SOLD = "sold", "Sold"
        GIVEN_AWAY = "given_away", "Given away"

    # Plain FK for the same reason as AuctionListing.instance: sold/given-away rows are kept as
    # history, and a treasure that left Buggy's shop can be sold back to him later.
    instance = models.ForeignKey(BallInstance, on_delete=models.CASCADE, related_name="hotel_stocks")
    server_id = models.BigIntegerField()
    buyout_price = models.PositiveBigIntegerField(help_text="What the Hotel paid the original seller.")
    resale_price = models.PositiveBigIntegerField(help_text="Price the Hotel resells this card for.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    acquired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "auctionhotelstock"
        indexes = (models.Index(fields=("server_id", "status")),)
        constraints = [
            models.UniqueConstraint(
                fields=("instance",),
                condition=Q(status="available"),
                name="auctionhotelstock_one_available_per_instance",
            )
        ]

    def __str__(self) -> str:
        return f"Hotel stock #{self.pk} ({self.status})"


class DirectSaleRecord(models.Model):
    """
    One row per direct sale to Buggy. Replaces the old aggregate daily counter — the daily
    limit is now a global (all-servers) count query against this table, and admins can click
    into a record to see exactly what was sold, by whom, where, and for how much.
    """

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="auction_direct_sales")
    server_id = models.BigIntegerField(help_text="Server the /sell command was used in.")
    instance_id = models.PositiveBigIntegerField(
        help_text="ID of the treasure instance sold, for reference even after it moves on."
    )
    ball_name = models.CharField(max_length=64, help_text="Name of the treasure sold (snapshot, in case it changes).")
    special_name = models.CharField(
        max_length=64, blank=True, null=True, help_text="Special the treasure had, if any (snapshot)."
    )
    attack_bonus = models.IntegerField(default=0, help_text="Attack stat bonus at the time of sale (snapshot).")
    health_bonus = models.IntegerField(default=0, help_text="Health stat bonus at the time of sale (snapshot).")
    price = models.PositiveBigIntegerField(help_text="What Buggy paid for it.")
    sold_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "auctiondirectsalerecord"
        indexes = (models.Index(fields=("player", "sold_at")),)

    def __str__(self) -> str:
        return f"{self.player} sold {self.ball_name} #{self.instance_id:0X} for {self.price} ({self.server_id})"


class ServerActivity(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="auction_activity")
    server_id = models.BigIntegerField()
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = "auctionserveractivity"
        unique_together = (("player", "server_id"),)
        indexes = (models.Index(fields=("server_id", "last_seen")),)

    def __str__(self) -> str:
        return f"{self.player} last seen {self.last_seen} in {self.server_id}"


class GiveawayLog(models.Model):
    server_id = models.BigIntegerField()
    winner = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="auction_giveaway_wins")
    instance = models.ForeignKey(
        BallInstance, on_delete=models.SET_NULL, null=True, blank=True, related_name="auction_giveaway_logs"
    )
    drawn_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "auctiongiveawaylog"
        indexes = (models.Index(fields=("server_id", "drawn_at")),)

    def __str__(self) -> str:
        return f"Giveaway in {self.server_id} won by {self.winner} at {self.drawn_at}"


class AuctionAdminRole(models.Model):
    """Role(s) allowed to create Featured Auctions in a given server."""

    server_id = models.BigIntegerField(help_text="Discord server ID this role applies to.")
    role_id = models.BigIntegerField(help_text="Role ID allowed to create Featured Auctions.")

    class Meta:
        managed = True
        db_table = "auctionadminrole"
        unique_together = (("server_id", "role_id"),)
        indexes = (models.Index(fields=("server_id",)),)

    def __str__(self) -> str:
        return f"Featured auction admin role {self.role_id} in {self.server_id}"


class AuctionBidBlacklist(models.Model):
    """A specific Discord account blocked from bidding anywhere in the auction house."""

    discord_id = models.BigIntegerField(unique=True)
    reason = models.TextField(blank=True, null=True, default=None)

    class Meta:
        managed = True
        db_table = "auctionbidblacklist"

    def __str__(self) -> str:
        return f"Blacklisted bidder {self.discord_id}"


class AuctionBidBlacklistRole(models.Model):
    """A role, in a given server, blocked from bidding anywhere in the auction house."""

    server_id = models.BigIntegerField(help_text="Discord server ID this role applies to.")
    role_id = models.BigIntegerField(help_text="Role ID blocked from bidding.")

    class Meta:
        managed = True
        db_table = "auctionbidblacklistrole"
        unique_together = (("server_id", "role_id"),)
        indexes = (models.Index(fields=("server_id",)),)

    def __str__(self) -> str:
        return f"Blacklisted bidder role {self.role_id} in {self.server_id}"


class FeaturedAuction(models.Model):
    """
    An admin/mod-curated auction, distinct from regular player listings: bids are public
    (bidder visible), there's no seller accept/reject step — the highest bid at expiry wins
    automatically — and it can bundle several treasures into one auction.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SOLD = "sold", "Sold"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED_UNSOLD = "expired_unsold", "Expired unsold"

    title = models.CharField(max_length=100)
    server_id = models.BigIntegerField(help_text="Server this auction was created in.")
    channel_id = models.BigIntegerField(help_text="Channel the live embed is posted in.")
    message_id = models.BigIntegerField(null=True, blank=True, help_text="Message ID of the live embed.")
    creator = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="featured_auctions_created")
    min_bid_increment = models.PositiveBigIntegerField(default=1)
    starting_bid = models.PositiveBigIntegerField()
    current_bid = models.PositiveBigIntegerField(null=True, blank=True)
    current_bidder = models.ForeignKey(
        Player, on_delete=models.SET_NULL, null=True, blank=True, related_name="featured_auctions_leading"
    )
    bid_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    items: models.QuerySet["FeaturedAuctionItem"]
    bids: models.QuerySet["FeaturedAuctionBid"]

    class Meta:
        managed = True
        db_table = "auctionfeatured"
        indexes = (models.Index(fields=("status", "expires_at")),)

    def __str__(self) -> str:
        return f"Featured auction #{self.pk} — {self.title} ({self.status})"


class FeaturedAuctionItem(models.Model):
    auction = models.ForeignKey(FeaturedAuction, on_delete=models.CASCADE, related_name="items")
    # Plain FK for the same reason as AuctionListing.instance: closed auctions are kept as history,
    # so a treasure can appear in a later auction. "Only one live commitment per treasure" can't be a
    # partial constraint here (the status lives on the parent auction), so it's enforced in
    # services.is_already_committed instead.
    instance = models.ForeignKey(BallInstance, on_delete=models.CASCADE, related_name="featured_auction_items")

    class Meta:
        managed = True
        db_table = "auctionfeatureditem"

    def __str__(self) -> str:
        return f"Item in featured auction #{self.auction_id}"


class FeaturedAuctionBid(models.Model):
    auction = models.ForeignKey(FeaturedAuction, on_delete=models.CASCADE, related_name="bids")
    bidder = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="featured_auction_bids")
    amount = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "auctionfeaturedbid"
        indexes = (models.Index(fields=("auction", "created_at")),)

    def __str__(self) -> str:
        return f"{self.bidder} bid {self.amount} on featured auction #{self.auction_id}"


def get_hotel_player_sync() -> Player:
    obj, _ = Player.objects.get_or_create(discord_id=HOTEL_PLAYER_DISCORD_ID)
    return obj


async def get_hotel_player() -> Player:
    return await sync_to_async(get_hotel_player_sync)()
