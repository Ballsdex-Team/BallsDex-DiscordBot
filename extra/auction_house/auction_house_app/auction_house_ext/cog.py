import logging
import random
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from auction_house_app import pricing, services
from currency_app.ledger import adjust_money
from currency_app.models import BerryTransaction
from auction_house_app.models import (
    AuctionGuildConfig,
    AuctionListing,
    AuctionOffer,
    AuctionSettings,
    FeaturedAuction,
    FeaturedAuctionBid,
    FeaturedAuctionItem,
    GiveawayLog,
    HotelStock,
    ServerActivity,
)
from discord import app_commands
from discord.ext import commands, tasks
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from ballsdex.core.game_events import Event, EventContext, bus
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.menus.old import FieldPageSource, Pages
from ballsdex.core.utils.transformers import BallEnabledTransform, BallInstanceTransform
from ballsdex.core.utils.utils import can_mention
from bd_models.models import BallInstance, GuildConfig, Player
from settings.models import settings
from settings.utils import format_currency

from . import views

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)

# every embed uses the color configured in the admin panel settings
AUCTION_COLOR = settings.embed_colour

SORT_CHOICES = [
    app_commands.Choice(name="Rarity", value="rarity"),
    app_commands.Choice(name="Most recent", value="recent"),
    app_commands.Choice(name="Price (low to high)", value="price_asc"),
    app_commands.Choice(name="Price (high to low)", value="price_desc"),
]
_LISTING_SORT_FIELDS = {
    "rarity": "instance__ball__rarity",
    "recent": "-created_at",
    "price_asc": "asking_price",
    "price_desc": "-asking_price",
}
_STOCK_SORT_FIELDS = {
    "rarity": "instance__ball__rarity",
    "recent": "-acquired_at",
    "price_asc": "resale_price",
    "price_desc": "-resale_price",
}

# One flavor line is picked at random for every giveaway announcement.
GIVEAWAY_FLAVOR_LINES = [
    (
        "Crocodile",
        "Congratulations, trash. Buggy just bought your silence with a shiny trinket from his little "
        "laundering operation. Smart of you to take the deal — or maybe you're just as big a fool as he is.",
    ),
    (
        "Mihawk",
        "A treasure changes hands, and silence is purchased once again. There is no honor in it — only the "
        "quiet arithmetic of men who fear the truth more than the blade.",
    ),
    (
        "Buggy",
        "AHAHAHA! The GREAT Captain Buggy the Star Clown has generously rewarded you with a treasure beyond "
        "your wildest dreams! Now — you didn't see any 'accounting irregularities' at the Auction House "
        "tonight. Understand? ...Understand?!",
    ),
]


def format_duration(minutes: int) -> str:
    """Renders a duration in minutes as "72h", "45m" or "2h30m"."""
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h{remainder:02d}m"
    if hours:
        return f"{hours}h"
    return f"{remainder}m"


