from typing import TYPE_CHECKING, Optional

import discord
from discord.ui import Button, button

from ballsdex.core.discord import View
from ballsdex.core.translation import current_locale, t
from bd_models.models import GuildConfig
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class AcceptTOSView(View):
    """
    Button prompting the admin setting up the bot to accept the terms of service.
    """

    def __init__(
        self, interaction: discord.Interaction["BallsDexBot"], channel: discord.TextChannel, new_player: discord.Member
    ):
        super().__init__()
        self.original_interaction = interaction
        self.channel = channel
        self.new_player = new_player
        self.message: Optional[discord.Message] = None

        self.add_item(
            Button(style=discord.ButtonStyle.link, label=t("Terms of Service"), url=settings.terms_of_service)
        )
        self.add_item(Button(style=discord.ButtonStyle.link, label=t("Privacy policy"), url=settings.privacy_policy))
        # `@button()` labels are resolved once at class-body (import) time, so the decorator
        # below keeps a static English default - override it here instead, where `t()` can see
        # the locale of whoever is running the /config channel command that creates this view.
        self.accept_button.label = t("Accept")

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"]) -> bool:
        current_locale.set(interaction.locale.value)
        if interaction.user.id != self.new_player.id:
            await interaction.response.send_message(
                t("You are not allowed to interact with this menu."), ephemeral=True
            )
            return False
        return True

    @button(label="Accept", style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}")
    async def accept_button(self, interaction: discord.Interaction["BallsDexBot"], button: discord.ui.Button):
        config, created = await GuildConfig.objects.aget_or_create(guild_id=interaction.guild_id)
        config.spawn_channel = self.channel.id  # type: ignore
        config.enabled = True
        await config.asave()
        interaction.client.dispatch("ballsdex_settings_change", interaction.guild, channel=self.channel, enabled=True)
        self.stop()
        if self.message:
            button.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
        await interaction.response.send_message(
            t(
                "The new spawn channel was successfully set to {channel}.\n"
                "{collectibles} will start spawning as users talk unless the bot is disabled."
            ).format(channel=self.channel.mention, collectibles=settings.collectible_name.title() + "s")
        )

    async def on_timeout(self) -> None:
        if self.message:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
