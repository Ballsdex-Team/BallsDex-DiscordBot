import random
import string
import zipfile
from collections.abc import AsyncIterable
from enum import StrEnum
from io import BytesIO
from typing import TYPE_CHECKING, NamedTuple, cast

import discord
from discord import ButtonStyle, SeparatorSpacing
from discord.ui import (
    ActionRow,
    Button,
    Container,
    Label,
    Section,
    Select,
    Separator,
    TextDisplay,
    TextInput,
    Thumbnail,
    button,
)

from ballsdex.core.discord import Modal
from ballsdex.core.translation import current_locale, t
from ballsdex.core.utils.buttons import ConfirmChoiceView
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
from settings.models import settings

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

    def __init__(self):
        super().__init__()
        # class-level `title=`/Label/TextDisplay content above is resolved once at import time -
        # override it here so t() sees the locale of whoever opened this modal
        self.title = t("Data export")
        self.category.text = t("Category")
        self.category.description = t("Choose the type of data you want to export.")
        select = cast(Select, self.category.component)
        select.options[0].label = settings.collectible_name.title()
        select.options[0].description = t("Export all of your {collectibles}.").format(
            collectibles=settings.plural_collectible_name
        )
        select.options[1].label = t("Trades")
        select.options[1].description = t("Export your trade history.")
        select.options[2].label = t("All")
        select.options[2].description = t("Export everything.")
        self.footer.content = t("-# Check the [privacy policy]({url}) for more informations about your data.").format(
            url=settings.privacy_policy
        )

    async def on_submit(self, interaction: Interaction):
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        if player is None:
            await interaction.response.send_message(t("You don't have any player data to export."), ephemeral=True)
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
                t("Your data is too large to export. Please contact the bot support for more information."),
                ephemeral=True,
            )
            return
        try:
            await interaction.user.send(t("Here is your player data:"), file=discord.File(zip_file, "player_data.zip"))
            await interaction.followup.send(t("Your player data has been sent via DMs."), ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                t(
                    "I couldn't send the player data to your DMs. "
                    "Either you blocked me or you disabled DMs in this server."
                ),
                ephemeral=True,
            )


CONFIRMATION_CODE_CHARS = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1IL")


