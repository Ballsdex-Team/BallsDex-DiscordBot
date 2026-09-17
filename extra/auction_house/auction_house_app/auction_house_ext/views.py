from typing import TYPE_CHECKING

import discord

from ballsdex.core.discord import View
from settings.models import settings
from settings.utils import format_currency

from .. import services
from ..models import AuctionOffer, FeaturedAuction

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

    from .cog import AuctionHouse

# every embed uses the color configured in the admin panel settings
AUCTION_COLOR = settings.embed_colour


class MyBidsView(View):
    """
    Browses a buyer's own pending bids one page (one bid) at a time — shows whether they've
    been outbid or matched, and lets them add to the bid or cancel it, right from that page.
    """

    def __init__(
        self, interaction: discord.Interaction["BallsDexBot"], offers: list["AuctionOffer"], cog: "AuctionHouse"
    ):
        super().__init__(timeout=180)
        self.restrict_author(interaction.user.id)
        self.bot = cog.bot
        self.cog = cog
        self.offers = offers
        self.index = 0
        self._update_nav()

    def _update_nav(self):
        self.previous_button.disabled = self.index == 0
        self.next_button.disabled = self.index >= len(self.offers) - 1

    async def build_embed(self) -> discord.Embed:
        offer = self.offers[self.index]
        listing = offer.listing
        top_amount = await self.cog.top_pending_bid(offer.listing_id, offer.pk)
        outbid = top_amount is not None and top_amount >= offer.amount

        embed = discord.Embed(title=f"Bid {self.index + 1}/{len(self.offers)}", color=AUCTION_COLOR)
        embed.add_field(
            name="Listing",
            value=f"#{listing.id} — {listing.instance.short_description()}",
            inline=False,
        )
        embed.add_field(name="Your bid", value=format_currency(offer.amount, False, self.bot), inline=True)
        embed.add_field(
            name="Status",
            value=(
                f"🔴 Highest bid is now **{format_currency(top_amount, False, self.bot)}** (not yours) — "
                "add more or you may lose out."
                if outbid
                else "🟢 You're currently the highest bidder."
            ),
            inline=True,
        )
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        self.index -= 1
        self._update_nav()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        self.index += 1
        self._update_nav()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)

    @discord.ui.button(label="Add", style=discord.ButtonStyle.success, row=1)
    async def add_button(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        offer = self.offers[self.index]
        await interaction.response.send_modal(AddBidModal(self, offer.pk))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel_button(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        offer = self.offers[self.index]
        try:
            cancelled = await self.cog.cancel_offer(offer.pk, interaction.user.id)
        except RuntimeError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        del self.offers[self.index]
        if not self.offers:
            for item in self.children:
                item.disabled = True  # type: ignore
            await interaction.response.edit_message(
                content=f"Bid #{cancelled.id} cancelled, "
                f"**{format_currency(cancelled.amount, False, self.bot)}** refunded. No more pending bids.",
                embed=None,
                view=self,
            )
            return
        self.index = min(self.index, len(self.offers) - 1)
        self._update_nav()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)
        await interaction.followup.send(
            f"Bid #{cancelled.id} cancelled, **{format_currency(cancelled.amount, False, self.bot)}** refunded.",
            ephemeral=True,
        )


class AddBidModal(discord.ui.Modal, title="Add to your bid"):
    """Opened by MyBidsView's Add button — lets the buyer top up their existing pending bid."""

    def __init__(self, view: "MyBidsView", offer_id: int):
        super().__init__()
        self.view_ref = view
        self.offer_id = offer_id
        self.amount_input: discord.ui.TextInput = discord.ui.TextInput(
            label="Amount to add", placeholder="e.g. 500", required=True, max_length=15
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction["BallsDexBot"]):
        raw = self.amount_input.value.strip().replace(",", "")
        if not raw.isdigit() or int(raw) <= 0:
            await interaction.response.send_message("Enter a positive whole number.", ephemeral=True)
            return
        additional = int(raw)
        try:
            updated = await self.view_ref.cog.increase_offer(self.offer_id, interaction.user.id, additional)
        except RuntimeError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        for i, offer in enumerate(self.view_ref.offers):
            if offer.pk == updated.pk:
                self.view_ref.offers[i] = updated
                break
        await interaction.response.edit_message(embed=await self.view_ref.build_embed(), view=self.view_ref)


class ListingOffersView(View):
    """
    Lets a seller accept or reject the current highest bid on each of their listings.
    Only the amount is ever shown — the bidder's identity stays hidden until accepted.
    """

    # 12 listings * 2 buttons = 24, safely under Discord's 25-component-per-view limit
    MAX_LISTINGS = 12

    def __init__(
        self, interaction: discord.Interaction["BallsDexBot"], top_offers: list["AuctionOffer"], cog: "AuctionHouse"
    ):
        super().__init__(timeout=180)
        self.restrict_author(interaction.user.id)
        self.bot = cog.bot
        self.cog = cog

        for offer in top_offers[: self.MAX_LISTINGS]:
            accept_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}",
            )
            reject_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
            )
            accept_button.callback = self._make_callback(offer.id, accept=True)
            reject_button.callback = self._make_callback(offer.id, accept=False)
            self.add_item(accept_button)
            self.add_item(reject_button)

    def _make_callback(self, offer_id: int, accept: bool):
        async def callback(interaction: discord.Interaction["BallsDexBot"]):
            for item in self.children:
                item.disabled = True  # type: ignore
            await interaction.response.edit_message(view=self)

            if accept:
                try:
                    listing, offer = await self.cog.accept_offer(offer_id, interaction.user.id)
                except RuntimeError as error:
                    await interaction.followup.send(str(error), ephemeral=True)
                    return
                await interaction.followup.send(
                    f"Accepted — **{format_currency(offer.amount, False, self.bot)}** added to your balance. "
                    "Other pending bids on that listing were refunded.",
                    ephemeral=True,
                )
                await self.cog.notify_sale(listing, offer)
            else:
                try:
                    offer = await self.cog.reject_offer(offer_id, interaction.user.id)
                except RuntimeError as error:
                    await interaction.followup.send(str(error), ephemeral=True)
                    return
                await interaction.followup.send(
                    f"Rejected — **{format_currency(offer.amount, False, self.bot)}** refunded to the buyer.",
                    ephemeral=True,
                )

        return callback


