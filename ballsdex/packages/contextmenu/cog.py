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
class ContextMenuCommands(commands.Cog):
    """
    Dex commands but in Context Menu!
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        
@app_commands.context_menu(name="View Brawler Collection")
@app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
async def context_brawler_collection(
    self,
    interaction: discord.Interaction,
    user: discord.User
):
    brawler_emoji_1 = self.bot.get_emoji(1371591594867949588)
    brawler_emoji_2 = self.bot.get_emoji(1371591872782401637)
    brawler_emoji_3 = self.bot.get_emoji(1371592384143556648)
    brawler_emoji_4 = self.bot.get_emoji(1371592712331198545)
    brawler_unlock_emoji = self.bot.get_emoji(1363692398596853841)
    brawler_lock_emoji = self.bot.get_emoji(1363692380208890066)
    no_brawler_emoji = self.bot.get_emoji(1349143586603667587)
    completionist_emoji = self.bot.get_emoji(1372373379939827744)

    user_obj = user
    await interaction.response.defer(thinking=True)

    try:
        player, _ = await Player.get_or_create(discord_id=user_obj.id)
    except DoesNotExist:
        await interaction.followup.send(
            f"{user_obj.name} doesn't have any brawlers yet."
        )
        return

    interaction_player, _ = await Player.get_or_create(discord_id=interaction.user.id)

    blocked = await player.is_blocked(interaction_player)
    if blocked and not is_staff(interaction):
        await interaction.followup.send(
            "You cannot view the collection of a user that has blocked you.",
            ephemeral=True,
        )
        return

    if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
        return

    bot_countryballs = {
        x: y.emoji_id
        for x, y in balls.items()
        if y.enabled and 3 <= y.economy_id <= 9
        and not 19 <= y.regime_id <= 21
        and y.economy_id != 16
    }

    filters = {"player__discord_id": user_obj.id, "ball__enabled": True}

    if not bot_countryballs:
        await interaction.followup.send(
            f"There are no {settings.plural_collectible_name} registered on this bot yet.",
            ephemeral=True,
        )
        return

    owned_countryballs = set(
        x[0]
        for x in await BallInstance.filter(**filters)
        .exclude(ball__regime_id__in=list(range(19, 34)) + [35, 37, 38, 39, 40])
        .distinct()
        .values_list("ball_id")
    )

    entries: list[tuple[str, str]] = []

    def fill_fields(title: str, emoji_ids: set[int]):
        first_field_added = False
        buffer = ""

        for emoji_id in emoji_ids:
            emoji = self.bot.get_emoji(emoji_id)
            if not emoji:
                continue

            text = f"{emoji} "
            if len(buffer) + len(text) > 1024:
                if first_field_added:
                    entries.append(("\u200b", buffer))
                else:
                    entries.append((f"__**{title}**__", buffer))
                    first_field_added = True
                buffer = ""

            buffer += text

        if buffer:
            if first_field_added:
                entries.append(("\u200b", buffer))
            else:
                entries.append((f"__**{title}**__", buffer))

    if owned_countryballs:
        fill_fields(
            f"{brawler_unlock_emoji} {len(owned_countryballs)} Brawlers Unlocked {brawler_unlock_emoji}",
            set(bot_countryballs[x] for x in owned_countryballs),
        )
    else:
        entries.append((f"*Seems like you don't have any Brawlers... {no_brawler_emoji}*", ""))

    missing = set(y for x, y in bot_countryballs.items() if x not in owned_countryballs)
    if missing:
        fill_fields(
            f"{brawler_lock_emoji} {len(bot_countryballs) - len(owned_countryballs)} Brawlers to be Unlocked {brawler_lock_emoji}",
            missing,
        )
    else:
        entries.append(
            (
                f"{completionist_emoji} Congrats, you are truly a Completionist! {completionist_emoji}",
                ""
            )
        )

    source = FieldPageSource(entries, per_page=5, inline=False, clear_description=False)
    source.embed.description = (
        f"{brawler_emoji_1}{brawler_emoji_2} BRAWLERS\n"
        f"{brawler_emoji_3}{brawler_emoji_4} {len(owned_countryballs)}/{len(bot_countryballs)} Collected"
    )
    source.embed.colour = discord.Colour.blurple()
    source.embed.set_author(name=user_obj.display_name, icon_url=user_obj.display_avatar.url)

    pages = Pages(source=source, interaction=interaction, compact=True)
    await pages.start()