class AuctionHouse(commands.GroupCog, name="Buggy's Auction House", group_name="auction"):
    """
    List treasures for player bids on Buggy's Auction House, bot-wide.
    """

    featured = app_commands.Group(name="featured", description="Curated multi-item auctions (mod/admin only).")

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    async def cog_load(self):
        self.sweep_listings.start()
        self.sweep_shop_stock.start()
        self.giveaway_draw.start()
        self.sweep_featured_auctions.start()
        await self._register_persistent_featured_views()

    def cog_unload(self):
        self.sweep_listings.cancel()
        self.sweep_shop_stock.cancel()
        self.giveaway_draw.cancel()
        self.sweep_featured_auctions.cancel()

    async def _register_persistent_featured_views(self):
        await self.bot.wait_until_ready()
        async for auction in FeaturedAuction.objects.filter(status=FeaturedAuction.Status.ACTIVE):
            if auction.message_id is not None:
                self.bot.add_view(views.FeaturedAuctionView(self, auction.id), message_id=auction.message_id)

    # -- shared helpers -----------------------------------------------------------------

    async def _get_guild_config(self, server_id: int) -> AuctionGuildConfig | None:
        return await AuctionGuildConfig.objects.filter(server_id=server_id).afirst()

    async def _resolve_announcement_channel(
        self, server_id: int, *, fallback_to_spawn: bool = False
    ) -> discord.TextChannel | discord.Thread | None:
        guild_config = await self._get_guild_config(server_id)
        channel_id = guild_config.notification_channel_id if guild_config else None
        if channel_id is None and fallback_to_spawn:
            core_config = await GuildConfig.objects.filter(guild_id=server_id).afirst()
            channel_id = core_config.spawn_channel if core_config else None
        if channel_id is None:
            return None
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                return None
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return None
        return channel

    async def notify_sale(self, listing: AuctionListing, offer: AuctionOffer):
        """Tag the buyer in the origin server's configured notification channel, if any."""
        channel = await self._resolve_announcement_channel(listing.server_id)
        if channel is None:
            return
        try:
            await channel.send(
                f"\N{PARTY POPPER} <@{offer.buyer.discord_id}> your offer of "
                f"**{format_currency(offer.amount, False, self.bot)}** was accepted for "
                f"{listing.instance.description(include_emoji=True, bot=self.bot)}!",
                allowed_mentions=await can_mention([offer.buyer]),
            )
        except discord.HTTPException:
            log.warning("Failed to send auction sale notification in channel %s", channel.id)

    async def notify_giveaway_win(self, winner: Player, instance: BallInstance, home_server_id: int | None):
        if home_server_id is None:
            return
        channel = await self._resolve_announcement_channel(home_server_id, fallback_to_spawn=True)
        if channel is None:
            return
        speaker, line = random.choice(GIVEAWAY_FLAVOR_LINES)
        embed = discord.Embed(
            title="🎪🤡 Buggy's Giveaway!",
            description=(
                f"<@{winner.discord_id}> just won "
                f"{instance.description(include_emoji=True, bot=self.bot)} from Buggy's unsold stock!\n\n"
                f"*\"{line}\"*\n— **{speaker}**"
            ),
            color=AUCTION_COLOR,
        )
        try:
            await channel.send(embed=embed, allowed_mentions=await can_mention([winner]))
        except discord.HTTPException:
            log.warning("Failed to send giveaway announcement in channel %s", channel.id)

    # -- /auction setchannel ------------------------------------------------------------------------

    @app_commands.command(name="setchannel")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    @app_commands.guild_only()
    async def set_channel(
        self, interaction: discord.Interaction["BallsDexBot"], channel: discord.TextChannel | None = None
    ):
        """
        Set the channel where Buggy's Auction House posts sale notifications for this server.

        Parameters
        ----------
        channel: discord.TextChannel
            The channel to use, current one if not specified.
        """
        if channel is None:
            if isinstance(interaction.channel, discord.TextChannel):
                channel = interaction.channel
            else:
                await interaction.response.send_message(
                    "The current channel is not a valid text channel.", ephemeral=True
                )
                return
        server_id = interaction.guild_id
        assert server_id is not None
        await AuctionGuildConfig.objects.aupdate_or_create(
            server_id=server_id, defaults={"notification_channel_id": channel.id}
        )
        await interaction.response.send_message(
            f"Sale notifications will now be posted in {channel.mention}.", ephemeral=True
        )

    # -- /auction create ------------------------------------------------------------------------

    @app_commands.command(name="create")
    @app_commands.describe(
        price="Your asking price",
        hours="How long the listing stays up, in hours (combine with minutes)",
        minutes="Extra minutes on top of the hours, for shorter auctions",
    )
    async def create_listing(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        price: app_commands.Range[int, 1],
        hours: app_commands.Range[int, 0, 72] = 0,
        minutes: app_commands.Range[int, 0, 59] = 0,
    ):
        """
        List a treasure on Buggy's Auction House. Buyers bid, you choose to accept or reject the highest.

        Parameters
        ----------
        countryball: BallInstance
            The treasure you want to list.
        price: int
            Your asking price (shown to buyers as a reference).
        hours: int
            How long the listing stays up, in hours.
        minutes: int
            Extra minutes on top of the hours, for auctions shorter than an hour.
        """
        if not countryball:
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not countryball.is_tradeable or countryball.deleted:
            await interaction.followup.send(f"This {settings.collectible_name} can't be listed.")
            return

        auction_settings, special_modifiers, stat_modifiers = await services.load_pricing_context()
        if countryball.countryball.rarity == auction_settings.excluded_rarity:
            await interaction.followup.send("This treasure's rarity can't be listed for auction.")
            return
        if await services.is_excluded_ball(countryball.ball_id, auction_settings):
            await interaction.followup.send("This treasure can't be listed for auction.")
            return
        total_minutes = hours * 60 + minutes
        if total_minutes == 0:
            await interaction.followup.send("Set a duration with `hours`, `minutes`, or both.")
            return
        if not (auction_settings.min_listing_minutes <= total_minutes <= auction_settings.max_listing_minutes):
            await interaction.followup.send(
                f"Duration must be between {format_duration(auction_settings.min_listing_minutes)} and "
                f"{format_duration(auction_settings.max_listing_minutes)}."
            )
            return
        if await countryball.is_locked():
            await interaction.followup.send(f"This {settings.collectible_name} is currently locked.")
            return
        if await services.is_already_committed(countryball):
            await interaction.followup.send("This treasure is already listed or already belongs to Buggy.")
            return

        active_count = await AuctionListing.objects.filter(
            seller=countryball.player, status=AuctionListing.Status.ACTIVE
        ).acount()
        if active_count >= auction_settings.max_active_listings:
            soonest = (
                await AuctionListing.objects.filter(seller=countryball.player, status=AuctionListing.Status.ACTIVE)
                .order_by("expires_at")
                .afirst()
            )
            hint = f" A slot frees up {discord.utils.format_dt(soonest.expires_at, 'R')}." if soonest else ""
            await interaction.followup.send(
                f"You can only have {auction_settings.max_active_listings} active listings at once.{hint} "
                "You can also free one up early with `/auction cancel`."
            )
            return

        recommended = pricing.recommended_price(countryball, auction_settings, special_modifiers, stat_modifiers)
        server_id = interaction.guild_id
        assert server_id is not None

        embed = discord.Embed(
            title="Create a listing on Buggy's Auction House",
            description=(
                f"{countryball.description(include_emoji=True, bot=self.bot)}\n\n"
                f"**Recommended price:** {format_currency(recommended, False, self.bot)}\n"
                f"**Your asking price:** {format_currency(price, False, self.bot)}\n"
                f"**Duration:** {format_duration(total_minutes)}\n\n"
                "Buyers anywhere can bid on this listing. You'll only see the highest bid, and can accept or "
                "reject it with `/auction mylistings` — you won't know who placed it unless you accept."
            ),
            color=AUCTION_COLOR,
        )
        view = ConfirmChoiceView(interaction, accept_message="Listed!", cancel_message="Listing cancelled.")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()
        if not view.value:
            return

        try:
            await services.safe_settle(self._create_listing, countryball.pk, price, total_minutes, server_id)
        except RuntimeError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        await interaction.followup.send("Your treasure has been listed on Buggy's Auction House!", ephemeral=True)

    def _create_listing(self, instance_id: int, price: int, total_minutes: int, server_id: int):
        with transaction.atomic():
            instance = BallInstance.objects.select_related("player").select_for_update().get(pk=instance_id)
            instance.locked = timezone.now()
            instance.save(update_fields=["locked"])
            AuctionListing.objects.create(
                instance=instance,
                seller=instance.player,
                server_id=server_id,
                asking_price=price,
                duration_minutes=total_minutes,
                expires_at=timezone.now() + timedelta(minutes=total_minutes),
            )
            context = EventContext(instances=[instance], price=price, server_id=server_id)
            seller_id = instance.player_id
            transaction.on_commit(
                lambda: bus.dispatch_soon(seller_id, Event.AUCTION_CREATE, context=context)
            )

    # -- /auction cancel ------------------------------------------------------------------------

    @app_commands.command(name="cancel")
    @app_commands.rename(listing_id="listing")
    async def cancel_listing(self, interaction: discord.Interaction["BallsDexBot"], listing_id: int):
        """
        Withdraw one of your own active listings early. Pending bids are refunded.

        Parameters
        ----------
        listing_id: int
            The listing you want to withdraw.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        seller, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        try:
            listing = await services.safe_settle(self._cancel_listing, listing_id, seller.pk)
        except RuntimeError as error:
            await interaction.followup.send(str(error))
            return
        await interaction.followup.send(
            f"Listing #{listing.id} cancelled — your treasure is back in your inventory.", ephemeral=True
        )

    def _cancel_listing(self, listing_id: int, seller_id: int) -> AuctionListing:
        with transaction.atomic():
            try:
                listing = AuctionListing.objects.select_related("instance").select_for_update().get(pk=listing_id)
            except AuctionListing.DoesNotExist:
                raise RuntimeError("This listing doesn't exist.")
            if listing.seller_id != seller_id:
                raise RuntimeError("This isn't your listing.")
            if listing.status != AuctionListing.Status.ACTIVE:
                raise RuntimeError("This listing is no longer active.")

            listing.status = AuctionListing.Status.CANCELLED
            listing.save(update_fields=["status"])
            listing.instance.locked = None
            listing.instance.save(update_fields=["locked"])

            pending = AuctionOffer.objects.filter(
                listing=listing, status=AuctionOffer.Status.PENDING
            ).select_related("buyer")
            for offer in pending:
                adjust_money(
                    offer.buyer,
                    offer.amount,
                    reason=BerryTransaction.Reason.AUCTION_BID_REFUND,
                    description=f"Listing #{listing.pk} withdrawn by the seller",
                    server_id=listing.server_id,
                )
                offer.status = AuctionOffer.Status.REFUNDED
                offer.save(update_fields=["status"])
            return listing

    @cancel_listing.autocomplete("listing_id")
    async def cancel_listing_autocomplete(
        self, interaction: discord.Interaction["BallsDexBot"], current: str
    ) -> list[app_commands.Choice[int]]:
        qs = AuctionListing.objects.filter(
            seller__discord_id=interaction.user.id, status=AuctionListing.Status.ACTIVE
        )
        if current:
            qs = qs.filter(instance__ball__country__icontains=current)
        qs = qs.select_related("instance").order_by("expires_at")[:25]
        return [
            app_commands.Choice(name=f"#{listing.id} {listing.instance.short_description()}", value=listing.id)
            async for listing in qs
        ]

    # -- /auction browse ------------------------------------------------------------------------

    @app_commands.command(name="browse")
    @app_commands.describe(treasure="Only show listings for this treasure", sort="How to order the results")
    @app_commands.choices(sort=SORT_CHOICES)
    async def browse(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        treasure: BallEnabledTransform | None = None,
        sort: app_commands.Choice[str] | None = None,
    ):
        """
        Browse treasures currently listed on Buggy's Auction House.

        Parameters
        ----------
        treasure: Ball
            Only show listings for this treasure.
        sort: str
            How to order the results.
        """
        await interaction.response.defer(thinking=True)
        qs = AuctionListing.objects.filter(status=AuctionListing.Status.ACTIVE).select_related(
            "instance", "instance__ball", "instance__special"
        )
        if treasure is not None:
            qs = qs.filter(instance__ball=treasure)
        order = _LISTING_SORT_FIELDS.get(sort.value if sort else "", "expires_at")
        listings = [listing async for listing in qs.order_by(order)]
        if not listings:
            await interaction.followup.send(
                "No listings match that treasure." if treasure else "No treasures are currently listed on Buggy's Auction House."
            )
            return

        top_bids = {
            row["listing_id"]: row["top"]
            async for row in AuctionOffer.objects.filter(
                listing_id__in=[listing.id for listing in listings], status=AuctionOffer.Status.PENDING
            )
            .values("listing_id")
            .annotate(top=Max("amount"))
        }

        entries = [
            (
                f"#{listing.id} — {listing.instance.description(include_emoji=True, bot=self.bot)}",
                f"Asking: {format_currency(listing.asking_price, False, self.bot)} • "
                + (
                    f"Highest bid: {format_currency(top_bids[listing.id], False, self.bot)} • "
                    if listing.id in top_bids
                    else "No bids yet • "
                )
                + f"Expires {discord.utils.format_dt(listing.expires_at, 'R')}",
            )
            for listing in listings
        ]
        source = FieldPageSource(entries, per_page=8, inline=False)
        source.embed.title = "Buggy's Auction House — Active listings"
        source.embed.colour = AUCTION_COLOR
        pages = Pages(source, interaction=interaction, compact=True)
        await pages.start()

    # -- /auction bid ------------------------------------------------------------------------

    @app_commands.command(name="bid")
    @app_commands.rename(listing_id="listing")
    async def bid(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        listing_id: int,
        amount: app_commands.Range[int, 1],
    ):
        """
        Bid on a treasure listed on Buggy's Auction House. Your coins are held until the seller decides.

        Parameters
        ----------
        listing_id: int
            The listing you want to bid on.
        amount: int
            How much you're bidding.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        if interaction.guild_id is not None and await services.is_blacklisted_bidder(
            interaction.user, interaction.guild_id
        ):
            await interaction.followup.send("You're not allowed to bid on the auction house.")
            return
        try:
            listing = await AuctionListing.objects.select_related("instance", "seller").aget(pk=listing_id)
        except AuctionListing.DoesNotExist:
            await interaction.followup.send("This listing doesn't exist.")
            return
        if listing.status != AuctionListing.Status.ACTIVE:
            await interaction.followup.send("This listing is no longer active.")
            return

        buyer, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        if listing.seller_id == buyer.pk:
            await interaction.followup.send("You can't bid on your own listing.")
            return
        if not buyer.can_afford(amount):
            await interaction.followup.send(
                f"You don't have enough {settings.currency_display_plural(self.bot)} for that bid.\n"
                f"Your balance: **{format_currency(buyer.money, False, self.bot)}** • "
                f"Bid amount: **{format_currency(amount, False, self.bot)}**"
            )
            return
        already_offered = await AuctionOffer.objects.filter(
            listing=listing, buyer=buyer, status=AuctionOffer.Status.PENDING
        ).aexists()
        if already_offered:
            await interaction.followup.send(
                "You already have a pending bid on this listing. Cancel it first with `/auction mybids` if you "
                "want to change your amount."
            )
            return

        try:
            await services.safe_settle(self._create_offer, listing.pk, buyer.pk, amount)
        except RuntimeError as error:
            await interaction.followup.send(str(error))
            return
        await interaction.followup.send(
            f"Bid of **{format_currency(amount, False, self.bot)}** submitted!", ephemeral=True
        )

    def _create_offer(self, listing_id: int, buyer_id: int, amount: int):
        with transaction.atomic():
            listing = AuctionListing.objects.select_for_update().get(pk=listing_id)
            if listing.status != AuctionListing.Status.ACTIVE:
                raise RuntimeError("This listing is no longer active.")
            buyer = Player.objects.select_for_update().get(pk=buyer_id)
            if buyer.money < amount:
                raise RuntimeError(
                    "Your balance changed and you can no longer afford this bid "
                    f"(balance: {format_currency(buyer.money, False)}, bid: {format_currency(amount, False)})."
                )
            adjust_money(
                buyer,
                -amount,
                reason=BerryTransaction.Reason.AUCTION_BID_HOLD,
                description=f"Bid on listing #{listing.pk}",
                server_id=listing.server_id,
            )
            AuctionOffer.objects.create(listing=listing, buyer=buyer, amount=amount)
            # only a bid that went through counts, and raising an existing bid is not a new one
            context = EventContext(price=amount, server_id=listing.server_id)
            transaction.on_commit(lambda: bus.dispatch_soon(buyer_id, Event.AUCTION_BID, context=context))

    @bid.autocomplete("listing_id")
    async def bid_autocomplete(
        self, interaction: discord.Interaction["BallsDexBot"], current: str
    ) -> list[app_commands.Choice[int]]:
        qs = AuctionListing.objects.filter(status=AuctionListing.Status.ACTIVE)
        if current:
            qs = qs.filter(instance__ball__country__icontains=current)
        qs = qs.select_related("instance").order_by("expires_at")[:25]
        return [
            app_commands.Choice(
                name=f"#{listing.id} {listing.instance.short_description()} — "
                f"{format_currency(listing.asking_price)}",
                value=listing.id,
            )
            async for listing in qs
        ]

    # -- /auction mybids ------------------------------------------------------------------------

    @app_commands.command(name="mybids")
    async def my_bids(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Browse your pending bids one at a time — see if you've been outbid, add to a bid, or cancel it.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        buyer, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        offers = [
            offer
            async for offer in AuctionOffer.objects.filter(buyer=buyer, status=AuctionOffer.Status.PENDING)
            .select_related("listing", "listing__instance")
            .order_by("-created_at")
        ]
        if not offers:
            await interaction.followup.send("You don't have any pending bids.")
            return

        view = views.MyBidsView(interaction, offers, self)
        embed = await view.build_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def top_pending_bid(self, listing_id: int, exclude_offer_id: int) -> int | None:
        """Highest pending bid on a listing other than `exclude_offer_id`, or None if there isn't one."""
        top = await (
            AuctionOffer.objects.filter(listing_id=listing_id, status=AuctionOffer.Status.PENDING)
            .exclude(pk=exclude_offer_id)
            .order_by("-amount", "created_at")
            .afirst()
        )
        return top.amount if top else None

    async def cancel_offer(self, offer_id: int, buyer_discord_id: int) -> AuctionOffer:
        return await services.safe_settle(self._cancel_offer, offer_id, buyer_discord_id)

    def _cancel_offer(self, offer_id: int, buyer_discord_id: int) -> AuctionOffer:
        with transaction.atomic():
            try:
                offer = AuctionOffer.objects.select_related("buyer").select_for_update().get(pk=offer_id)
            except AuctionOffer.DoesNotExist:
                raise RuntimeError("This bid no longer exists.")
            if offer.buyer.discord_id != buyer_discord_id:
                raise RuntimeError("This isn't your bid.")
            if offer.status != AuctionOffer.Status.PENDING:
                raise RuntimeError("This bid is no longer pending.")

            adjust_money(
                offer.buyer,
                offer.amount,
                reason=BerryTransaction.Reason.AUCTION_BID_REFUND,
                description=f"Cancelled own bid on listing #{offer.listing_id}",
            )
            offer.status = AuctionOffer.Status.CANCELLED
            offer.save(update_fields=["status"])
            return offer

    async def increase_offer(self, offer_id: int, buyer_discord_id: int, additional: int) -> AuctionOffer:
        return await services.safe_settle(self._increase_offer, offer_id, buyer_discord_id, additional)

    def _increase_offer(self, offer_id: int, buyer_discord_id: int, additional: int) -> AuctionOffer:
        with transaction.atomic():
            try:
                offer = (
                    AuctionOffer.objects.select_related("buyer", "listing", "listing__instance")
                    .select_for_update()
                    .get(pk=offer_id)
                )
            except AuctionOffer.DoesNotExist:
                raise RuntimeError("This bid no longer exists.")
            if offer.buyer.discord_id != buyer_discord_id:
                raise RuntimeError("This isn't your bid.")
            if offer.status != AuctionOffer.Status.PENDING:
                raise RuntimeError("This bid is no longer pending.")
            if offer.listing.status != AuctionListing.Status.ACTIVE:
                raise RuntimeError("This listing is no longer active.")

            buyer = offer.buyer
            buyer.refresh_from_db(fields=["money"])
            if buyer.money < additional:
                raise RuntimeError(
                    f"You don't have enough coins to add that much (balance: "
                    f"{format_currency(buyer.money, False)})."
                )
            adjust_money(
                buyer,
                -additional,
                reason=BerryTransaction.Reason.AUCTION_BID_HOLD,
                description=f"Raised bid on listing #{offer.listing_id}",
            )
            offer.amount = F("amount") + additional
            offer.save(update_fields=["amount"])
            # refresh only `amount` (not a full refresh_from_db): that keeps the already
            # select_related-cached `buyer`/`listing` around instead of clearing them, which
            # would otherwise force an unsafe sync DB fetch the next time this offer's
            # `.listing` is read from async code (e.g. MyBidsView.build_embed)
            offer.refresh_from_db(fields=["amount"])
            return offer

    # -- /auction mylistings ------------------------------------------------------------------------

    @app_commands.command(name="mylistings")
    async def my_listings(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        See your active listings and the highest bid on each — accept or reject it.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        seller, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        listings = [
            listing
            async for listing in AuctionListing.objects.filter(
                seller=seller, status=AuctionListing.Status.ACTIVE
            )
            .select_related("instance")
            .prefetch_related("offers")
            .order_by("expires_at")
        ]
        if not listings:
            await interaction.followup.send("You don't have any active listings.")
            return

        embed = discord.Embed(
            title="Your listings",
            description="You only ever see the highest bid on each listing — the bidder stays anonymous "
            "until you accept.",
            color=AUCTION_COLOR,
        )
        top_offers = []
        for listing in listings:
            pending = [o for o in listing.offers.all() if o.status == AuctionOffer.Status.PENDING]
            if pending:
                top = max(pending, key=lambda o: o.amount)
                top_offers.append(top)
                value = f"Highest bid: **{format_currency(top.amount, False, self.bot)}**"
            else:
                value = "No bids yet."
            embed.add_field(
                name=(
                    f"Listing #{listing.id} — {listing.instance.short_description()} "
                    f"(asking {format_currency(listing.asking_price, False, self.bot)})"
                ),
                value=value,
                inline=False,
            )

        if not top_offers:
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        view = views.ListingOffersView(interaction, top_offers, self)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def accept_offer(self, offer_id: int, seller_discord_id: int) -> tuple[AuctionListing, AuctionOffer]:
        return await services.safe_settle(self._accept_offer, offer_id, seller_discord_id)

    def _accept_offer(self, offer_id: int, seller_discord_id: int) -> tuple[AuctionListing, AuctionOffer]:
        with transaction.atomic():
            try:
                offer = (
                    AuctionOffer.objects.select_related("listing", "listing__instance", "listing__seller", "buyer")
                    .select_for_update()
                    .get(pk=offer_id)
                )
            except AuctionOffer.DoesNotExist:
                raise RuntimeError("This bid no longer exists.")
            listing = offer.listing
            if listing.seller.discord_id != seller_discord_id:
                raise RuntimeError("This isn't your listing.")
            if listing.status != AuctionListing.Status.ACTIVE or offer.status != AuctionOffer.Status.PENDING:
                raise RuntimeError("This bid is no longer available.")

            adjust_money(
                listing.seller,
                offer.amount,
                reason=BerryTransaction.Reason.AUCTION_SALE_PAYOUT,
                description=f"Listing #{listing.pk} sold",
                server_id=listing.server_id,
            )

            instance = listing.instance
            instance.player = offer.buyer
            instance.locked = None
            instance.save(update_fields=["player", "locked"])

            offer.status = AuctionOffer.Status.ACCEPTED
            offer.save(update_fields=["status"])
            listing.status = AuctionListing.Status.SOLD
            listing.save(update_fields=["status"])

            won_context = EventContext(instances=[instance], price=offer.amount, server_id=listing.server_id)
            winner_id = offer.buyer_id
            transaction.on_commit(lambda: bus.dispatch_soon(winner_id, Event.AUCTION_WON, context=won_context))

            others = AuctionOffer.objects.filter(listing=listing, status=AuctionOffer.Status.PENDING).exclude(
                pk=offer.pk
            )
            for other in others.select_related("buyer"):
                adjust_money(
                    other.buyer,
                    other.amount,
                    reason=BerryTransaction.Reason.AUCTION_BID_REFUND,
                    description=f"Outbid on listing #{listing.pk}",
                    server_id=listing.server_id,
                )
                other.status = AuctionOffer.Status.REFUNDED
                other.save(update_fields=["status"])

            return listing, offer

    async def reject_offer(self, offer_id: int, seller_discord_id: int) -> AuctionOffer:
        return await services.safe_settle(self._reject_offer, offer_id, seller_discord_id)

    def _reject_offer(self, offer_id: int, seller_discord_id: int) -> AuctionOffer:
        with transaction.atomic():
            try:
                offer = (
                    AuctionOffer.objects.select_related("listing__seller", "buyer").select_for_update().get(pk=offer_id)
                )
            except AuctionOffer.DoesNotExist:
                raise RuntimeError("This bid no longer exists.")
            if offer.listing.seller.discord_id != seller_discord_id:
                raise RuntimeError("This isn't your listing.")
            if offer.status != AuctionOffer.Status.PENDING:
                raise RuntimeError("This bid is no longer pending.")

            adjust_money(
                offer.buyer,
                offer.amount,
                reason=BerryTransaction.Reason.AUCTION_BID_REFUND,
                description=f"Bid rejected on listing #{offer.listing_id}",
            )
            offer.status = AuctionOffer.Status.REJECTED
            offer.save(update_fields=["status"])
            return offer

    # -- /auction shop & /auction buy ------------------------------------------------------------------------

    @app_commands.command(name="shop")
    @app_commands.describe(treasure="Only show this treasure", sort="How to order the results")
    @app_commands.choices(sort=SORT_CHOICES)
    async def shop(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        treasure: BallEnabledTransform | None = None,
        sort: app_commands.Choice[str] | None = None,
    ):
        """
        Browse Buggy's Auction House resale shop.

        Parameters
        ----------
        treasure: Ball
            Only show this treasure.
        sort: str
            How to order the results.
        """
        await interaction.response.defer(thinking=True)
        auction_settings = await AuctionSettings.aload()
        qs = HotelStock.objects.filter(status=HotelStock.Status.AVAILABLE).select_related(
            "instance", "instance__ball"
        )
        if auction_settings.max_shop_rarity is not None:
            qs = qs.filter(instance__ball__rarity__lte=auction_settings.max_shop_rarity)
        cutoff = timezone.now() - timedelta(hours=auction_settings.shop_listing_hours)
        qs = qs.filter(acquired_at__gte=cutoff)
        if treasure is not None:
            qs = qs.filter(instance__ball=treasure)
        order = _STOCK_SORT_FIELDS.get(sort.value if sort else "", "resale_price")
        stock = [item async for item in qs.order_by(order)]
        if not stock:
            await interaction.followup.send(
                "No items match that treasure." if treasure else "Buggy doesn't have anything for sale right now."
            )
            return

        server_id = interaction.guild_id
        discount_percent = (
            await services.get_total_booster_bonus(interaction.user, server_id, "buy_discount_percent")
            if server_id is not None
            else 0
        )

        entries = []
        for item in stock:
            price = item.resale_price
            if discount_percent:
                price = round(price * (1 - min(discount_percent, 100) / 100))
            entries.append(
                (
                    f"#{item.id} — {item.instance.description(include_emoji=True, bot=self.bot)}",
                    format_currency(price, False, self.bot),
                )
            )
        source = FieldPageSource(entries, per_page=8, inline=False)
        source.embed.title = "Buggy's Auction House — Resale shop"
        source.embed.colour = AUCTION_COLOR
        pages = Pages(source, interaction=interaction, compact=True)
        await pages.start()

    @app_commands.command(name="buy")
    @app_commands.rename(stock_id="item")
    async def buy(self, interaction: discord.Interaction["BallsDexBot"], stock_id: int):
        """
        Buy a treasure from Buggy's Auction House resale shop.

        Parameters
        ----------
        stock_id: int
            The item you want to buy.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            stock = await HotelStock.objects.select_related("instance", "instance__ball").aget(pk=stock_id)
        except HotelStock.DoesNotExist:
            await interaction.followup.send("This item doesn't exist.")
            return
        if stock.status != HotelStock.Status.AVAILABLE:
            await interaction.followup.send("This item has already been sold.")
            return

        auction_settings = await AuctionSettings.aload()
        if (
            auction_settings.max_shop_rarity is not None
            and stock.instance.countryball.rarity > auction_settings.max_shop_rarity
        ):
            await interaction.followup.send("This item isn't part of Buggy's current shop selection.")
            return

        buyer, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        server_id = interaction.guild_id
        discount_percent = (
            await services.get_total_booster_bonus(interaction.user, server_id, "buy_discount_percent")
            if server_id is not None
            else 0
        )
        price = stock.resale_price
        if discount_percent:
            price = round(price * (1 - min(discount_percent, 100) / 100))
        if not buyer.can_afford(price):
            await interaction.followup.send(
                f"You don't have enough {settings.currency_display_plural(self.bot)} for this item.\n"
                f"Your balance: **{format_currency(buyer.money, False, self.bot)}** • "
                f"Price: **{format_currency(price, False, self.bot)}**"
            )
            return

        try:
            await services.safe_settle(self._settle_shop_purchase, stock.pk, buyer.pk, price)
        except RuntimeError as error:
            await interaction.followup.send(str(error))
            return
        await interaction.followup.send(f"Bought for **{format_currency(price, False, self.bot)}**!", ephemeral=True)

    def _settle_shop_purchase(self, stock_id: int, buyer_id: int, price: int):
        with transaction.atomic():
            stock = HotelStock.objects.select_related("instance").select_for_update().get(pk=stock_id)
            if stock.status != HotelStock.Status.AVAILABLE:
                raise RuntimeError("This item has already been sold.")
            buyer = Player.objects.select_for_update().get(pk=buyer_id)
            if buyer.money < price:
                raise RuntimeError(
                    "You don't have enough coins anymore "
                    f"(balance: {format_currency(buyer.money, False)}, price: {format_currency(price, False)})."
                )
            adjust_money(
                buyer,
                -price,
                reason=BerryTransaction.Reason.AUCTION_SHOP_BUY,
                description=f"Bought stock #{stock.pk} from Buggy's shop",
                server_id=stock.server_id,
            )
            instance = stock.instance
            instance.player = buyer
            instance.save(update_fields=["player"])
            stock.status = HotelStock.Status.SOLD
            stock.save(update_fields=["status"])

            context = EventContext(
                instances=[instance], price=price, amount=-price, server_id=stock.server_id
            )
            transaction.on_commit(lambda: bus.dispatch_soon(buyer_id, Event.SHOP_BUY, context=context))

    @buy.autocomplete("stock_id")
    async def buy_autocomplete(
        self, interaction: discord.Interaction["BallsDexBot"], current: str
    ) -> list[app_commands.Choice[int]]:
        auction_settings = await AuctionSettings.aload()
        qs = HotelStock.objects.filter(status=HotelStock.Status.AVAILABLE)
        if auction_settings.max_shop_rarity is not None:
            qs = qs.filter(instance__ball__rarity__lte=auction_settings.max_shop_rarity)
        cutoff = timezone.now() - timedelta(hours=auction_settings.shop_listing_hours)
        qs = qs.filter(acquired_at__gte=cutoff)
        if current:
            qs = qs.filter(instance__ball__country__icontains=current)
        qs = qs.select_related("instance").order_by("resale_price")[:25]
        return [
            app_commands.Choice(
                name=f"#{item.id} {item.instance.short_description()} — {format_currency(item.resale_price)}",
                value=item.id,
            )
            async for item in qs
        ]

    # -- /auction featured --------------------------------------------------------------------------

    @featured.command(name="create")
    @app_commands.describe(
        title="Name of the auction",
        starting_bid="Minimum starting bid",
        duration_hours="How long the auction runs, in hours (combine with duration_minutes)",
        duration_minutes="Extra minutes on top of the hours, for shorter auctions",
        channel="Channel to post the live embed in",
        min_bid_increment="Minimum amount each new bid must exceed the last by (default 1)",
    )
    @app_commands.guild_only()
    async def featured_create(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        title: app_commands.Range[str, 1, 100],
        starting_bid: app_commands.Range[int, 1],
        channel: discord.TextChannel,
        duration_hours: app_commands.Range[int, 0, 168] = 0,
        duration_minutes: app_commands.Range[int, 0, 59] = 0,
        min_bid_increment: app_commands.Range[int, 1] = 1,
    ):
        """
        Start a Featured Auction (mod/admin only) — add items to it with /auction featured additem.
        """
        server_id = interaction.guild_id
        assert server_id is not None
        if not await services.is_auction_admin(interaction.user, server_id):
            await interaction.response.send_message(
                "You don't have permission to create Featured Auctions here.", ephemeral=True
            )
            return
        total_minutes = duration_hours * 60 + duration_minutes
        if total_minutes == 0:
            await interaction.response.send_message(
                "Set a duration with `duration_hours`, `duration_minutes`, or both.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        creator, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        auction = await FeaturedAuction.objects.acreate(
            title=title,
            server_id=server_id,
            channel_id=channel.id,
            creator=creator,
            min_bid_increment=min_bid_increment,
            starting_bid=starting_bid,
            expires_at=timezone.now() + timedelta(minutes=total_minutes),
        )
        embed = await self._build_featured_embed(auction)
        view = views.FeaturedAuctionView(self, auction.id)
        message = await channel.send(embed=embed, view=view)
        auction.message_id = message.id
        await auction.asave(update_fields=("message_id",))
        await interaction.followup.send(
            f"Featured auction #{auction.id} created in {channel.mention}. Add items with "
            f"`/auction featured additem auction:{auction.id}`.",
            ephemeral=True,
        )

    @featured.command(name="additem")
    @app_commands.rename(auction_id="auction")
    @app_commands.guild_only()
    async def featured_additem(
        self, interaction: discord.Interaction["BallsDexBot"], auction_id: int, countryball: BallInstanceTransform
    ):
        """
        Add a treasure you own to one of your draft/active Featured Auctions.
        """
        if not countryball:
            return
        server_id = interaction.guild_id
        assert server_id is not None
        if not await services.is_auction_admin(interaction.user, server_id):
            await interaction.response.send_message(
                "You don't have permission to manage Featured Auctions here.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            auction = await FeaturedAuction.objects.aget(pk=auction_id, status=FeaturedAuction.Status.ACTIVE)
        except FeaturedAuction.DoesNotExist:
            await interaction.followup.send("This featured auction doesn't exist or has already closed.")
            return
        if auction.creator_id != countryball.player_id:
            await interaction.followup.send("You can only add treasures you own yourself.")
            return
        if not countryball.is_tradeable or countryball.deleted:
            await interaction.followup.send(f"This {settings.collectible_name} can't be added.")
            return
        if await countryball.is_locked() or await services.is_already_committed(countryball):
            await interaction.followup.send("This treasure is locked or already committed elsewhere.")
            return
        if await FeaturedAuctionItem.objects.filter(instance=countryball).aexists():
            await interaction.followup.send("This treasure is already part of a featured auction.")
            return

        try:
            await services.safe_settle(self._add_featured_item, auction_id, countryball.pk)
        except RuntimeError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        await self._refresh_featured_embed(auction_id)
        await interaction.followup.send(f"Added to featured auction #{auction_id}.", ephemeral=True)

    def _add_featured_item(self, auction_id: int, instance_id: int):
        with transaction.atomic():
            instance = BallInstance.objects.select_for_update().get(pk=instance_id)
            instance.locked = timezone.now()
            instance.save(update_fields=["locked"])
            FeaturedAuctionItem.objects.create(auction_id=auction_id, instance=instance)

    @featured_additem.autocomplete("auction_id")
    async def featured_additem_autocomplete(
        self, interaction: discord.Interaction["BallsDexBot"], current: str
    ) -> list[app_commands.Choice[int]]:
        qs = FeaturedAuction.objects.filter(
            server_id=interaction.guild_id,
            status=FeaturedAuction.Status.ACTIVE,
            creator__discord_id=interaction.user.id,
        ).order_by("-created_at")[:25]
        return [app_commands.Choice(name=f"#{auction.id} {auction.title}", value=auction.id) async for auction in qs]

    @featured.command(name="cancel")
    @app_commands.rename(auction_id="auction")
    @app_commands.guild_only()
    async def featured_cancel(self, interaction: discord.Interaction["BallsDexBot"], auction_id: int):
        """
        Cancel one of your Featured Auctions early. Items and the current bid are refunded.
        """
        server_id = interaction.guild_id
        assert server_id is not None
        if not await services.is_auction_admin(interaction.user, server_id):
            await interaction.response.send_message(
                "You don't have permission to manage Featured Auctions here.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            auction = await services.safe_settle(
                self._close_featured_auction, auction_id, FeaturedAuction.Status.CANCELLED
            )
        except RuntimeError as error:
            await interaction.followup.send(str(error))
            return
        await self._render_featured_close(auction)
        await interaction.followup.send(f"Featured auction #{auction_id} cancelled.", ephemeral=True)

    @featured_cancel.autocomplete("auction_id")
    async def featured_cancel_autocomplete(
        self, interaction: discord.Interaction["BallsDexBot"], current: str
    ) -> list[app_commands.Choice[int]]:
        qs = FeaturedAuction.objects.filter(
            server_id=interaction.guild_id, status=FeaturedAuction.Status.ACTIVE
        ).order_by("-created_at")[:25]
        return [app_commands.Choice(name=f"#{auction.id} {auction.title}", value=auction.id) async for auction in qs]

    # -- buttons on the live embed (creator-only) ------------------------------------------

    async def accept_featured_now(self, auction_id: int, requester_discord_id: int) -> FeaturedAuction:
        return await services.safe_settle(self._accept_featured_now, auction_id, requester_discord_id)

    def _accept_featured_now(self, auction_id: int, requester_discord_id: int) -> FeaturedAuction:
        with transaction.atomic():
            try:
                auction = (
                    FeaturedAuction.objects.select_related("creator")
                    .select_for_update()
                    .get(pk=auction_id, status=FeaturedAuction.Status.ACTIVE)
                )
            except FeaturedAuction.DoesNotExist:
                raise RuntimeError("This featured auction doesn't exist or has already closed.")
            if auction.creator.discord_id != requester_discord_id:
                raise RuntimeError("Only the creator can accept early.")
            if auction.current_bidder_id is None:
                raise RuntimeError("There are no bids yet.")
            self._settle_featured_close(auction, FeaturedAuction.Status.SOLD, award_to_bidder=True)
            return auction

    async def cancel_featured_now(self, auction_id: int, requester_discord_id: int) -> FeaturedAuction:
        return await services.safe_settle(
            self._close_featured_auction,
            auction_id,
            FeaturedAuction.Status.CANCELLED,
            requester_discord_id=requester_discord_id,
        )

    async def place_featured_bid(
        self, auction_id: int, bidder_discord_id: int, amount: int
    ) -> tuple[FeaturedAuction, Player | None, int, int]:
        """
        Returns the updated auction, the previous bidder and bid, and how many minutes the auction was
        extended by (0 if the bid didn't come in at the last minute).
        """
        return await services.safe_settle(self._place_featured_bid, auction_id, bidder_discord_id, amount)

    def _place_featured_bid(
        self, auction_id: int, bidder_discord_id: int, amount: int
    ) -> tuple[FeaturedAuction, Player | None, int, int]:
        with transaction.atomic():
            try:
                auction = FeaturedAuction.objects.select_for_update().get(
                    pk=auction_id, status=FeaturedAuction.Status.ACTIVE
                )
            except FeaturedAuction.DoesNotExist:
                raise RuntimeError("This featured auction is no longer active.")
            now = timezone.now()
            if auction.expires_at <= now:
                raise RuntimeError("This featured auction has already ended.")

            minimum = (
                auction.current_bid + auction.min_bid_increment if auction.current_bid else auction.starting_bid
            )
            if amount < minimum:
                raise RuntimeError(f"Your bid must be at least {format_currency(minimum, False)}.")

            bidder, _ = Player.objects.get_or_create(discord_id=bidder_discord_id)
            if bidder.pk == auction.creator_id:
                raise RuntimeError("You can't bid on your own featured auction.")
            bidder.refresh_from_db(fields=["money"])
            if bidder.money < amount:
                raise RuntimeError(
                    f"You don't have enough coins (balance: {format_currency(bidder.money, False)})."
                )

            previous_bidder = auction.current_bidder
            previous_bid = auction.current_bid
            adjust_money(
                bidder,
                -amount,
                reason=BerryTransaction.Reason.FEATURED_BID_HOLD,
                description=f"Bid on featured auction #{auction.pk} ({auction.title})",
                server_id=auction.server_id,
            )
            if previous_bidder is not None and previous_bid is not None:
                adjust_money(
                    previous_bidder,
                    previous_bid,
                    reason=BerryTransaction.Reason.FEATURED_BID_REFUND,
                    description=f"Outbid on featured auction #{auction.pk} ({auction.title})",
                    server_id=auction.server_id,
                )

            FeaturedAuctionBid.objects.create(auction=auction, bidder=bidder, amount=amount)
            auction.current_bid = amount
            auction.current_bidder = bidder
            auction.bid_count = F("bid_count") + 1
            update_fields = ["current_bid", "current_bidder", "bid_count"]

            # a bid placed right before the end pushes it back, so nobody can snipe the auction
            extension = 0
            auction_settings = AuctionSettings.load()
            window = timedelta(minutes=auction_settings.featured_extension_window_minutes)
            if auction_settings.featured_extension_minutes and auction.expires_at - now <= window:
                extension = auction_settings.featured_extension_minutes
                auction.expires_at += timedelta(minutes=extension)
                update_fields.append("expires_at")

            auction.save(update_fields=update_fields)
            auction.refresh_from_db()
            return auction, previous_bidder, previous_bid or 0, extension

    async def announce_featured_extension(self, auction: FeaturedAuction, minutes: int):
        channel = self.bot.get_channel(auction.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(auction.channel_id)
            except discord.HTTPException:
                return
        try:
            await channel.send(  # type: ignore
                f"\N{ALARM CLOCK} Last-minute bid on **Auction #{auction.id} — {auction.title}**! "
                f"The auction is extended by **{minutes} minutes** and now ends "
                f"{discord.utils.format_dt(auction.expires_at, 'R')}."
            )
        except discord.HTTPException:
            log.warning("Failed to announce the extension of featured auction %s", auction.id)

    async def _build_featured_embed(self, auction: FeaturedAuction) -> discord.Embed:
        items = [item async for item in auction.items.select_related("instance", "instance__ball").all()]
        creator = await Player.objects.aget(pk=auction.creator_id)

        lines = [f"**Items ({len(items)}):**"]
        for item in items:
            lines.append(f"• {item.instance.description(include_emoji=True, bot=self.bot)}")
        embed = discord.Embed(
            title="🏴‍☠️ Featured Auction!",
            description=f"**Auction #{auction.id} — {auction.title}**\n\n" + "\n".join(lines),
            color=AUCTION_COLOR,
        )
        embed.add_field(name="Seller", value=f"<@{creator.discord_id}>", inline=True)
        embed.add_field(name="Ends", value=discord.utils.format_dt(auction.expires_at, "R"), inline=True)
        if auction.current_bid is not None and auction.current_bidder_id is not None:
            bidder = await Player.objects.aget(pk=auction.current_bidder_id)
            embed.add_field(
                name="Current bid",
                value=f"{format_currency(auction.current_bid, False, self.bot)} by <@{bidder.discord_id}>",
                inline=False,
            )
            next_minimum = auction.current_bid + auction.min_bid_increment
        else:
            next_minimum = auction.starting_bid

        recent_bids = [
            bid
            async for bid in FeaturedAuctionBid.objects.filter(auction=auction)
            .select_related("bidder")
            .order_by("-created_at")[:5]
        ]
        if recent_bids:
            embed.add_field(
                name="Recent bids",
                value="\n".join(
                    f"<@{bid.bidder.discord_id}> — {format_currency(bid.amount, False, self.bot)} "
                    f"({discord.utils.format_dt(bid.created_at, 'R')})"
                    for bid in recent_bids
                ),
                inline=False,
            )

        embed.add_field(name="Next minimum", value=format_currency(next_minimum, False, self.bot), inline=False)
        embed.add_field(
            name="​",
            value="Use the button below (or `/auction bid`) to place a bid. Once confirmed, a bid cannot be "
            "retracted.",
            inline=False,
        )
        embed.set_footer(text=f"{auction.bid_count} bid(s) placed")
        return embed

    async def _refresh_featured_embed(self, auction_id: int):
        try:
            auction = await FeaturedAuction.objects.aget(pk=auction_id)
        except FeaturedAuction.DoesNotExist:
            return
        if auction.message_id is None:
            return
        channel = self.bot.get_channel(auction.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(auction.channel_id)
            except discord.HTTPException:
                return
        try:
            message = await channel.fetch_message(auction.message_id)
        except discord.HTTPException:
            return
        embed = await self._build_featured_embed(auction)
        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            pass

    async def _render_featured_close(self, auction: FeaturedAuction):
        if auction.message_id is None:
            return
        channel = self.bot.get_channel(auction.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(auction.channel_id)
            except discord.HTTPException:
                return
        try:
            message = await channel.fetch_message(auction.message_id)
        except discord.HTTPException:
            return
        embed = await self._build_featured_embed(auction)
        if auction.status == FeaturedAuction.Status.SOLD:
            embed.title = "🏴‍☠️ Featured Auction — Sold!"
        elif auction.status == FeaturedAuction.Status.CANCELLED:
            embed.title = "🏴‍☠️ Featured Auction — Cancelled"
        else:
            embed.title = "🏴‍☠️ Featured Auction — Ended (no bids)"
        # keep the embed and its buttons in place, just greyed out — not removed
        closed_view = views.FeaturedAuctionView(self, auction.id)
        for item in closed_view.children:
            item.disabled = True  # type: ignore
        try:
            await message.edit(embed=embed, view=closed_view)
        except discord.HTTPException:
            pass

        if auction.status == FeaturedAuction.Status.SOLD and auction.current_bidder_id is not None:
            winner = await Player.objects.aget(pk=auction.current_bidder_id)
            try:
                await channel.send(
                    f"\N{PARTY POPPER} <@{winner.discord_id}> won **Auction #{auction.id} — {auction.title}** "
                    f"for **{format_currency(auction.current_bid, False, self.bot)}**!",
                    allowed_mentions=await can_mention([winner]),
                )
            except discord.HTTPException:
                log.warning("Failed to send featured auction winner announcement in channel %s", channel.id)

    def _close_featured_auction(
        self, auction_id: int, status: str, *, requester_discord_id: int | None = None
    ) -> FeaturedAuction:
        """
        Manual close (cancel): refunds the current bidder and returns items to the creator.
        `requester_discord_id` is only checked when provided — the slash command relies on the
        broader auction-admin role check instead, while the embed's Cancel button (open to
        anyone who can see it) restricts this to the auction's own creator.
        """
        with transaction.atomic():
            try:
                auction = (
                    FeaturedAuction.objects.select_related("creator")
                    .select_for_update()
                    .get(pk=auction_id, status=FeaturedAuction.Status.ACTIVE)
                )
            except FeaturedAuction.DoesNotExist:
                raise RuntimeError("This featured auction doesn't exist or has already closed.")
            if requester_discord_id is not None and auction.creator.discord_id != requester_discord_id:
                raise RuntimeError("Only the creator can cancel this from here.")
            self._settle_featured_close(auction, status, award_to_bidder=False)
            return auction

    def _settle_featured_close(self, auction: FeaturedAuction, status: str, *, award_to_bidder: bool):
        items = list(FeaturedAuctionItem.objects.filter(auction=auction).select_related("instance"))
        if award_to_bidder and auction.current_bidder_id is not None:
            recipient_id = auction.current_bidder_id
            # the winning bid was escrowed from the bidder at bid time — pay it out to the creator now
            adjust_money(
                auction.creator_id,
                auction.current_bid,
                reason=BerryTransaction.Reason.FEATURED_PAYOUT,
                description=f"Featured auction #{auction.pk} sold ({auction.title})",
                server_id=auction.server_id,
            )
        else:
            if auction.current_bidder_id is not None and auction.current_bid is not None:
                adjust_money(
                    auction.current_bidder_id,
                    auction.current_bid,
                    reason=BerryTransaction.Reason.FEATURED_BID_REFUND,
                    description=f"Featured auction #{auction.pk} closed unsold ({auction.title})",
                    server_id=auction.server_id,
                )
            recipient_id = auction.creator_id

        for item in items:
            item.instance.player_id = recipient_id
            item.instance.locked = None
            item.instance.save(update_fields=["player", "locked"])

        auction.status = status
        auction.save(update_fields=["status"])

    # -- activity tracking (for giveaway eligibility) ------------------------------------------

    @commands.Cog.listener()
    async def on_app_command_completion(
        self, interaction: discord.Interaction["BallsDexBot"], command: app_commands.Command | app_commands.ContextMenu
    ):
        if interaction.guild_id is None:
            return
        await sync_to_async(self._touch_activity)(interaction.user.id, interaction.guild_id)

    def _touch_activity(self, discord_id: int, server_id: int):
        player, _ = Player.objects.get_or_create(discord_id=discord_id)
        ServerActivity.objects.update_or_create(player=player, server_id=server_id)

    # -- background loops ------------------------------------------------------------------------

    @tasks.loop(minutes=5)
    async def sweep_listings(self):
        await sync_to_async(self._sweep_listings)()

    @sweep_listings.before_loop
    async def before_sweep_listings(self):
        await self.bot.wait_until_ready()

    def _sweep_listings(self):
        now = timezone.now()
        with transaction.atomic():
            active = list(
                AuctionListing.objects.select_for_update()
                .filter(status=AuctionListing.Status.ACTIVE)
                .select_related("instance")
            )
            for listing in active:
                if listing.expires_at <= now:
                    self._expire_listing(listing)
                else:
                    listing.instance.locked = now
                    listing.instance.save(update_fields=["locked"])

    def _expire_listing(self, listing: AuctionListing):
        listing.status = AuctionListing.Status.EXPIRED
        listing.save(update_fields=["status"])
        listing.instance.locked = None
        listing.instance.save(update_fields=["locked"])
        pending = AuctionOffer.objects.filter(listing=listing, status=AuctionOffer.Status.PENDING).select_related(
            "buyer"
        )
        for offer in pending:
            adjust_money(
                offer.buyer,
                offer.amount,
                reason=BerryTransaction.Reason.AUCTION_BID_REFUND,
                description=f"Listing #{listing.pk} expired unsold",
                server_id=listing.server_id,
            )
            offer.status = AuctionOffer.Status.REFUNDED
            offer.save(update_fields=["status"])

    @tasks.loop(minutes=5)
    async def sweep_shop_stock(self):
        await sync_to_async(self._sweep_shop_stock)()

    @sweep_shop_stock.before_loop
    async def before_sweep_shop_stock(self):
        await self.bot.wait_until_ready()

    def _sweep_shop_stock(self):
        auction_settings = AuctionSettings.load()
        cutoff = timezone.now() - timedelta(hours=auction_settings.shop_listing_hours)
        with transaction.atomic():
            expired = list(
                HotelStock.objects.select_for_update()
                .filter(status=HotelStock.Status.AVAILABLE, acquired_at__lt=cutoff)
                .select_related("instance")
            )
            for stock in expired:
                stock.instance.deleted = True
                stock.instance.save(update_fields=["deleted"])
                stock.delete()

    @tasks.loop(hours=1)
    async def giveaway_draw(self):
        result = await sync_to_async(self._giveaway_draw)()
        if result is not None:
            winner, instance, home_server_id = result
            await self.notify_giveaway_win(winner, instance, home_server_id)

    @giveaway_draw.before_loop
    async def before_giveaway_draw(self):
        await self.bot.wait_until_ready()

    def _giveaway_draw(self):
        auction_settings = AuctionSettings.load()
        cutoff = timezone.now() - timedelta(hours=auction_settings.giveaway_interval_hours)
        activity_cutoff = timezone.now() - timedelta(hours=auction_settings.giveaway_activity_window_hours)

        last = GiveawayLog.objects.order_by("-drawn_at").first()
        if last is not None and last.drawn_at > cutoff:
            return None

        activity = ServerActivity.objects.filter(last_seen__gte=activity_cutoff)
        if auction_settings.giveaway_server_id is not None:
            activity = activity.filter(server_id=auction_settings.giveaway_server_id)
        eligible_ids = list(activity.values_list("player_id", flat=True).distinct())
        if not eligible_ids:
            return None
        stock_ids = list(
            HotelStock.objects.filter(status=HotelStock.Status.AVAILABLE).values_list("pk", flat=True)
        )
        if not stock_ids:
            return None

        winner_player_id = random.choice(eligible_ids)
        stock_id = random.choice(stock_ids)

        with transaction.atomic():
            stock = HotelStock.objects.select_related("instance").select_for_update().get(pk=stock_id)
            if stock.status != HotelStock.Status.AVAILABLE:
                return None
            winner = Player.objects.get(pk=winner_player_id)
            instance = stock.instance
            instance.player = winner
            instance.save(update_fields=["player"])
            stock.status = HotelStock.Status.GIVEN_AWAY
            stock.save(update_fields=["status"])

            if auction_settings.giveaway_server_id is not None:
                # Giveaways are pinned to one server: always announce there, since that's the only
                # place the winner was drawn from.
                home_server_id = auction_settings.giveaway_server_id
            else:
                home_activity = (
                    ServerActivity.objects.filter(player_id=winner_player_id).order_by("-last_seen").first()
                )
                home_server_id = home_activity.server_id if home_activity else None

            GiveawayLog.objects.create(server_id=home_server_id or 0, winner=winner, instance=instance)
            return winner, instance, home_server_id

    # checked every minute since last-minute bids keep moving the end of featured auctions
    @tasks.loop(minutes=1)
    async def sweep_featured_auctions(self):
        closed = await sync_to_async(self._sweep_featured_auctions)()
        for auction in closed:
            await self._render_featured_close(auction)

    @sweep_featured_auctions.before_loop
    async def before_sweep_featured_auctions(self):
        await self.bot.wait_until_ready()

    def _sweep_featured_auctions(self) -> list[FeaturedAuction]:
        now = timezone.now()
        closed = []
        with transaction.atomic():
            expired = list(
                FeaturedAuction.objects.select_for_update().filter(
                    status=FeaturedAuction.Status.ACTIVE, expires_at__lte=now
                )
            )
            for auction in expired:
                status = FeaturedAuction.Status.SOLD if auction.current_bidder_id else FeaturedAuction.Status.EXPIRED_UNSOLD
                self._settle_featured_close(auction, status, award_to_bidder=True)
                closed.append(auction)
        return closed
