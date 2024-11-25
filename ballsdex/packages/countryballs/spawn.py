import asyncio
import logging
import random
from abc import abstractmethod
from collections import deque, namedtuple
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord.utils import format_dt

from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.countryballs")

SPAWN_CHANCE_RANGE = (40, 55)

CachedMessage = namedtuple("CachedMessage", ["content", "author_id"])


class BaseSpawnManager:
    """
    A class instancied on cog load that will include the logic determining when a countryball
    should be spawned. You can implement your own version and configure it in config.yml.

    Be careful with optimization and memory footprint, this will be called very often and should
    not slow down the bot or cause memory leaks.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @abstractmethod
    async def handle_message(self, message: discord.Message) -> bool:
        """
        Handle a message event and determine if a countryball should be spawned next.

        Parameters
        ----------
        message: discord.Message
            The message that triggered the event

        Returns
        -------
        bool
            `True` if a countryball should be spawned, else `False`.

            If a countryball should spawn, do not forget to cleanup induced context to avoid
            infinite spawns.
        """
        raise NotImplementedError

    @abstractmethod
    async def admin_explain(
        self, interaction: discord.Interaction["BallsDexBot"], guild: discord.Guild
    ):
        """
        Invoked by "/admin cooldown", this function should provide insights of the cooldown
        system for admins.

        Parameters
        ----------
        interaction: discord.Interaction[BallsDexBot]
            The interaction of the slash command
        guild: discord.Guild
            The guild that is targeted for the insights
        """
        raise NotImplementedError


@dataclass
class SpawnCooldown:
    """
    Represents the default spawn internal system per guild. Contains the counters that will
    determine if a countryball should be spawned next or not.

    Attributes
    ----------
    time: datetime
        Time when the object was initialized. Block spawning when it's been less than ten minutes
    scaled_message_count: float
        A number starting at 0, incrementing with the messages until reaching `threshold`. At this
        point, a ball will be spawned next.
    threshold: int
        The number `scaled_message_count` has to reach for spawn.
        Determined randomly with `SPAWN_CHANCE_RANGE`
    lock: asyncio.Lock
        Used to ratelimit messages and ignore fast spam
    message_cache: ~collections.deque[CachedMessage]
        A list of recent messages used to reduce the spawn chance when too few different chatters
        are present. Limited to the 100 most recent messages in the guild.
    """

    time: datetime
    # initialize partially started, to reduce the dead time after starting the bot
    scaled_message_count: float = field(default=SPAWN_CHANCE_RANGE[0] // 2)
    threshold: int = field(default_factory=lambda: random.randint(*SPAWN_CHANCE_RANGE))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    message_cache: deque[CachedMessage] = field(default_factory=lambda: deque(maxlen=100))

    def reset(self, time: datetime):
        self.scaled_message_count = 1.0
        self.threshold = random.randint(*SPAWN_CHANCE_RANGE)
        try:
            self.lock.release()
        except RuntimeError:  # lock is not acquired
            pass
        self.time = time

    async def increase(self, message: discord.Message) -> bool:
        # this is a deque, not a list
        # its property is that, once the max length is reached (100 for us),
        # the oldest element is removed, thus we only have the last 100 messages in memory
        self.message_cache.append(
            CachedMessage(content=message.content, author_id=message.author.id)
        )

        if self.lock.locked():
            return False

        async with self.lock:
            message_multiplier = 1
            if message.guild.member_count < 5 or message.guild.member_count > 1000:  # type: ignore
                message_multiplier /= 2
            if message._state.intents.message_content and len(message.content) < 5:
                message_multiplier /= 2
            if len(set(x.author_id for x in self.message_cache)) < 4 or (
                len(list(filter(lambda x: x.author_id == message.author.id, self.message_cache)))
                / self.message_cache.maxlen  # type: ignore
                > 0.4
            ):
                message_multiplier /= 2
            self.scaled_message_count += message_multiplier
            await asyncio.sleep(10)
        return True


class SpawnManager(BaseSpawnManager):
    def __init__(self, bot: "BallsDexBot"):
        super().__init__(bot)
        self.cooldowns: dict[int, SpawnCooldown] = {}

    async def handle_message(self, message: discord.Message) -> bool:
        guild = message.guild
        if not guild:
            return False

        cooldown = self.cooldowns.get(guild.id, None)
        if not cooldown:
            cooldown = SpawnCooldown(message.created_at)
            self.cooldowns[guild.id] = cooldown

        delta_t = (message.created_at - cooldown.time).total_seconds()
        # change how the threshold varies according to the member count, while nuking farm servers
        if not guild.member_count:
            return False
        elif guild.member_count < 5:
            time_multiplier = 0.1
        elif guild.member_count < 100:
            time_multiplier = 0.8
        elif guild.member_count < 1000:
            time_multiplier = 0.5
        else:
            time_multiplier = 0.2

        # manager cannot be increased more than once per 10 seconds
        if not await cooldown.increase(message):
            return False

        # normal increase, need to reach goal
        if cooldown.scaled_message_count + time_multiplier * (delta_t // 60) <= cooldown.threshold:
            return False

        # at this point, the goal is reached
        if delta_t < 600:
            # wait for at least 10 minutes before spawning
            return False

        # spawn countryball
        cooldown.reset(message.created_at)
        return True

    async def admin_explain(
        self, interaction: discord.Interaction["BallsDexBot"], guild: discord.Guild
    ):
        cooldown = self.cooldowns.get(guild.id)
        if not cooldown:
            await interaction.response.send_message(
                "No spawn manager could be found for that guild. Spawn may have been disabled.",
                ephemeral=True,
            )
            return

        if not guild.member_count:
            await interaction.response.send_message(
                "`member_count` data not returned for this guild, spawn cannot work."
            )
            return

        embed = discord.Embed()
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        embed.colour = discord.Colour.orange()

        delta = (interaction.created_at - cooldown.time).total_seconds()
        # change how the threshold varies according to the member count, while nuking farm servers
        if guild.member_count < 5:
            multiplier = 0.1
            range = "1-4"
        elif guild.member_count < 100:
            multiplier = 0.8
            range = "5-99"
        elif guild.member_count < 1000:
            multiplier = 0.5
            range = "100-999"
        else:
            multiplier = 0.2
            range = "1000+"

        penalities: list[str] = []
        if guild.member_count < 5 or guild.member_count > 1000:
            penalities.append("Server has less than 5 or more than 1000 members")
        if any(len(x.content) < 5 for x in cooldown.message_cache):
            penalities.append("Some cached messages are less than 5 characters long")

        authors_set = set(x.author_id for x in cooldown.message_cache)
        low_chatters = len(authors_set) < 4
        # check if one author has more than 40% of messages in cache
        major_chatter = any(
            (
                len(list(filter(lambda x: x.author_id == author, cooldown.message_cache)))
                / cooldown.message_cache.maxlen  # type: ignore
                > 0.4
            )
            for author in authors_set
        )
        # this mess is needed since either conditions make up to a single penality
        if low_chatters:
            if not major_chatter:
                penalities.append("Message cache has less than 4 chatters")
            else:
                penalities.append(
                    "Message cache has less than 4 chatters **and** "
                    "one user has more than 40% of messages within message cache"
                )
        elif major_chatter:
            if not low_chatters:
                penalities.append("One user has more than 40% of messages within cache")

        penality_multiplier = 0.5 ** len(penalities)
        if penalities:
            embed.add_field(
                name="\N{WARNING SIGN}\N{VARIATION SELECTOR-16} Penalities",
                value="Each penality divides the progress by 2\n\n- " + "\n- ".join(penalities),
            )

        chance = cooldown.threshold - multiplier * (delta // 60)

        embed.description = (
            f"Manager initiated **{format_dt(cooldown.time, style='R')}**\n"
            f"Initial number of points to reach: **{cooldown.threshold}**\n"
            f"Message cache length: **{len(cooldown.message_cache)}**\n\n"
            f"Time-based multiplier: **x{multiplier}** *({range} members)*\n"
            "*This affects how much the number of points to reach reduces over time*\n"
            f"Penality multiplier: **x{penality_multiplier}**\n"
            "*This affects how much a message sent increases the number of points*\n\n"
            f"__Current count: **{cooldown.threshold}/{chance}**__\n\n"
        )

        informations: list[str] = []
        if cooldown.lock.locked():
            informations.append("The manager is currently on cooldown.")
        if delta < 600:
            informations.append(
                f"The manager is less than 10 minutes old, {settings.plural_collectible_name} "
                "cannot spawn at the moment."
            )
        if informations:
            embed.add_field(
                name="\N{INFORMATION SOURCE}\N{VARIATION SELECTOR-16} Informations",
                value="- " + "\n- ".join(informations),
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
