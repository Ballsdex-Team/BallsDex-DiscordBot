import zipfile
from enum import StrEnum
from io import BytesIO
from typing import TYPE_CHECKING, NamedTuple, cast

import discord
from discord import ButtonStyle, SeparatorSpacing
from discord.ui import ActionRow, Button, Container, Label, Section, Select, Separator, TextDisplay, Thumbnail, button

from ballsdex.core.discord import Modal
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.menus import Formatter
from ballsdex.settings import settings
from bd_models.models import (
    Block,
    DonationPolicy,
    FriendPolicy,
    Friendship,
    MentionPolicy,
    Player,
    PrivacyPolicy,
    TradeCooldownPolicy,
)

from .utils import get_items_csv, get_trades_csv

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot

type Interaction = discord.Interaction["BallsDexBot"]


class Row(NamedTuple):
    row: ActionRow
    setting: str
    buttons: dict[int, Button]


class ExportCategory(StrEnum):
    BALLS = "balls"
    TRADES = "trades"
    ALL = "all"


class ExportModal(Modal, title="Data export"):
    category = Label(
        text="Category",
        description="Choose the type of data you want to export.",
        component=Select(
            options=[
                discord.SelectOption(
                    label=settings.collectible_name.title(),
                    description=f"Export all of your {settings.plural_collectible_name}.",
                    value=ExportCategory.BALLS,
                ),
                discord.SelectOption(
                    label="Trades", description="Export your trade history.", value=ExportCategory.TRADES
                ),
                discord.SelectOption(label="All", description="Export everything.", value=ExportCategory.ALL),
            ]
        ),
    )
    footer = TextDisplay(
        f"-# Check the [privacy policy]({settings.privacy_policy}) for more informations about your data."
    )

    async def on_submit(self, interaction: Interaction):
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        if player is None:
            await interaction.response.send_message("You don't have any player data to export.", ephemeral=True)
            return
        await interaction.response.defer()
        files: list[tuple[str, BytesIO]] = []
        category = cast(Select, self.category.component).values[0]
        if category == ExportCategory.BALLS or category == ExportCategory.ALL:
            data = await get_items_csv(player)
            filename = f"{interaction.user.id}_{settings.collectible_name}.csv"
            files.append((filename, data))
        if category == ExportCategory.TRADES or category == ExportCategory.ALL:
            data = await get_trades_csv(player)
            filename = f"{interaction.user.id}_trades.csv"
            files.append((filename, data))
        zip_file = BytesIO()
        with zipfile.ZipFile(zip_file, "w") as z:
            for filename, file in files:
                z.writestr(filename, file.getvalue())
        zip_file.seek(0)
        if zip_file.tell() > 25_000_000:
            await interaction.followup.send(
                "Your data is too large to export.Please contact the bot support for more information.", ephemeral=True
            )
            return
        try:
            await interaction.user.send("Here is your player data:", file=discord.File(zip_file, "player_data.zip"))
            await interaction.followup.send("Your player data has been sent via DMs.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "I couldn't send the player data to you in DM. "
                "Either you blocked me or you disabled DMs in this server.",
                ephemeral=True,
            )


class DataActionRow(ActionRow):
    @button(label="Export")
    async def export(self, interaction: Interaction, button: Button):
        """
        Export your player data.
        """
        await interaction.response.send_modal(ExportModal())

    @button(label="Delete all data")
    async def delete(self, interaction: Interaction, button: Button):
        view = ConfirmChoiceView(interaction)
        await interaction.response.send_message(
            "Are you sure you want to delete your player data?", view=view, ephemeral=True
        )
        await view.wait()
        if view.value is None or not view.value:
            return
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        if player:
            await player.adelete()


