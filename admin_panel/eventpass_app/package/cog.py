"""
The /pass commands: look at an event pass, claim what you finished, and see how you compare to other players.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Separator, TextDisplay
from django.db.models import Count, Q
from django.utils import timezone

from ballsdex.core.discord import Container, LayoutView
from ballsdex.core.utils.leaderboard import EXTRA_ROWS, LEADERBOARD_SIZE, send_leaderboard
from ballsdex.core.utils.utils import is_staff
from bd_models.models import Player

from ..engine import engine
from ..integrations import INTEGRATIONS, check_integrations
from ..models import EventPass, PlayerQuest
from ..state import build_state
from ..transformers import EventPassTransform
from .views import PassView

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def current_pass(chosen: EventPass | None, *, staff: bool = False) -> EventPass | None:
    """
    The pass a command works on: the one the player picked, or the one running right now.

    Staff also see the passes still in draft, whatever their dates, so an event can be checked in Discord before it
    is published. Nothing progresses in a draft, it is only there to be looked at.
    """
    if chosen is not None:
        if chosen.status == EventPass.Status.DRAFT and not staff:
            return None
        return chosen
    now = timezone.now()
    running = (
        await EventPass.objects.filter(status=EventPass.Status.ACTIVE, starts_at__lte=now)
        .order_by("position", "-starts_at")
        .afirst()
    )
    if running or not staff:
        return running
    return await EventPass.objects.filter(status=EventPass.Status.DRAFT).order_by("position", "-starts_at").afirst()


class EventPassCog(commands.GroupCog, name="Event pass", group_name="pass"):
    """
    Event passes: quests, tiers and rewards.
    """

    def __init__(self, bot: BallsDexBot):
        self.bot = bot

    @app_commands.command(name="view")
    async def view_pass(self, interaction: discord.Interaction[BallsDexBot], event_pass: EventPassTransform | None):
        """
        Look at an event pass, your progress on it, and claim your rewards.

        Parameters
        ----------
        event_pass: EventPass
            The pass to open. Defaults to the one running right now.
        """
        await interaction.response.defer(thinking=True)
        chosen = await current_pass(event_pass, staff=await is_staff(interaction))
        if chosen is None:
            await interaction.followup.send("There is no event running right now.", ephemeral=True)
            return
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        state = await build_state(player, chosen)
        view = PassView(self.bot, player, state)
        view.refresh()
        view.message = await interaction.followup.send(view=view, wait=True)

    @app_commands.command()
    async def leaderboard(self, interaction: discord.Interaction[BallsDexBot], event_pass: EventPassTransform | None):
        """
        The players who completed the most quests of an event pass.

        Parameters
        ----------
        event_pass: EventPass
            The pass to rank. Defaults to the one running right now.
        """
        await interaction.response.defer(thinking=True)
        chosen = await current_pass(event_pass, staff=await is_staff(interaction))
        if chosen is None:
            await interaction.followup.send("There is no event running right now.", ephemeral=True)
            return

        ranking = (
            Player.objects.filter(
                pk__in=PlayerQuest.objects.filter(quest__event_pass=chosen, completed_at__isnull=False).values(
                    "player_id"
                )
            )
            .annotate(
                completed=Count(
                    "event_pass_quests",
                    filter=Q(
                        event_pass_quests__quest__event_pass=chosen, event_pass_quests__completed_at__isnull=False
                    ),
                )
            )
            .order_by("-completed")
            .values_list("discord_id", "completed")[: LEADERBOARD_SIZE + EXTRA_ROWS]
        )
        rows = [row async for row in ranking]
        if not rows:
            await interaction.followup.send("Nobody completed a quest of this pass yet.", ephemeral=True)
            return
        total = await PlayerQuest.objects.filter(quest__event_pass=chosen, completed_at__isnull=False).acount()
        await send_leaderboard(
            interaction,
            title=f"{chosen.emoji} {chosen.name}".strip(),
            subtitle=f"{total:,} quests completed by {len(rows):,} players",
            ranking=rows,
            describe=lambda completed: f"Quests completed: {completed:,}",
        )

    @app_commands.command()
    async def compare(
        self, interaction: discord.Interaction[BallsDexBot], user: discord.User, event_pass: EventPassTransform | None
    ):
        """
        Compare your progress on a pass with another player.

        Parameters
        ----------
        user: discord.User
            The player to compare yourself with.
        event_pass: EventPass
            The pass to compare. Defaults to the one running right now.
        """
        await interaction.response.defer(thinking=True)
        chosen = await current_pass(event_pass, staff=await is_staff(interaction))
        if chosen is None:
            await interaction.followup.send("There is no event running right now.", ephemeral=True)
            return
        if user.bot:
            await interaction.followup.send("Bots don't play.", ephemeral=True)
            return

        mine, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        theirs = await Player.objects.aget_or_none(discord_id=user.id)
        if theirs is None:
            await interaction.followup.send(f"{user.display_name} has no account yet.", ephemeral=True)
            return

        my_state = await build_state(mine, chosen)
        their_state = await build_state(theirs, chosen)
        lines = [
            f"**{interaction.user.display_name}**: {my_state.completed_count}/{my_state.total_count} quests, "
            f"{sum(1 for tier in my_state.tiers if tier.unlocked)} tiers unlocked",
            f"**{user.display_name}**: {their_state.completed_count}/{their_state.total_count} quests, "
            f"{sum(1 for tier in their_state.tiers if tier.unlocked)} tiers unlocked",
        ]
        ahead = my_state.completed_count - their_state.completed_count
        if ahead > 0:
            lines.append(f"-# You are ahead by {ahead} quest{'s' if ahead > 1 else ''}.")
        elif ahead < 0:
            lines.append(f"-# You are behind by {-ahead} quest{'s' if ahead < -1 else ''}.")
        else:
            lines.append("-# You are neck and neck.")

        view = LayoutView()
        view.restrict_author(interaction.user.id)
        view.add_item(
            Container(
                TextDisplay(f"# {chosen.emoji} {chosen.name}".strip()),
                Separator(),
                TextDisplay("\n".join(lines)),
                accent_colour=chosen.accent_colour,
            )
        )
        await interaction.followup.send(view=view)

    @app_commands.command()
    @app_commands.default_permissions(administrator=True)
    async def diagnostics(self, interaction: discord.Interaction[BallsDexBot]):
        """
        Staff only: check that every package the quests need is installed and listening.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        quests = await engine.active_quests()
        warnings = check_integrations({quest.type for quest in quests})
        lines = [f"**Active quests loaded:** {len(quests)}"]
        for integration in INTEGRATIONS:
            mark = "\N{WHITE HEAVY CHECK MARK}" if integration.installed else "\N{CROSS MARK}"
            lines.append(f"{mark} {integration.label}")
        if warnings:
            lines.append("")
            lines.extend(f"\N{WARNING SIGN}\N{VARIATION SELECTOR-16} {warning}" for warning in warnings)
        else:
            lines.append("\n-# Every package the current quests need is installed.")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
