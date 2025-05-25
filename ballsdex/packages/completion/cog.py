import enum
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, button
from tortoise.exceptions import DoesNotExist
from tortoise.functions import Count

from ballsdex.core.models import BallInstance, DonationPolicy, Player, Trade, TradeObject, balls
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.core.utils.sorting import SortingChoices, sort_balls
from ballsdex.core.utils.transformers import (
    BallEnabledTransform,
    BallInstanceTransform,
    SpecialEnabledTransform,
    TradeCommandType,
)
from ballsdex.core.utils.utils import inventory_privacy, is_staff
from ballsdex.packages.balls.countryballs_paginator import CountryballsViewer
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(dms=True, private_channels=True, guilds=True)
class Completion(commands.GroupCog, group_name="completion"):
    """
    Multi completion commands.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        
    @app_commands.command()
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def skins(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User | None = None,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Show your current skin completion of the BallsDex.

        Parameters
        ----------
        user: discord.User
            The user whose completion you want to view, if not yours.
        special: Special
            The special you want to see the completion of
        """
        skin_emoji_1 = self.bot.get_emoji(1371574815361732618)
        skin_emoji_2 = self.bot.get_emoji(1371576710386024519)
        skin_emoji_3 = self.bot.get_emoji(1371558580234227854)
        skin_emoji_4 = self.bot.get_emoji(1371558589537321013)
        skin_unlock_emoji = self.bot.get_emoji(1363692398596853841)
        skin_lock_emoji = self.bot.get_emoji(1363692380208890066)
        no_skin_emoji = self.bot.get_emoji(1349143586603667587)
        completionist_emoji = self.bot.get_emoji(1372373379939827744)
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)
        extra_text = f"{special.name} " if special else ""
        if user is not None:
            try:
                player = await Player.get(discord_id=user_obj.id)
            except DoesNotExist:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any "
                    f"{extra_text}skins yet."
                )
                return

            interaction_player, _ = await Player.get_or_create(discord_id=interaction.user.id)

            blocked = await player.is_blocked(interaction_player)
            if blocked and not is_staff(interaction):
                await interaction.followup.send(
                    "You cannot view the completion of a user that has blocked you.",
                    ephemeral=True,
                )
                return

            if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
                return
        # Filter disabled balls, they do not count towards progression
        # Only ID and emoji is interesting for us
        bot_countryballs = {x: y.emoji_id for x, y in balls.items() if y.enabled and 22 <= y.regime_id <= 27 or 35 <= y.regime_id <= 40}

        # Set of ball IDs owned by the player
        filters = {"player__discord_id": user_obj.id, "ball__enabled": True}
        if special:
            filters["special"] = special
            bot_countryballs = {
                x: y.emoji_id
                for x, y in balls.items()
                if y.enabled and 22 <= y.regime_id <= 27 or 35 <= y.regime_id <= 40 and (special.end_date is None or y.created_at < special.end_date)
            }
        if not bot_countryballs:
            await interaction.followup.send(
                f"There are no {extra_text}skins"
                " registered on this bot yet.",
                ephemeral=True,
            )
            return

        owned_countryballs = set(
            x[0]
            for x in await BallInstance.filter(**filters).exclude(ball__regime_id=5).exclude(ball__regime_id=6).exclude(ball__regime_id=7).exclude(ball__regime_id=8).exclude(ball__regime_id=16).exclude(ball__regime_id=19).exclude(ball__regime_id=20).exclude(ball__regime_id=21).exclude(ball__regime_id=28).exclude(ball__regime_id=29).exclude(ball__regime_id=30).exclude(ball__regime_id=31).exclude(ball__regime_id=32).exclude(ball__regime_id=33).exclude(ball__regime_id=34).exclude(ball__regime_id=36)
            .distinct()  # Do not query everything
            .values_list("ball_id")
        )

        entries: list[tuple[str, str]] = []

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
                        entries.append(("\u200B", buffer))
                    else:
                        entries.append((f"__**{title}**__", buffer))
                        first_field_added = True
                    buffer = ""
                buffer += text

            if buffer:  # add what's remaining
                if first_field_added:
                    entries.append(("\u200B", buffer))
                else:
                    entries.append((f"__**{title}**__", buffer))

        if owned_countryballs:
            # Getting the list of emoji IDs from the IDs of the owned countryballs
            fill_fields(
                f"{skin_unlock_emoji} {len(owned_countryballs)} Skins Unlocked {skin_unlock_emoji}",
                set(bot_countryballs[x] for x in owned_countryballs),
            )
        else:
            entries.append((f"*Seems like you don't have any Skins... {no_skin_emoji}*"))

        if missing := set(y for x, y in bot_countryballs.items() if x not in owned_countryballs):
            fill_fields(f"{skin_lock_emoji} {len(bot_countryballs) - len(owned_countryballs)} Skins to be Unlocked {skin_lock_emoji}", missing)
        else:
            entries.append(
                (
                    f"*{completionist_emoji} Congrats, you are truly a Completionist! {completionist_emoji}*"
                )
            )  # force empty field value
        source = FieldPageSource(entries, per_page=5, inline=False, clear_description=False)
        special_str = f" ({special.name})" if special else ""
        source.embed.description = (
            f"{skin_emoji_1}{skin_emoji_2} SKINS\n"
            f"{skin_emoji_3}{skin_emoji_4} {len(owned_countryballs)}/{len(bot_countryballs)} Collected"
        )
        source.embed.colour = discord.Colour.blurple()
        source.embed.set_author(name=user_obj.display_name, icon_url=user_obj.display_avatar.url)

        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start()
        
    @app_commands.command()
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def buzzlightyear(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User | None = None,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Show your current Buzz Lightyear completion of the BallsDex.

        Parameters
        ----------
        user: discord.User
            The user whose completion you want to view, if not yours.
        special: Special
            The special you want to see the completion of
        """
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)
        extra_text = f"{special.name} " if special else ""
        if user is not None:
            try:
                player = await Player.get(discord_id=user_obj.id)
            except DoesNotExist:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any "
                    f"{extra_text}Buzz Lightyears yet."
                )
                return

            interaction_player, _ = await Player.get_or_create(discord_id=interaction.user.id)

            blocked = await player.is_blocked(interaction_player)
            if blocked and not is_staff(interaction):
                await interaction.followup.send(
                    "You cannot view the completion of a user that has blocked you.",
                    ephemeral=True,
                )
                return

            if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
                return
        # Filter disabled balls, they do not count towards progression
        # Only ID and emoji is interesting for us
        bot_countryballs = {x: y.emoji_id for x, y in balls.items() if not y.enabled and y.rarity == 0.000113}

        # Set of ball IDs owned by the player
        filters = {"player__discord_id": user_obj.id, "ball__enabled": False, "ball__rarity": 0.000113}
        if special:
            filters["special"] = special
            bot_countryballs = {
                x: y.emoji_id
                for x, y in balls.items()
                if not y.enabled and y.rarity == 0.000113 and (special.end_date is None or y.created_at < special.end_date)
            }
        if not bot_countryballs:
            await interaction.followup.send(
                f"There are no {extra_text}Buzz Lightyears"
                " registered on this bot yet.",
                ephemeral=True,
            )
            return

        owned_countryballs = set(
            x[0]
            for x in await BallInstance.filter(**filters)
            .distinct()  # Do not query everything
            .values_list("ball_id")
        )

        entries: list[tuple[str, str]] = []

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
                        entries.append(("\u200B", buffer))
                    else:
                        entries.append((f"__**{title}**__", buffer))
                        first_field_added = True
                    buffer = ""
                buffer += text

            if buffer:  # add what's remaining
                if first_field_added:
                    entries.append(("\u200B", buffer))
                else:
                    entries.append((f"__**{title}**__", buffer))

        if owned_countryballs:
            # Getting the list of emoji IDs from the IDs of the owned countryballs
            fill_fields(
                f"Owned Buzz Lightyears - {len(owned_countryballs)} total",
                set(bot_countryballs[x] for x in owned_countryballs),
            )
        else:
            entries.append((f"__**Owned Buzz Lightyears**__ - {len(owned_countryballs)} total", "Nothing yet."))

        if missing := set(y for x, y in bot_countryballs.items() if x not in owned_countryballs):
            fill_fields(f"Missing Buzz Lightyears - {len(bot_countryballs) - len(owned_countryballs)} total", missing)
        else:
            entries.append(
                (
                    f"__**To infinity "
                    "and beyond!**__",
                    "\u200B",
                )
            )  # force empty field value

        source = FieldPageSource(entries, per_page=5, inline=False, clear_description=False)
        special_str = f" ({special.name})" if special else ""
        source.embed.description = (
            f"Lightyear progress: "
            f"**{round(len(owned_countryballs) / len(bot_countryballs) * 100, 1)}% ({len(owned_countryballs)}/{len(bot_countryballs)})**"
        )
        source.embed.colour = discord.Colour.blurple()
        source.embed.set_author(name=user_obj.display_name, icon_url=user_obj.display_avatar.url)

        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start()
