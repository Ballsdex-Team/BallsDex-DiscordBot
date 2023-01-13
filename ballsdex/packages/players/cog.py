import discord
import time
import logging
import enum

from typing import TYPE_CHECKING, Optional, List, Union, AsyncIterator
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime
from tortoise.exceptions import DoesNotExist

from discord import app_commands
from discord.ext import commands, tasks

from ballsdex.core.models import Ball, Player, BallInstance

from ballsdex.packages.players.countryballs_paginator import (
    CountryballsViewer,
    CountryballsExchangerPaginator,
)
from ballsdex.packages.players.exchange_interaction import ExchangePlayer

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.countryballs")

CACHE_TIME = 30


class SortingChoices(enum.Enum):
    alphabetic = "ball__country"
    catch_date = "-catch_date"
    rarity = "ball__rarity"
    special = "special__id"

    # manual sorts are not sorted by SQL queries but by our code
    # this may be do-able with SQL still, but I don't have much experience ngl
    duplicates = "manualsort-duplicates"


@dataclass
class UserCountryballsCache:
    time: float
    balls: List[BallInstance]


class CountryballCache:
    def __init__(self):
        self.cache: dict[int, UserCountryballsCache] = {}
        self.clear_cache.start()

    async def get(self, user: discord.abc.User, value: str) -> AsyncIterator[BallInstance]:
        time = datetime.utcnow().timestamp()
        try:
            cache = self.cache[user.id]
            if time - cache.time > 60:
                raise KeyError  # refresh cache after a minute
        except KeyError:
            try:
                player = await Player.get(discord_id=user.id)
            except DoesNotExist:
                balls = []
            else:
                balls = await BallInstance.filter(player=player).select_related("ball").all()
            cache = UserCountryballsCache(time, balls)
            self.cache[user.id] = cache

        total = 0
        for ball in cache.balls:
            if value in ball.ball.country.lower():
                yield ball
                total += 1
                if total >= 25:
                    return

    @tasks.loop(seconds=10, reconnect=True)
    async def clear_cache(self):
        time = datetime.utcnow().timestamp()
        to_delete: List[int] = []
        for id, user in self.cache.items():
            if time - user.time > CACHE_TIME:
                to_delete.append(id)
        for id in to_delete:
            del self.cache[id]


class BallInstanceTransformer(app_commands.Transformer):
    def __init__(self):
        self.cache = CountryballCache()

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> List[app_commands.Choice[Union[int, float, str]]]:
        t1 = time.time()
        choices: List[app_commands.Choice] = []
        async for ball in self.cache.get(interaction.user, value):
            choices.append(app_commands.Choice(name=str(ball), value=str(ball.id)))
        t2 = time.time()
        log.debug(f"Autocomplete took {round((t2-t1)*1000)}ms, {len(choices)} results")
        return choices

    async def transform(self, interaction: discord.Interaction, value: str) -> BallInstance | None:
        # in theory, the selected ball should be in the cache
        # but it's possible that the autocomplete was never invoked
        try:
            try:
                balls = self.cache.cache[interaction.user.id].balls
                for ball in balls:
                    if ball.id == int(value):
                        return ball
            except KeyError:
                # maybe the cache didn't have time to build, let's try anyway to fetch the value
                try:
                    return await BallInstance.get(id=int(value)).prefetch_related("ball")
                except DoesNotExist:
                    await interaction.response.send_message(
                        "The ball could not be found. Make sure to use the autocomplete "
                        "function on this command."
                    )
                    return None

        except ValueError:
            # autocomplete didn't work and user tried to force a custom value
            await interaction.response.send_message(
                "The ball could not be found. Make sure to use the autocomplete "
                "function on this command."
            )
            return None


