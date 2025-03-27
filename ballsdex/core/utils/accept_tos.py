from typing import Optional

import discord
from discord.ui import Button, View, button

from ballsdex.core.models import Player
from ballsdex.settings import settings


def activation_embed() -> discord.Embed:
    return discord.Embed(
        colour=0x00D936,
        title=f"{settings.bot_name} activation",
        description=(
            f"To start using {settings.bot_name}, you must "
            f"read and accept the [Terms of Service]({settings.terms_of_service}).\n\n"
            "As a summary, these are the rules of the bot:\n"
            f"- No farming (spamming or creating servers for {settings.plural_collectible_name})\n"
            f"- Selling or exchanging {settings.plural_collectible_name} "
            "against money or other goods is forbidden\n"
            "- Do not attempt to abuse the bot's internals\n"
            "**Not respecting these rules will lead to a blacklist.**"
        ),
    )


class UserAcceptTOS(View):
    """
    Button prompting the user to accept the terms of service.
    """

    def __init__(self, interaction: discord.Interaction):
        super().__init__()
        self.original_interaction = interaction
        self.message: Optional[discord.Message] = None

        self.add_item(
            Button(
                style=discord.ButtonStyle.link,
                label="Terms of Service",
                url=settings.terms_of_service,
            )
        )
        self.add_item(
            Button(
                style=discord.ButtonStyle.link,
                label="Privacy policy",
                url=settings.privacy_policy,
            )
        )

    @button(
        label="Accept",
        style=discord.ButtonStyle.success,
        emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}",
    )
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await Player.filter(discord_id=interaction.user.id).update(accepted_tos=True)
        await interaction.response.send_message(
            "You have accepted the terms of service, you can now continue with playing the bot.",
            ephemeral=True,
        )
        self.stop()

        if self.message:
            button.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_timeout(self) -> None:
        if self.message:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
