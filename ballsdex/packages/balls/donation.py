import enum
from typing import TYPE_CHECKING

import discord
from discord.ui import Button, button

from ballsdex.core.discord import View
from ballsdex.core.translation import current_locale, t
from ballsdex.core.utils.menus import Menu
from bd_models.enums import DonationPolicy
from bd_models.models import BallInstance, Player, Trade, TradeObject
from settings.models import settings

from .countryballs_paginator import CountryballsViewer

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

type Interaction = discord.Interaction["BallsDexBot"]


class GiveSkipReason(enum.StrEnum):
    NOT_TRADEABLE = "no longer tradeable"
    LOCKED = "locked for another trade"


async def check_giveable(countryball: BallInstance) -> GiveSkipReason | None:
    """
    Check whether a countryball can currently be given away, independent of the recipient.
    """
    if not countryball.is_tradeable:
        return GiveSkipReason.NOT_TRADEABLE
    if await countryball.is_locked():
        return GiveSkipReason.LOCKED
    return None


async def check_recipient(bot: "BallsDexBot", new_player: Player, old_player: Player) -> str | None:
    """
    Check whether old_player may donate to new_player at all, independent of which countryball(s)
    are involved. Returns a user-facing error message, or None if the donation is allowed.
    """
    if new_player == old_player:
        return t("You cannot give a {collectible} to yourself.").format(collectible=settings.collectible_name)
    if new_player.donation_policy == DonationPolicy.ALWAYS_DENY:
        return t("This player does not accept donations. You can use trades instead.")
    if new_player.donation_policy == DonationPolicy.FRIENDS_ONLY:
        if not await new_player.is_friend(old_player):
            return t("This player only accepts donations from friends, use trades instead.")
    if await new_player.is_blocked(old_player):
        return t("You cannot interact with a user that has blocked you.")
    if new_player.discord_id in bot.blacklist:
        return t("You cannot donate to a blacklisted user.")
    return None


VIEW_ALL_CUSTOM_ID = "bulk_give:view_all"


def add_view_all_button(
    view: View, bot: "BallsDexBot", ball_ids: list[int], *, sender_id: int, recipient_id: int
) -> None:
    """
    Attach a "View All" button to a view. Clicking it opens a paginated, ephemeral browser of the
    given countryballs (same select-and-inspect menu used by `/balls list`), private to whoever
    clicked it. Both the sender and the recipient of the donation may click it; anyone else is
    rejected.

    If `view`'s own `interaction_check` would otherwise restrict interactions to a single user
    (e.g. `BulkDonationRequest`), it should let this button through by checking
    `interaction.data["custom_id"] == VIEW_ALL_CUSTOM_ID` - the permission check happens here
    instead, in the callback.
    """

    async def callback(interaction: Interaction):
        if interaction.user.id not in (sender_id, recipient_id):
            await interaction.response.send_message(
                t("You are not allowed to interact with this menu."), ephemeral=True
            )
            return
        queryset = BallInstance.objects.filter(id__in=ball_ids).order_by("-id")
        viewer = CountryballsViewer()
        viewer.restrict_author(interaction.user.id)
        menu = Menu.countryballs(bot, viewer, viewer.selected, queryset)
        await menu.init(position=2)
        viewer.header.content = (
            t("Viewing what you received") if interaction.user.id == recipient_id else t("Viewing what you gave")
        )
        await interaction.response.send_message(view=viewer, ephemeral=True)

    item = Button(label=t("View All"), style=discord.ButtonStyle.blurple, custom_id=VIEW_ALL_CUSTOM_ID)
    item.callback = callback
    view.add_item(item)


