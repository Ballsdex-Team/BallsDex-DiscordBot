from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING, cast

import discord
from discord.ui import Button, Modal, View
from prometheus_client import Counter
from tortoise.timezone import now as datetime_now

from ballsdex.core.models import BallInstance, Player, specials
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.core.models import Special
    from ballsdex.packages.countryballs.countryball import CountryBall

log = logging.getLogger("ballsdex.packages.countryballs.components")
caught_balls = Counter(
    "caught_cb", "Caught countryballs", ["country", "shiny", "special", "guild_size"]
)


class CatchButton(Button):
    def __init__(self, ball: "CountryBall"):
        super().__init__(style=discord.ButtonStyle.primary, label="Pick me!")
        self.ball = ball

    async def callback(self, interaction: discord.Interaction):
        if self.ball.catched:
            await interaction.response.send_message(
                "Aw man someone picked this up before you", ephemeral=True
            )
        else:
            ball, has_caught_before = await self.catch_ball(interaction)
            special = ""
            if ball.shiny:
                special += f"✨ ***Its a {settings.collectible_name} from space!*** ✨\n"
            if ball.specialcard and ball.specialcard.catch_phrase:
                special += f"*{ball.specialcard.catch_phrase}*\n"
            if has_caught_before:
                special += (
                    f"This is a **new {settings.collectible_name}** ||is it?|| "
                    "that has been added to your amazing rock collection!"
                )
            await interaction.response.send_message(
                f"{interaction.user.mention} You picked up **{self.ball.name}!** "
                f"`(#{ball.pk:0X}, {ball.attack_bonus:+}%/{ball.health_bonus:+}%)`\n\n"
                f"{special}"
            )
            self.disabled = True
            await interaction.message.edit(view=self)

    async def catch_ball(self, interaction: discord.Interaction) -> tuple[BallInstance, bool]:
        player, created = await Player.get_or_create(discord_id=interaction.user.id)

        # stat may vary by +/- 20% of base stat
        bonus_attack = random.randint(-1, 1)
        bonus_health = random.randint(-1, 1)
        shiny = random.randint(1, 500) == 1

        # check if we can spawn cards with a special background
        special: "Special | None" = None
        population = [x for x in specials.values() if x.start_date <= datetime_now() <= x.end_date]
        if not shiny and population:
            common_weight = sum(1 - x.rarity for x in population)
            weights = [x.rarity for x in population] + [common_weight]
            special = random.choices(population=population + [None], weights=weights, k=1)[0]

        is_new = not await BallInstance.filter(player=player, ball=self.ball.model).exists()
        ball = await BallInstance.create(
            ball=self.ball.model,
            player=player,
            shiny=shiny,
            special=special,
            attack_bonus=bonus_attack,
            health_bonus=bonus_health,
            server_id=interaction.user.guild.id,
            spawned_time=self.ball.time,
        )
        if interaction.user.id in bot.catch_log:
            log.info(
                f"{interaction.user} picked {settings.collectible_name}"
                f" {self.ball.model}, {shiny=} {special=}",
            )
        else:
            log.debug(
                f"{interaction.user} picked {settings.collectible_name}"
                f" {self.ball.model}, {shiny=} {special=}",
            )
        if interaction.user.guild.member_count:
            caught_balls.labels(
                country=self.ball.model.country,
                shiny=shiny,
                special=special,
                guild_size=10
                ** math.ceil(math.log(max(interaction.user.guild.member_count - 1, 1), 10)),
            ).inc()
        return ball, is_new


class CatchView(View):
    def __init__(self, ball: "CountryBall"):
        super().__init__()
        self.ball = ball
        self.button = CatchButton(ball)
        self.add_item(self.button)

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"], /) -> bool:
        return await interaction.client.blacklist_check(interaction)

    async def on_timeout(self):
        self.button.disabled = True
        if self.ball.message:
            try:
                await self.ball.message.edit(view=self)
            except discord.HTTPException:
                pass
