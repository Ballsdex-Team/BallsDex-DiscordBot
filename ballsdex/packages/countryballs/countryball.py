from __future__ import annotations

import logging
import math
import random
import string
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord.ui import Button, Modal, TextInput, View, button
from tortoise.timezone import get_default_timezone
from tortoise.timezone import now as tortoise_now

from ballsdex.core.metrics import caught_balls
from ballsdex.core.models import (
    Ball,
    BallInstance,
    Player,
    Special,
    Trade,
    TradeObject,
    balls,
    specials,
)
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.countryballs")


class CountryballNamePrompt(Modal, title=f"Catch this {settings.collectible_name}!"):
    name = TextInput(
        label=f"Name of this {settings.collectible_name}",
        style=discord.TextStyle.short,
        placeholder="Your guess",
    )

    def __init__(self, view: BallSpawnView):
        super().__init__()
        self.view = view

    async def on_error(
        self, interaction: discord.Interaction["BallsDexBot"], error: Exception, /  # noqa: W504
    ) -> None:
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
        await interaction.response.defer(thinking=True)

        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        if self.view.caught:
            slow_message = random.choice(settings.slow_messages).format(
                user=interaction.user.mention,
                collectible=settings.collectible_name,
                ball=self.view.name,
                collectibles=settings.plural_collectible_name,
            )

            await interaction.followup.send(
                slow_message,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=player.can_be_mentioned),
            )
            return

        if not self.view.is_name_valid(self.name.value):
            if len(self.name.value) > 500:
                wrong_name = self.name.value[:500] + "..."
            else:
                wrong_name = self.name.value

            wrong_message = random.choice(settings.wrong_messages).format(
                user=interaction.user.mention,
                collectible=settings.collectible_name,
                ball=self.view.name,
                collectibles=settings.plural_collectible_name,
                wrong=wrong_name,
            )

            await interaction.followup.send(
                wrong_message,
                allowed_mentions=discord.AllowedMentions(
                    users=player.can_be_mentioned, everyone=False, roles=False
                ),
                ephemeral=False,
            )
            return

        ball, has_caught_before = await self.view.catch_ball(
            interaction.user, player=player, guild=interaction.guild
        )

        await interaction.followup.send(
            self.view.get_catch_message(ball, has_caught_before, interaction.user.mention),
            allowed_mentions=discord.AllowedMentions(users=player.can_be_mentioned),
        )
        await interaction.followup.edit_message(self.view.message.id, view=self.view)


