from __future__ import annotations
import discord

from typing import TYPE_CHECKING
from discord.ui import Modal, TextInput, Button, View

from ballsdex.core.models import Player, BallInstance

if TYPE_CHECKING:
    from ballsdex.packages.countryballs.countryball import CountryBall


class CountryballNamePrompt(Modal, title="Catch this countryball!"):
    name = TextInput(
        label="Name of this country", style=discord.TextStyle.short, placeholder="Your guess"
    )

    def __init__(self, ball: "CountryBall", button: CatchButton):
        super().__init__()
        self.ball = ball
        self.button = button

    async def on_submit(self, interaction: discord.Interaction):
        # TODO: use lock
        if self.ball.catched:
            await interaction.response.send_message(
                f"{interaction.user.mention} I was caught already!"
            )
            return
        if self.name.value.lower() == self.ball.name.lower():
            self.ball.catched = True
            await self.catch_ball(interaction.user)
            await interaction.response.send_message(
                f"{interaction.user.mention} You caught **{self.ball.name}!**"
            )
            self.button.disabled = True
            await interaction.followup.edit_message(self.ball.message.id, view=self.button.view)
        else:
            await interaction.response.send_message(f"{interaction.user.mention} Wrong name!")

    async def catch_ball(self, user: discord.abc.User):
        player, created = await Player.get_or_create(discord_id=user.id)
        await player.fetch_related("balls")
        await BallInstance.create(
            ball=self.ball.model, player=player, count=(await player.balls.all().count()) + 1
        )


class CatchButton(Button):
    def __init__(self, ball: "CountryBall"):
        super().__init__(style=discord.ButtonStyle.primary, label="Catch me!")
        self.ball = ball

    async def callback(self, interaction: discord.Interaction):
        if self.ball.catched:
            await interaction.response.send_message("I was caught already!", ephemeral=True)
        else:
            await interaction.response.send_modal(CountryballNamePrompt(self.ball, self))


class CatchView(View):
    def __init__(self, ball: "CountryBall"):
        super().__init__()
        self.ball = ball
        self.button = CatchButton(ball)
        self.add_item(self.button)

    async def on_timeout(self):
        self.button.disabled = True
        if self.ball.message:
            await self.ball.message.edit(view=self)
