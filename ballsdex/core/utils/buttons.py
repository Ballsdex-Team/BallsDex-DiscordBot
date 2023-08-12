import discord

from discord.ui import View, Button


class ConfirmChoiceView(View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=90)
        self.value = None
        self.interaction = interaction

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.interaction.user:
            await interaction.response.send_message(
                "Only the original author can use this.", ephemeral=True
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
            item.disabled = True
        try:
            await self.interaction.followup.edit_message("@original", view=self)
        except discord.NotFound:
            pass

    @discord.ui.button(
        style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}"
    )
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=interaction.message.content + "\nConfirmed", view=self
        )
        self.value = True
        self.stop()

    @discord.ui.button(
        style=discord.ButtonStyle.danger,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
    )
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=interaction.message.content + "\nCancelled", view=self
        )
        self.value = False
        self.stop()