class FeaturedBidModal(discord.ui.Modal, title="Place your bid"):
    """Opened by the featured auction's Bid button — lets the bidder type a custom amount."""

    def __init__(self, cog: "AuctionHouse", auction_id: int, minimum: int):
        super().__init__()
        self.cog = cog
        self.auction_id = auction_id
        self.amount_input: discord.ui.TextInput = discord.ui.TextInput(
            label="Bid amount", placeholder=f"Minimum: {minimum:,}", required=True, max_length=15
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction["BallsDexBot"]):
        raw = self.amount_input.value.strip().replace(",", "")
        if not raw.isdigit():
            await interaction.response.send_message("Enter a whole number.", ephemeral=True)
            return
        amount = int(raw)
        try:
            await self.cog.place_featured_bid(self.auction_id, interaction.user.id, amount)
        except RuntimeError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Bid of **{format_currency(amount, False, self.cog.bot)}** placed on featured auction "
            f"#{self.auction_id}!",
            ephemeral=True,
        )
        await self.cog._refresh_featured_embed(self.auction_id)


class FeaturedAuctionView(View):
    """
    Persistent view attached to a Featured Auction's live embed — built with a stable
    custom_id so it keeps working across bot restarts once re-registered in cog_load.
    """

    def __init__(self, cog: "AuctionHouse", auction_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.auction_id = auction_id
        self.bid_button.custom_id = f"auction_featured_bid:{auction_id}"
        self.accept_button.custom_id = f"auction_featured_accept:{auction_id}"
        self.cancel_button.custom_id = f"auction_featured_cancel:{auction_id}"

    @discord.ui.button(label="Bid", style=discord.ButtonStyle.success)
    async def bid_button(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        try:
            auction = await FeaturedAuction.objects.aget(pk=self.auction_id)
        except FeaturedAuction.DoesNotExist:
            await interaction.response.send_message("This auction no longer exists.", ephemeral=True)
            return
        if auction.status != FeaturedAuction.Status.ACTIVE:
            await interaction.response.send_message("This auction has already closed.", ephemeral=True)
            return
        if interaction.guild_id is not None and await services.is_blacklisted_bidder(
            interaction.user, interaction.guild_id
        ):
            await interaction.response.send_message("You're not allowed to bid on the auction house.", ephemeral=True)
            return
        minimum = (
            auction.current_bid + auction.min_bid_increment if auction.current_bid else auction.starting_bid
        )
        await interaction.response.send_modal(FeaturedBidModal(self.cog, self.auction_id, minimum))

    @discord.ui.button(label="Accept now", style=discord.ButtonStyle.primary)
    async def accept_button(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        """Creator-only: ends the auction immediately and awards it to the current highest bidder."""
        try:
            auction = await self.cog.accept_featured_now(self.auction_id, interaction.user.id)
        except RuntimeError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(
            "Accepted — sold to the current highest bidder!", ephemeral=True
        )
        await self.cog._render_featured_close(auction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        """Creator-only: cancels the auction, refunding the current bidder and the treasures."""
        try:
            auction = await self.cog.cancel_featured_now(self.auction_id, interaction.user.id)
        except RuntimeError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(
            "Cancelled — the current bid and treasures were refunded.", ephemeral=True
        )
        await self.cog._render_featured_close(auction)