class Players(commands.GroupCog, group_name="balls"):
    """
    View and manage your countryballs collection.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.describe(
        user="View someone else's collection",
        sort="Modify the default sorting of your countryballs",
    )
    async def list(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        sort: SortingChoices | None = None,
    ):
        """
        List your countryballs.
        """
        user: discord.User | discord.Member = user or interaction.user

        try:
            player = await Player.get(discord_id=user.id)
        except DoesNotExist:
            if user == interaction.user:
                await interaction.response.send_message("You don't have any countryball yet.")
            else:
                await interaction.response.send_message(
                    f"{user.name} doesn't have any countryball yet."
                )
            return

        await player.fetch_related("balls")
        if sort:
            if sort == SortingChoices.duplicates:
                countryballs = await player.balls.all().prefetch_related("ball")
                count = defaultdict(int)
                for countryball in countryballs:
                    count[countryball.ball.pk] += 1
                countryballs.sort(key=lambda m: (-count[m.ball.pk], m.ball.pk))
            else:
                countryballs = (
                    await player.balls.all().prefetch_related("ball").order_by(sort.value)
                )
        else:
            countryballs = (
                await player.balls.all().prefetch_related("ball").order_by("-favorite", "-shiny")
            )

        if len(countryballs) < 1:
            if user == interaction.user:
                await interaction.response.send_message("You don't have any countryball yet.")
            else:
                await interaction.response.send_message(
                    f"{user.name} doesn't have any countryball yet."
                )
            return

        paginator = CountryballsViewer(interaction, countryballs)
        if user == interaction.user:
            await paginator.start()
        else:
            await paginator.start(content=f"Viewing {user.name}'s countryballs")

    @app_commands.command()
    async def completion(self, interaction: discord.Interaction):
        """
        Show your current completion of the BallsDex.
        """
        # Filter disabled balls, they do not count towards progression
        # Only ID and emoji is interesting for us
        bot_countryballs = {
            x.pk: x.emoji_id for x in await Ball.filter(enabled=True).only("id", "emoji_id")
        }
        # Set of ball IDs owned by the player
        owned_countryballs = set(
            x[0]
            for x in await BallInstance.filter(player__discord_id=interaction.user.id)
            .distinct()  # Do not query everything
            .values_list("ball_id")
        )

        embed = discord.Embed(
            description="BallsDex progression: "
            f"**{round(len(owned_countryballs)/len(bot_countryballs)*100, 4)}%**",
            colour=discord.Colour.blurple(),
        )
        embed.set_author(
            name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url
        )

        def fill_fields(title: str, emoji_ids: set[int]):
            # check if we need to add "(continued)" to the field name
            first_field_added = False
            buffer = ""

            for emoji_id in emoji_ids:
                emoji = self.bot.get_emoji(emoji_id)
                if not emoji:
                    continue

                text = f"{emoji} "
                if len(buffer) + len(text) > 1024:
                    # hitting embed limits, adding an intermediate field
                    if first_field_added:
                        embed.add_field(name="\u200B", value=buffer, inline=False)
                    else:
                        embed.add_field(name=f"__**{title}**__", value=buffer, inline=False)
                        first_field_added = True
                    buffer = ""
                buffer += text

            if buffer:  # add what's remaining
                if first_field_added:
                    embed.add_field(name="\u200B", value=buffer, inline=False)
                else:
                    embed.add_field(name=f"__**{title}**__", value=buffer, inline=False)

        if owned_countryballs:
            # Getting the list of emoji IDs from the IDs of the owned countryballs
            fill_fields("Owned countryballs", set(bot_countryballs[x] for x in owned_countryballs))
        else:
            embed.add_field(name="__**Owned countryballs**__", value="Nothing yet.", inline=False)

        if missing := set(y for x, y in bot_countryballs.items() if x not in owned_countryballs):
            fill_fields("Missing countryballs", missing)
        else:
            embed.add_field(
                name="__**:tada: No missing countryball, congratulations! :tada:**__",
                value="\u200B",
                inline=False,
            )  # force empty field value

        await interaction.response.send_message(embed=embed)

    @app_commands.command()
    @app_commands.describe(countryball="The countryball you want to inspect")
    async def info(
        self,
        interaction: discord.Interaction,
        countryball: app_commands.Transform[BallInstance, BallInstanceTransformer],
    ):
        """
        Display info from a specific countryball.
        """
        if not countryball:
            return
        await interaction.response.defer(thinking=True)
        content, file = await countryball.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file)
        file.close()

    @app_commands.command()
    async def last(self, interaction: discord.Interaction):
        """
        Display info of your last caught countryball.
        """
        await interaction.response.defer(thinking=True)
        try:
            player = await Player.get(discord_id=interaction.user.id)
        except DoesNotExist:
            await interaction.followup.send("You do not have any countryball yet.", ephemeral=True)
            return

        countryball = await player.balls.all().order_by("-id").first().select_related("ball")
        if not countryball:
            await interaction.followup.send("You do not have any countryball yet.", ephemeral=True)
            return

        content, file = await countryball.prepare_for_message(interaction)
        await interaction.followup.send(content=content, file=file)
        file.close()

    @app_commands.command()
    @app_commands.describe(countryball="The countryball you want to set/unset as favorite")
    async def favorite(
        self,
        interaction: discord.Interaction,
        countryball: app_commands.Transform[BallInstance, BallInstanceTransformer],
    ):
        """
        Set favorite countryballs.
        """
        if not countryball.favorite:

            player = await Player.get(discord_id=interaction.user.id).prefetch_related("balls")
            if await player.balls.filter(favorite=True).count() > 6:
                await interaction.response.send_message(
                    "You cannot set more than 6 favorite countryballs.", ephemeral=True
                )
                return

            countryball.favorite = True  # type: ignore
            await countryball.save()
            emoji = self.bot.get_emoji(countryball.ball.emoji_id) or ""
            await interaction.response.send_message(
                f"{emoji} `{countryball.count}#` {countryball.ball.country} "
                "is now a favorite countryball!",
                ephemeral=True,
            )

        else:
            countryball.favorite = False  # type: ignore
            await countryball.save()
            emoji = self.bot.get_emoji(countryball.ball.emoji_id) or ""
            await interaction.response.send_message(
                f"{emoji} `{countryball.count}#` {countryball.ball.country} "
                "isn't a favorite countryball anymore.",
                ephemeral=True,
            )

    @app_commands.command()
    @app_commands.describe(
        user="The user you want to exchange a countryball with",
        countryball="The countryball you want to exchange",
    )
    async def exchange(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        countryball: app_commands.Transform[BallInstance, BallInstanceTransformer] = None,
    ):
        """
        Exchange a countryball with another player.
        """
        if user.bot:
            await interaction.response.send_message(
                "You cannot exchange with bots.", ephemeral=True
            )
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot exchange with yourself.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True)
        # theorically, the player should always be created by the autocomplete function
        # let's still handle the case where autocomplete wasn't invoked and the player may not
        # have been created yet
        if countryball is None:
            await CountryballsExchangerPaginator.begin_blank_exchange(
                interaction, interaction.user, user
            )
        else:
            player, created = await Player.get_or_create(discord_id=interaction.user.id)
            await CountryballsExchangerPaginator.half_ready_exchange(
                interaction, ExchangePlayer(interaction.user, player, countryball), user
            )
