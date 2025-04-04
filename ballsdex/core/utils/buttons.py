from typing import TYPE_CHECKING, Optional

import discord
from discord.ui import Button, View

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class ConfirmChoiceView(View):
    def __init__(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: Optional[discord.User] = None,
        accept_message: str = "Confirmed",
        cancel_message: str = "Cancelled",
    ):
        super().__init__(timeout=90)
        self.value = None
        self.interaction = interaction
        self.user = user or interaction.user
        self.interaction_response: discord.Interaction["BallsDexBot"]
        self.accept_message = accept_message
        self.cancel_message = cancel_message

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"]) -> bool:
        self.interaction_response = interaction

        if interaction.user != self.user:
            await interaction.response.send_message(
                "You cannot interact with this view.", ephemeral=True
            )
            return False

        if self.value is not None:
            await interaction.response.send_message(
                "You've already made a choice.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True  # type: ignore
        try:
            await self.interaction.followup.edit_message("@original", view=self)  # type: ignore
        except discord.NotFound:
            pass

    @discord.ui.button(
        style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}"
    )
    async def confirm_button(
        self, interaction: discord.Interaction["BallsDexBot"], button: Button
    ):
        for item in self.children:
            item.disabled = True  # type: ignore

        if interaction.message:
            content = interaction.message.content or ""
        else:
            content = ""

        await interaction.response.edit_message(
            content=f"{content}\n{self.accept_message}", view=self
        )

        self.value = True
        self.stop()

    @discord.ui.button(
        style=discord.ButtonStyle.danger,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
    )
    async def cancel_button(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        for item in self.children:
            item.disabled = True  # type: ignore

        if interaction.message:
            content = interaction.message.content or ""
        else:
            content = ""

        await interaction.response.edit_message(
            content=f"{content}\n{self.cancel_message}", view=self
        )

        self.value = False
        self.stop()