class DonationRequest(View):
    def __init__(self, bot: "BallsDexBot", interaction: Interaction, countryball: BallInstance, new_player: Player):
        super().__init__(timeout=120)
        self.bot = bot
        self.original_interaction = interaction
        self.countryball = countryball
        self.new_player = new_player

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        current_locale.set(interaction.locale.value)
        if interaction.user.id != self.new_player.discord_id:
            await interaction.response.send_message(
                t("You are not allowed to interact with this menu."), ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True  # type: ignore
        try:
            await self.original_interaction.edit_original_response(view=self)
        except discord.NotFound:
            pass
        await self.countryball.unlock()

    @button(style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}")
    async def accept(self, interaction: Interaction, button: Button):
        self.stop()
        for item in self.children:
            item.disabled = True  # type: ignore
        self.countryball.favorite = False
        self.countryball.trade_player = self.countryball.player
        self.countryball.player = self.new_player
        await self.countryball.asave()
        trade = await Trade.objects.acreate(player1=self.countryball.trade_player, player2=self.new_player)
        await TradeObject.objects.acreate(
            trade=trade, ballinstance=self.countryball, player=self.countryball.trade_player
        )
        await interaction.response.edit_message(
            content=interaction.message.content  # type: ignore
            + "\n\N{WHITE HEAVY CHECK MARK} "
            + t("The donation was accepted!"),
            view=self,
        )
        await self.countryball.unlock()

    @button(style=discord.ButtonStyle.danger, emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}")
    async def deny(self, interaction: Interaction, button: Button):
        self.stop()
        for item in self.children:
            item.disabled = True  # type: ignore
        await interaction.response.edit_message(
            content=interaction.message.content  # type: ignore
            + "\n\N{CROSS MARK} "
            + t("The donation was denied."),
            view=self,
        )
        await self.countryball.unlock()


class BulkDonationRequest(View):
    def __init__(
        self,
        bot: "BallsDexBot",
        interaction: Interaction,
        countryballs: list[BallInstance],
        new_player: Player,
        old_player: Player,
    ):
        super().__init__(timeout=120)
        self.bot = bot
        self.original_interaction = interaction
        self.countryballs = countryballs
        self.new_player = new_player
        self.old_player = old_player

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        current_locale.set(interaction.locale.value)
        if interaction.data and interaction.data.get("custom_id") == VIEW_ALL_CUSTOM_ID:
            return True
        if interaction.user.id != self.new_player.discord_id:
            await interaction.response.send_message(
                t("You are not allowed to interact with this menu."), ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True  # type: ignore
        try:
            await self.original_interaction.edit_original_response(view=self)
        except discord.NotFound:
            pass
        for countryball in self.countryballs:
            await countryball.unlock()

    @button(style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}")
    async def accept(self, interaction: Interaction, button: Button):
        self.stop()
        for item in self.children:
            item.disabled = True  # type: ignore
        trade = await Trade.objects.acreate(player1=self.old_player, player2=self.new_player)
        for countryball in self.countryballs:
            countryball.favorite = False
            countryball.trade_player = self.old_player
            countryball.player = self.new_player
            await countryball.asave()
            await TradeObject.objects.acreate(trade=trade, ballinstance=countryball, player=self.old_player)
            await countryball.unlock()
        add_view_all_button(
            self,
            self.bot,
            [countryball.pk for countryball in self.countryballs],
            sender_id=self.old_player.discord_id,
            recipient_id=self.new_player.discord_id,
        )
        await interaction.response.edit_message(
            content=(interaction.message.content if interaction.message else "")
            + "\n\N{WHITE HEAVY CHECK MARK} "
            + t("The donation of {count} {collectibles} was accepted!").format(
                count=len(self.countryballs), collectibles=settings.plural_collectible_name
            ),
            view=self,
        )

    @button(style=discord.ButtonStyle.danger, emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}")
    async def deny(self, interaction: Interaction, button: Button):
        self.stop()
        for item in self.children:
            item.disabled = True  # type: ignore
        await interaction.response.edit_message(
            content=(interaction.message.content if interaction.message else "")
            + "\n\N{CROSS MARK} "
            + t("The donation was denied."),
            view=self,
        )
        for countryball in self.countryballs:
            await countryball.unlock()