class BallSpawnView(View):
    """
    BallSpawnView is a Discord UI view that represents the spawning and interaction logic for a
    countryball in the BallsDex bot. It handles user interactions, spawning mechanics, and
    countryball catching logic.

    Attributes
    ----------
    bot: BallsDexBot
    model: Ball
        The ball being spawned.
    algo: str | None
        The algorithm used for spawning, used for metrics.
    message: discord.Message
        The Discord message associated with this view once created with `spawn`.
    caught: bool
        Whether the countryball has been caught yet.
    ballinstance: BallInstance | None
        If this is set, this ball instance will be spawned instead of creating a new ball instance.
        All properties are preserved, and if successfully caught, the owner is transferred (with
        a trade entry created). Use the `from_existing` constructor to use this.
    special: Special | None
        Force the spawned countryball to have a special event attached. If None, a random one will
        be picked.
    atk_bonus: int | None
        Force a specific attack bonus if set, otherwise random range defined in config.yml.
    hp_bonus: int | None
        Force a specific health bonus if set, otherwise random range defined in config.yml.
    """

    def __init__(self, bot: "BallsDexBot", model: Ball):
        super().__init__()
        self.bot = bot
        self.model = model
        self.algo: str | None = None
        self.message: discord.Message = discord.utils.MISSING
        self.caught = False
        self.ballinstance: BallInstance | None = None
        self.special: Special | None = None
        self.atk_bonus: int | None = None
        self.hp_bonus: int | None = None
        self.og_id: int

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"], /) -> bool:
        return await interaction.client.blacklist_check(interaction)

    async def on_timeout(self):
        self.catch_button.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
        if self.ballinstance and not self.caught:
            await self.ballinstance.unlock()

    @button(style=discord.ButtonStyle.primary, label="Catch me!")
    async def catch_button(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        if self.caught:
            await interaction.response.send_message("I was caught already!", ephemeral=True)
        else:
            await interaction.response.send_modal(CountryballNamePrompt(self))

    @classmethod
    async def from_existing(cls, bot: "BallsDexBot", ball_instance: BallInstance):
        """
        Get an instance from an existing `BallInstance`. Instead of creating a new ball instance,
        this will transfer ownership of the existing instance when caught.

        The ball instance must be unlocked from trades, and will be locked until caught or timed
        out.
        """
        if await ball_instance.is_locked():
            raise RuntimeError("This countryball is locked for a trade")

        # prevent countryball from being traded while spawned
        await ball_instance.lock_for_trade()

        view = cls(bot, ball_instance.ball)
        view.ballinstance = ball_instance
        view.og_id = ball_instance.player.discord_id
        return view

    @classmethod
    async def get_random(cls, bot: "BallsDexBot"):
        """
        Get a new instance with a random countryball. Rarity values are taken into account.
        """
        countryballs = list(filter(lambda m: m.enabled, balls.values()))
        if not countryballs:
            raise RuntimeError("No ball to spawn")
        rarities = [x.rarity for x in countryballs]
        cb = random.choices(population=countryballs, weights=rarities, k=1)[0]
        return cls(bot, cb)

    @property
    def name(self):
        return self.model.country

    def get_random_special(self) -> Special | None:
        population = [
            x
            for x in specials.values()
            # handle null start/end dates with infinity times
            if (x.start_date or datetime.min.replace(tzinfo=get_default_timezone()))
            <= tortoise_now()
            <= (x.end_date or datetime.max.replace(tzinfo=get_default_timezone()))
        ]

        if not population:
            return None

        common_weight: float = 1 - sum(x.rarity for x in population)

        if common_weight < 0:
            common_weight = 0

        weights = [x.rarity for x in population] + [common_weight]
        # None is added representing the common countryball
        special: Special | None = random.choices(
            population=population + [None], weights=weights, k=1
        )[0]

        return special

    async def spawn(self, channel: discord.TextChannel) -> bool:
        """
        Spawn a countryball in a channel.

        Parameters
        ----------
        channel: discord.TextChannel
            The channel where to spawn the countryball. Must have permission to send messages
            and upload files as a bot (not through interactions).

        Returns
        -------
        bool
            `True` if the operation succeeded, otherwise `False`. An error will be displayed
            in the logs if that's the case.
        """

        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
            return "".join(random.choices(source, k=15))

        extension = self.model.wild_card.split(".")[-1]
        file_location = "./admin_panel/media/" + self.model.wild_card
        file_name = f"nt_{generate_random_name()}.{extension}"
        try:
            permissions = channel.permissions_for(channel.guild.me)
            if permissions.attach_files and permissions.send_messages:
                spawn_message = random.choice(settings.spawn_messages).format(
                    collectible=settings.collectible_name,
                    ball=self.name,
                    collectibles=settings.plural_collectible_name,
                )

                self.message = await channel.send(
                    spawn_message,
                    view=self,
                    file=discord.File(file_location, filename=file_name),
                )
                return True
            else:
                log.error("Missing permission to spawn ball in channel %s.", channel)
        except discord.Forbidden:
            log.error(f"Missing permission to spawn ball in channel {channel}.")
        except discord.HTTPException:
            log.error("Failed to spawn ball", exc_info=True)
        return False

    def is_name_valid(self, text: str) -> bool:
        """
        Check if the prompted name is valid.

        Parameters
        ----------
        text: str
            The text entered by the user. It will be lowered and stripped of enclosing blank
            characters.

        Returns
        -------
        bool
            Whether the name matches or not.
        """
        if self.model.catch_names:
            possible_names = (self.name.lower(), *self.model.catch_names.split(";"))
        else:
            possible_names = (self.name.lower(),)
        if self.model.translations:
            possible_names += tuple(x.lower() for x in self.model.translations.split(";"))
        cname = text.lower().strip()
        # Remove fancy unicode characters like ’ to replace to '
        cname = cname.replace("\u2019", "'")
        cname = cname.replace("\u2018", "'")
        cname = cname.replace("\u201c", '"')
        cname = cname.replace("\u201d", '"')
        return cname in possible_names

    async def catch_ball(
        self,
        user: discord.User | discord.Member,
        *,
        player: Player | None,
        guild: discord.Guild | None,
    ) -> tuple[BallInstance, bool]:
        """
        Mark this countryball as caught and assign a new `BallInstance` (or transfer ownership if
        attribute `ballinstance` was set).

        Parameters
        ----------
        user: discord.User | discord.Member
            The user that will obtain the new countryball.
        player: Player
            If already fetched, add the player model here to avoid an additional query.
        guild: discord.Guild | None
            If caught in a guild, specify here for additional logs. Will be extracted from `user`
            if it's a member object.

        Returns
        -------
        tuple[bool, BallInstance]
            A tuple whose first value indicates if this is the first time this player catches this
            countryball. Second value is the newly created countryball.

            If `ballinstance` was set, this value is returned instead.

        Raises
        ------
        RuntimeError
            The `caught` attribute is already set to `True`. You should always check before calling
            this function that the ball was not caught.
        """
        if self.caught:
            raise RuntimeError("This ball was already caught!")
        self.caught = True
        self.catch_button.disabled = True
        player = player or (await Player.get_or_create(discord_id=user.id))[0]
        is_new = not await BallInstance.filter(player=player, ball=self.model).exists()

        if self.ballinstance:
            # if specified, do not create a countryball but switch owner
            # it's important to register this as a trade to avoid bypass
            trade = await Trade.create(player1=self.ballinstance.player, player2=player)
            await TradeObject.create(
                trade=trade, player=self.ballinstance.player, ballinstance=self.ballinstance
            )
            self.ballinstance.trade_player = self.ballinstance.player
            self.ballinstance.player = player
            self.ballinstance.locked = None  # type: ignore
            await self.ballinstance.save(update_fields=("player_id", "trade_player_id", "locked"))
            return self.ballinstance, is_new

        # stat may vary by +/- 20% of base stat
        bonus_attack = (
            self.atk_bonus
            if self.atk_bonus is not None
            else random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
        )
        bonus_health = (
            self.hp_bonus
            if self.hp_bonus is not None
            else random.randint(-settings.max_health_bonus, settings.max_health_bonus)
        )

        # check if we can spawn cards with a special background
        special: Special | None = self.special

        if not special:
            special = self.get_random_special()

        ball = await BallInstance.create(
            ball=self.model,
            player=player,
            special=special,
            attack_bonus=bonus_attack,
            health_bonus=bonus_health,
            server_id=guild.id if guild else None,
            spawned_time=self.message.created_at,
        )

        # logging and stats
        log.log(
            logging.INFO if user.id in self.bot.catch_log else logging.DEBUG,
            f"{user} caught {settings.collectible_name} {self.model}, {special=}",
        )
        if isinstance(user, discord.Member) and user.guild.member_count:
            caught_balls.labels(
                country=self.name,
                special=special,
                # observe the size of the server, rounded to the nearest power of 10
                guild_size=10 ** math.ceil(math.log(max(user.guild.member_count - 1, 1), 10)),
                spawn_algo=self.algo,
            ).inc()

        return ball, is_new

    def get_catch_message(self, ball: BallInstance, new_ball: bool, mention: str) -> str:
        """
        Generate a user-facing message after a ball has been caught.

        Parameters
        ----------
        ball: BallInstance
            The newly created ball instance
        new_ball: bool
            Boolean indicating if this is a new countryball in completion
            (as returned by `catch_ball`)
        """
        text = ""
        if ball.specialcard and ball.specialcard.catch_phrase:
            text += f"*{ball.specialcard.catch_phrase}*\n"
        if new_ball:
            text += (
                f"This is a **new {settings.collectible_name}** "
                "that has been added to your completion!"
            )
        if self.ballinstance:
            text += f"This {settings.collectible_name} was dropped by <@{self.og_id}>\n"

        caught_message = (
            random.choice(settings.caught_messages).format(
                user=mention,
                collectible=settings.collectible_name,
                ball=self.name,
                collectibles=settings.plural_collectible_name,
            )
            + " "
        )

        return (
            caught_message
            + f"`(#{ball.pk:0X}, {ball.attack_bonus:+}%/{ball.health_bonus:+}%)`\n\n{text}"
        )
