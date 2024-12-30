from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING, cast

import discord
from discord.ui import Button, Modal, TextInput, View, button
from tortoise.timezone import now as datetime_now

from ballsdex.core.metrics import caught_balls
from ballsdex.core.models import BallInstance, Player, specials
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.core.models import Special
    from ballsdex.packages.countryballs.countryball import CountryBall

log = logging.getLogger("ballsdex.packages.countryballs.components")


class CountryballNamePrompt(Modal, title=f"Catch this {settings.collectible_name}!"):
    name = TextInput(
        label=f"Name of this {settings.collectible_name}",
        style=discord.TextStyle.short,
        placeholder="Your guess",
    )

    def __init__(self, ball: "CountryBall", button: Button):
        super().__init__()
        self.ball = ball
        self.button = button

    async def on_error(self, interaction: discord.Interaction, error: Exception, /) -> None:
        log.exception("An error occured in countryball catching prompt", exc_info=error)
        if interaction.response.is_done():
            await interaction.followup.send(
                f"An error occured with this {settings.collectible_name}.",
            )
        else:
            await interaction.response.send_message(
                f"An error occured with this {settings.collectible_name}.",
            )

    async def on_submit(self, interaction: discord.Interaction["BallsDexBot"]):
        # TODO: use lock
        await interaction.response.defer(thinking=True)

        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        if self.ball.catched:
            await interaction.followup.send(
                f"{interaction.user.mention} I was caught already!",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=player.can_be_mentioned),
            )
            return

        if self.ball.model.catch_names:
            possible_names = (self.ball.name.lower(), *self.ball.model.catch_names.split(";"))
        else:
            possible_names = (self.ball.name.lower(),)
        if self.ball.model.translations:
            possible_names += tuple(x.lower() for x in self.ball.model.translations.split(";"))

        if self.name.value.lower().strip() in possible_names:
            self.ball.catched = True
            ball, has_caught_before = await self.catch_ball(
                interaction.client, cast(discord.Member, interaction.user)
            )

            special = ""
            if ball.shiny:
                special += f"✨ ***It's a shiny {settings.collectible_name}!*** ✨\n"
            if ball.specialcard and ball.specialcard.catch_phrase:
                special += f"*{ball.specialcard.catch_phrase}*\n"
            if has_caught_before:
                special += (
                    f"This is a **new {settings.collectible_name}** "
                    "that has been added to your completion!"
                )
            await interaction.followup.send(
                f"{interaction.user.mention} You caught **{self.ball.name}!** "
                f"`(#{ball.pk:0X}, {ball.attack_bonus:+}%/{ball.health_bonus:+}%)`\n\n"
                f"{special}",
                allowed_mentions=discord.AllowedMentions(users=player.can_be_mentioned),
            )
            self.button.disabled = True
            await interaction.followup.edit_message(self.ball.message.id, view=self.button.view)
        else:
            await interaction.followup.send(
                f"{interaction.user.mention} Wrong name!",
                allowed_mentions=discord.AllowedMentions(users=player.can_be_mentioned),
                ephemeral=False,
            )

    async def catch_ball(
        self, bot: "BallsDexBot", user: discord.Member
    ) -> tuple[BallInstance, bool]:
        player, created = await Player.get_or_create(discord_id=user.id)

        # stat may vary by +/- 20% of base stat
        bonus_attack = self.ball.atk_bonus or random.randint(
            -settings.max_attack_bonus, settings.max_attack_bonus
        )
        bonus_health = self.ball.hp_bonus or random.randint(
            -settings.max_health_bonus, settings.max_health_bonus
        )
        shiny = self.ball.shiny or random.randint(1, 2048) == 1

        # check if we can spawn cards with a special background
        special: "Special | None" = None if shiny else self.ball.special
        population = [x for x in specials.values() if x.start_date <= datetime_now() <= x.end_date]
        if not special and not shiny and population:
            # Here we try to determine what should be the chance of having a common card
            # since the rarity field is a value between 0 and 1, 1 being no common
            # and 0 only common, we get the remaining value by doing (1-rarity)
            # We then sum each value for each current event, and we should get an algorithm
            # that kinda makes sense.
            common_weight = sum(1 - x.rarity for x in population)

            weights = [x.rarity for x in population] + [common_weight]
            # None is added representing the common countryball
            special = random.choices(population=population + [None], weights=weights, k=1)[0]

        is_new = not await BallInstance.filter(player=player, ball=self.ball.model).exists()
        ball = await BallInstance.create(
            ball=self.ball.model,
            player=player,
            shiny=shiny,
            special=special,
            attack_bonus=bonus_attack,
            health_bonus=bonus_health,
            server_id=user.guild.id,
            spawned_time=self.ball.time,
        )
        if user.id in bot.catch_log:
            log.info(
                f"{user} caught {settings.collectible_name}"
                f" {self.ball.model}, {shiny=} {special=}",
            )
        else:
            log.debug(
                f"{user} caught {settings.collectible_name}"
                f" {self.ball.model}, {shiny=} {special=}",
            )
        if user.guild.member_count:
            caught_balls.labels(
                country=self.ball.model.country,
                shiny=shiny,
                special=special,
                # observe the size of the server, rounded to the nearest power of 10
                guild_size=10 ** math.ceil(math.log(max(user.guild.member_count - 1, 1), 10)),
                spawn_algo=self.ball.algo,
            ).inc()
        return ball, is_new


class CatchView(View):
    def __init__(self, ball: "CountryBall"):
        super().__init__()
        self.ball = ball

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"], /) -> bool:
        return await interaction.client.blacklist_check(interaction)

    async def on_timeout(self):
        self.catch_button.disabled = True
        if self.ball.message:
            try:
                await self.ball.message.edit(view=self)
            except discord.HTTPException:
                pass

    @button(style=discord.ButtonStyle.primary, label="Catch me!")
    async def catch_button(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        if self.ball.catched:
            await interaction.response.send_message("I was caught already!", ephemeral=True)
        else:
            await interaction.response.send_modal(CountryballNamePrompt(self.ball, button))
