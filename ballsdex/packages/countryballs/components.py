from __future__ import annotations
import discord
import random
import logging

from typing import TYPE_CHECKING, cast
from discord.ui import Modal, TextInput, Button, View

from ballsdex.core.models import Player, BallInstance

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.core.models import Special
    from ballsdex.packages.countryballs.countryball import CountryBall

log = logging.getLogger("ballsdex.packages.countryballs.components")


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
        if self.name.value.lower().strip() == self.ball.name.lower():
            self.ball.catched = True
            ball = await self.catch_ball(cast("BallsDexBot", interaction.client), interaction.user)

            special = ""
            if ball.shiny:
                special += "✨ ***It's a shiny countryball !*** ✨\n"
            if ball.special and ball.special.catch_phrase:
                special += f"*{ball.special.catch_phrase}*\n"

            await interaction.response.send_message(
                f"{interaction.user.mention} You caught **{self.ball.name}!**\n\n{special}",
            )
            self.button.disabled = True
            await interaction.followup.edit_message(self.ball.message.id, view=self.button.view)
        else:
            await interaction.response.send_message(f"{interaction.user.mention} Wrong name!")

    async def catch_ball(self, bot: "BallsDexBot", user: discord.abc.User) -> BallInstance:
        player, created = await Player.get_or_create(discord_id=user.id)
        await player.fetch_related("balls")

        # stat may vary by +/- 20% of base stat
        bonus_attack = random.randint(-20, 20)
        bonus_health = random.randint(-20, 20)
        shiny = random.randint(1, 2048) == 1

        # check if we can spawn cards with a special background
        special: "Special" | None = None
        if not shiny and bot.special_cache:
            # calculate the average rarity of all current events to determine the weight of a
            # common countryball. If average=1, no common countryball may spawn, average=0.5 means
            # half common half special, and average=0 means only commons
            weights = [x.rarity for x in bot.special_cache]
            average_rarity = sum(weights) / len(bot.special_cache)
            common_ball_weight = 1 - average_rarity

            population = list(range(-1, len(bot.special_cache)))  # picking -1 = common
            index = random.choices(
                population=population,
                weights=weights + [common_ball_weight],
                k=1,
            )[0]
            if index != -1:  # not common
                special = bot.special_cache[index]

        log.debug(f"{user} caught countryball {self.ball.model}, {shiny=} {special=}")

        return await BallInstance.create(
            ball=self.ball.model,
            player=player,
            count=(await player.balls.all().count()) + 1,
            shiny=shiny,
            special=special,
            attack_bonus=bonus_attack,
            health_bonus=bonus_health,
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

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        bot = cast("BallsDexBot", interaction.client)
        return await bot.blacklist_check(interaction)

    async def on_timeout(self):
        self.button.disabled = True
        if self.ball.message:
            await self.ball.message.edit(view=self)
