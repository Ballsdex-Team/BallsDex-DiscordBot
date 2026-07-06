from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands
from discord.ui import Button

from ballsdex.core.discord import View
from ballsdex.core.translation import current_locale, t

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class ConfirmChoiceView(View):
    """
    An utility to prompt the user for confirmation.

    Parameters
    ----------
    ctx: Interaction[BallsDexBot] | commands.Context[BallsDexBot]
        Either a context or interaction.
    user: discord.User | None
        The user you're interacting with. If `None`, then `interaction.user` is used.
    accept_message: str
        The message appended to the message's content if the prompt is accepted.
    cancel_message: str
        The message appended to the message's content if the prompt is refused.

    Attributes
    ----------
    value: bool | None
        The user's choice. `None` if the interaction timed out or didn't finish. Call [`wait()`][discord.ui.View.wait]
        first.

    Example
    -------
        view = ConfirmChoiceView(interaction)
        await interaction.response.send_message("Are you sure?", view=view)
        await view.wait()
        if view.value is True:
            # user accepted
        elif view.value is False:
            # user denied
        elif view.value is None:
            # timed out
    """

    def __init__(
        self,
        ctx: discord.Interaction["BallsDexBot"] | commands.Context["BallsDexBot"],
        user: Optional[discord.User] = None,
        accept_message: Optional[str] = None,
        cancel_message: Optional[str] = None,
    ):
        super().__init__(timeout=90)
        self.value = None
        if isinstance(ctx, discord.Interaction):
            self.interaction = ctx
            self.user = user or ctx.user
        else:
            self.interaction = ctx.interaction
            self.user = user or ctx.author
        self.interaction_response: discord.Interaction["BallsDexBot"]
        # resolved here rather than as default parameter values, since those are evaluated once
        # at import time and would always resolve to English
        self.accept_message = accept_message if accept_message is not None else t("Confirmed")
        self.cancel_message = cancel_message if cancel_message is not None else t("Cancelled")
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"]) -> bool:
        current_locale.set(interaction.locale.value)
        self.interaction_response = interaction

        if interaction.user != self.user:
            await interaction.response.send_message(t("You cannot interact with this view."), ephemeral=True)
            return False

        if self.value is not None:
            await interaction.response.send_message(t("You've already made a choice."), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True  # type: ignore
        try:
            if self.interaction:
                await self.interaction.edit_original_response(view=self)
            elif self.message:
                await self.message.edit(view=self)
        except discord.NotFound:
            pass

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}")
    async def confirm_button(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        for item in self.children:
            item.disabled = True  # type: ignore

        if interaction.message:
            content = interaction.message.content or ""
        else:
            content = ""

        await interaction.response.edit_message(content=f"{content}\n{self.accept_message}", view=self)

        self.value = True
        self.stop()

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}")
    async def cancel_button(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        for item in self.children:
            item.disabled = True  # type: ignore

        if interaction.message:
            content = interaction.message.content or ""
        else:
            content = ""

        await interaction.response.edit_message(content=f"{content}\n{self.cancel_message}", view=self)

        self.value = False
        self.stop()