class DeleteDataModal(Modal, title="Confirm data deletion"):
    confirmation = Label(
        text="Confirmation code", component=TextInput(style=discord.TextStyle.short, placeholder="Confirmation code")
    )

    def __init__(self, code: str):
        super().__init__()
        self.code = code
        # class-level `title=`/Label content above is resolved once at import time - override
        # it here so t() sees the locale of whoever opened this modal
        self.title = t("Confirm data deletion")
        self.confirmation.text = t("Confirmation code")
        cast(TextInput, self.confirmation.component).placeholder = t("Confirmation code")
        self.confirmation.description = t(
            "This will permanently delete all of your data and cannot be undone. Type {code} below to confirm."
        ).format(code=code)

    async def on_submit(self, interaction: Interaction):
        value = cast(TextInput, self.confirmation.component).value.strip().upper()
        if value != self.code:
            await interaction.response.send_message(
                t("The code you entered did not match. Your data was **not** deleted."), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        if player:
            await player.adelete()
        await interaction.followup.send(t("Your player data has been permanently deleted."), ephemeral=True)


class DataActionRow(ActionRow):
    # @button() labels are resolved once at class-body (import) time - this row is itself a
    # class-level attribute of SettingsContainer (constructed at import time too), so labels
    # are overridden from SettingsContainer.configure() instead, where the locale is known

    @button(label="Export")
    async def export(self, interaction: Interaction, button: Button):
        """
        Export your player data.
        """
        await interaction.response.send_modal(ExportModal())

    @button(label="Delete all data")
    async def delete(self, interaction: Interaction, button: Button):
        code = "".join(random.choices(CONFIRMATION_CODE_CHARS, k=6))
        await interaction.response.send_modal(DeleteDataModal(code))


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

    language_text = TextDisplay(
        content=f"### Language\n-# Choose the language {settings.plural_collectible_name} are displayed in"
    )
    language_actions = ActionRow()

    sep2 = Separator(visible=True, spacing=SeparatorSpacing.small)

    data_text = TextDisplay(content="## Your data")
    data_actions = DataActionRow()

    player: Player

    DEFAULT_LANGUAGE_VALUE = "__default__"

    async def interaction_check(self, interaction: Interaction) -> bool:
        current_locale.set(interaction.locale.value)
        if interaction.user.id == self.player.discord_id:
            return True
        await interaction.response.send_message(t("You are not allowed to interact with this!"), ephemeral=True)
        return False

    def configure(self, interaction: Interaction, player: Player):
        self.player = player
        self.title.accessory = discord.ui.Thumbnail(media=interaction.user.display_avatar.url)

        # class-level TextDisplay/Section content above is resolved once at import time -
        # override it here, in a method that only ever runs per-interaction
        cast(TextDisplay, self.title.children[0]).content = t("# Player settings")
        cast(TextDisplay, self.title.children[1]).content = t("Configure your personal settings here")
        self.inv_text.content = t("### Inventory privacy\n-# Who should be able to view your inventory")
        self.donation_text.content = t("### Donation policy\n-# Who should be able to donate {collectibles}").format(
            collectibles=settings.plural_collectible_name
        )
        self.fr_text.content = t("### Friend requests\n-# You can open or close all friend requests")
        self.trade_text.content = t(
            "### Trade cooldown\n-# Skip all cooldowns in trades if the other player also has this off"
        )
        self.mention_text.content = t("### Mention policy\n-# Choose if you want to be mentioned by the bot or not")
        self.language_text.content = t("### Language\n-# Choose the language {collectibles} are displayed in").format(
            collectibles=settings.plural_collectible_name
        )
        self.data_text.content = t("## Your data")
        self.data_actions.export.label = t("Export")
        self.data_actions.delete.label = t("Delete all data")

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
                    PrivacyPolicy.ALLOW: Button(label=t("Open")),
                    PrivacyPolicy.DENY: Button(label=t("Private")),
                    PrivacyPolicy.FRIENDS: Button(label=t("Friends only")),
                    PrivacyPolicy.SAME_SERVER: Button(label=t("Same server")),
                },
            ),
            Row(
                self.donation_actions,
                "donation_policy",
                {
                    DonationPolicy.ALWAYS_ACCEPT: Button(label=t("Always accept")),
                    DonationPolicy.REQUEST_APPROVAL: Button(label=t("Needs approval")),
                    DonationPolicy.FRIENDS_ONLY: Button(label=t("Friends only")),
                    DonationPolicy.ALWAYS_DENY: Button(label=t("Closed")),
                },
            ),
            Row(
                self.fr_actions,
                "friend_policy",
                {FriendPolicy.ALLOW: Button(label=t("Open")), FriendPolicy.DENY: Button(label=t("Closed"))},
            ),
            Row(
                self.trade_actions,
                "trade_cooldown_policy",
                {
                    TradeCooldownPolicy.COOLDOWN: Button(label=t("Wait 10s")),
                    TradeCooldownPolicy.BYPASS: Button(label=t("Bypass")),
                },
            ),
            Row(
                self.mention_actions,
                "mention_policy",
                {MentionPolicy.ALLOW: Button(label=t("Mentions")), MentionPolicy.DENY: Button(label=t("No mentions"))},
            ),
        ]
        for row, setting, buttons in settings_buttons:
            for value, item in buttons.items():
                item.callback = button_callback(buttons, setting, value)
                if getattr(player, setting) == value:
                    item.disabled = True
                    item.style = ButtonStyle.primary
                row.add_item(item)

        current_language = player.language or self.DEFAULT_LANGUAGE_VALUE
        language_select = Select(
            placeholder=t("Select a language"),
            options=[
                discord.SelectOption(
                    label=t("Server / bot default"),
                    value=self.DEFAULT_LANGUAGE_VALUE,
                    default=current_language == self.DEFAULT_LANGUAGE_VALUE,
                ),
                *(
                    discord.SelectOption(label=language, value=language, default=language == current_language)
                    for language in settings.available_languages[:24]
                ),
            ],
        )

        async def language_callback(interaction: Interaction):
            value = language_select.values[0]
            player.language = None if value == self.DEFAULT_LANGUAGE_VALUE else value
            await player.asave(update_fields=("language",))
            for option in language_select.options:
                option.default = option.value == value
            await interaction.response.edit_message(view=self.view)

        language_select.callback = language_callback
        self.language_actions.add_item(language_select)


class RelationContainer(Container):
    title = TextDisplay("")
    sep1 = Separator()

    async def paginate_relations[M: Friendship | Block](
        self, qs: "QuerySet[M]", player: Player
    ) -> AsyncIterable[Section]:
        assert self.view
        if TYPE_CHECKING:
            assert isinstance(self.view, discord.ui.LayoutView)

        def get_button(relationship: M):
            b = Button(label=t("Remove"), style=discord.ButtonStyle.secondary)

            async def button_callback(interaction: Interaction):
                # should be handled by the view's interaction_check, but just in case
                assert interaction.user.id == player.discord_id

                await interaction.response.defer(ephemeral=True)
                view = ConfirmChoiceView(interaction)
                prompt = (
                    t("Are you sure you want to remove this friend?")
                    if isinstance(relationship, Friendship)
                    else t("Are you sure you want to remove this block?")
                )
                await interaction.followup.send(prompt, view=view, ephemeral=True)
                await view.wait()
                if view.value is not True:
                    return
                await relationship.adelete()
                b.disabled = True
                b.parent.children[0].content += t("-# Removed")  # type: ignore
                await interaction.edit_original_response(view=self.view)

            b.callback = button_callback
            return b

        async for x in qs:
            other = x.player2 if x.player1 == player else x.player1
            yield Section(TextDisplay(f"<@{other.discord_id}>"), accessory=get_button(x))