class SettingsContainer(Container):
    title = Section(
        TextDisplay(content="# Player settings"),
        TextDisplay(content="Configure your personal settings here"),
        accessory=Thumbnail(media=""),
    )
    sep1 = Separator(visible=True, spacing=SeparatorSpacing.small)
    inv_text = TextDisplay(content="### Inventory privacy\n-# Who should be able to view your inventory")
    inv_actions = ActionRow()

    donation_text = TextDisplay(
        content=f"### Donation policy\n-# Who should be able to donate {settings.plural_collectible_name}"
    )
    donation_actions = ActionRow()

    fr_text = TextDisplay(content="### Friend requests\n-# You can open or close all friend requests")
    fr_actions = ActionRow()

    trade_text = TextDisplay(
        content="### Trade cooldown\n-# Skip all cooldowns in trades if the other player also has this off"
    )
    trade_actions = ActionRow()

    mention_text = TextDisplay(content="### Mention policy\n-# Choose if you want to be mentioned by the bot or not")
    mention_actions = ActionRow()

    sep2 = Separator(visible=True, spacing=SeparatorSpacing.small)

    data_text = TextDisplay(content="## Your data")
    data_actions = DataActionRow()

    player: Player

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.player.discord_id:
            return True
        await interaction.response.send_message("You are not allowed to interact with this!", ephemeral=True)
        return False

    def configure(self, interaction: Interaction, player: Player):
        self.player = player
        self.title.accessory = discord.ui.Thumbnail(media=interaction.user.display_avatar.url)

        def button_callback(buttons: dict[int, Button], setting: str, value: int):
            async def callback(interaction: Interaction):
                for v, item in buttons.items():
                    if v == value:
                        item.disabled = True
                        item.style = ButtonStyle.primary
                    else:
                        item.disabled = False
                        item.style = ButtonStyle.secondary
                setattr(player, setting, value)
                await player.asave(update_fields=(setting,))
                await interaction.response.edit_message(view=self.view)

            return callback

        settings_buttons = [
            Row(
                self.inv_actions,
                "privacy_policy",
                {
                    PrivacyPolicy.ALLOW: Button(label="Open"),
                    PrivacyPolicy.DENY: Button(label="Private"),
                    PrivacyPolicy.FRIENDS: Button(label="Friends only"),
                    PrivacyPolicy.SAME_SERVER: Button(label="Same server"),
                },
            ),
            Row(
                self.donation_actions,
                "donation_policy",
                {
                    DonationPolicy.ALWAYS_ACCEPT: Button(label="Always accept"),
                    DonationPolicy.REQUEST_APPROVAL: Button(label="Needs approval"),
                    DonationPolicy.FRIENDS_ONLY: Button(label="Friends only"),
                    DonationPolicy.ALWAYS_DENY: Button(label="Closed"),
                },
            ),
            Row(
                self.fr_actions,
                "friend_policy",
                {FriendPolicy.ALLOW: Button(label="Open"), FriendPolicy.DENY: Button(label="Closed")},
            ),
            Row(
                self.trade_actions,
                "trade_cooldown_policy",
                {
                    TradeCooldownPolicy.COOLDOWN: Button(label="Wait 10s"),
                    TradeCooldownPolicy.BYPASS: Button(label="Bypass"),
                },
            ),
            Row(
                self.mention_actions,
                "mention_policy",
                {MentionPolicy.ALLOW: Button(label="Mentions"), MentionPolicy.DENY: Button(label="No mentions")},
            ),
        ]
        for row, setting, buttons in settings_buttons:
            for value, item in buttons.items():
                item.callback = button_callback(buttons, setting, value)
                if getattr(player, setting) == value:
                    item.disabled = True
                    item.style = ButtonStyle.primary
                row.add_item(item)


class RelationContainer(Container):
    title = TextDisplay("")
    sep1 = Separator()

    async def paginate_relations[M: Friendship | Block](self, qs: "QuerySet[M]", player: Player) -> list[list[Section]]:
        assert self.view
        if TYPE_CHECKING:
            assert isinstance(self.view, discord.ui.LayoutView)

        def get_button(relationship: M):
            b = Button(label="Remove", style=discord.ButtonStyle.secondary)

            async def button_callback(interaction: Interaction):
                # should be handled by the view's interaction_check, but just in case
                assert interaction.user.id == player.discord_id

                await interaction.response.defer()
                await relationship.adelete()
                b.disabled = True
                b.parent.children[0].content += "-# Removed"  # type: ignore
                await interaction.edit_original_response(view=self.view)

            b.callback = button_callback
            return b

        sections = []
        current_chunk = []
        async for x in qs:
            other = x.player2 if x.player1 == player else x.player2
            item = Section(TextDisplay(f"<@{other.discord_id}>"), accessory=get_button(x))
            self.add_item(item)
            current_chunk.append(item)
            if self.view.content_length() > 5900 or self.view.total_children_count > 30:
                sections.append(current_chunk)
                for old_item in current_chunk:
                    self.remove_item(old_item)
                current_chunk = []
        if current_chunk:
            sections.append(current_chunk)
            for old_item in current_chunk:
                self.remove_item(old_item)
        return sections


class RelationFormatter(Formatter["list[Section]", RelationContainer]):
    async def format_page(self, page: "list[Section]") -> None:
        for i, item in enumerate(self.item.children):
            if i > 1:
                self.item.remove_item(item)
        for section in page:
            self.item.add_item(section)
        if self.menu.source.get_max_pages() > 1:
            self.item.add_item(TextDisplay(f"-# Page {self.menu.current_page + 1}/{self.menu.source.get_max_pages()}"))
