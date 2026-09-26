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

from ..access import check as check_access
from ..access import has_early_access, role_ids_of
from ..engine import engine
from ..integrations import INTEGRATIONS, check_integrations
from ..models import EventPass, PlayerQuest, Quest
from ..state import build_state
from ..transformers import EventPassTransform
from .views import PassView

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def _completed_pass_ids(player: Player | None, passes: list[EventPass]) -> set[int]:
    """
    The passes among these that the player has nothing left to do on: every enabled quest completed.

    Counted rather than rebuilt tier by tier, because this runs before a pass is even chosen.
    """
    if player is None or not passes:
        return set()
    ids = [event_pass.pk for event_pass in passes]
    totals: dict[int, int] = {}
    async for pass_id, total in (
        Quest.objects.filter(event_pass_id__in=ids, enabled=True)
        .values_list("event_pass_id")
        .annotate(total=Count("pk"))
    ):
        totals[pass_id] = total
    done: dict[int, int] = {}
    async for pass_id, count in (
        PlayerQuest.objects.filter(player=player, quest__event_pass_id__in=ids, completed_at__isnull=False)
        .values_list("quest__event_pass_id")
        .annotate(count=Count("pk", distinct=True))
    ):
        done[pass_id] = count
    return {pass_id for pass_id, total in totals.items() if total and done.get(pass_id, 0) >= total}


async def _open_to(player: Player | None, event_pass: EventPass, role_ids: set[int] | None) -> bool:
    """
    Whether this player may take part in a pass, used to leave the ones reserved to others out of the default.
    """
    if player is None:
        return True
    verdict = await check_access(player.pk, event_pass, role_ids=role_ids)
    return verdict.allowed or verdict.joined


async def _pick(candidates: list[EventPass], player: Player | None, role_ids: set[int] | None) -> EventPass | None:
    """
    The first pass of the list this player should land on: one they can take part in, and that they have not
    already finished. A pass they finished still comes back when it is the only thing left, rather than greeting
    them with nothing.
    """
    open_ones = [event_pass for event_pass in candidates if await _open_to(player, event_pass, role_ids)]
    if not open_ones:
        return None
    completed = await _completed_pass_ids(player, open_ones)
    unfinished = [event_pass for event_pass in open_ones if event_pass.pk not in completed]
    return (unfinished or open_ones)[0]


async def current_pass(
    chosen: EventPass | None, *, staff: bool = False, player: Player | None = None, role_ids: set[int] | None = None
) -> EventPass | None:
    """
    The pass a command works on: the one the player picked, or the one they should land on.

    Named explicitly, a pass is always opened — that is how staff check a draft, and how a player reaches an event
    that is not their default. With no name, the choice walks the running passes by `position` and takes the first
    one that is **theirs to play**: not reserved to somebody else, and not one they have already finished. Someone
    who finished everything still gets their last pass back rather than being told there is no event.

    An event that is over never hides one that is running, whatever its position. Only once nothing is running does
    a finished pass come back, and only while its claim window is open, so players who completed it can still
    collect. Staff also see the drafts, which are there to be looked at and never progress.
    """
    if chosen is not None:
        if chosen.status == EventPass.Status.DRAFT and not staff:
            return None
        return chosen
    now = timezone.now()
    published = EventPass.objects.filter(status=EventPass.Status.ACTIVE, starts_at__lte=now)
    running = [event_pass async for event_pass in published.filter(ends_at__gte=now).order_by("position", "-starts_at")]
    # a pass whose early start has come is running too, for the players it let in early
    early = [
        event_pass
        async for event_pass in EventPass.objects.filter(
            status=EventPass.Status.ACTIVE, early_starts_at__lte=now, starts_at__gt=now
        ).order_by("position", "-starts_at")
        if player is not None and await has_early_access(player.pk, event_pass)
    ]
    found = await _pick(early + running, player, role_ids)
    if found is None:
        over = [
            event_pass async for event_pass in published.filter(claim_until__gte=now).order_by("position", "-ends_at")
        ]
        found = await _pick(over, player, role_ids)
    if found or not staff:
        return found
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
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        roles = role_ids_of(interaction.user, self.bot)
        chosen = await current_pass(event_pass, staff=await is_staff(interaction), player=player, role_ids=roles)
        if chosen is None:
            await interaction.followup.send("There is no event running right now.", ephemeral=True)
            return
        # the only place a player can enter a restricted pass: their Discord roles are only readable here,
        # and the verdict written down now is what the engine reads for everything that follows
        access = await check_access(player.pk, chosen, role_ids=roles, join=True)
        state = await build_state(player, chosen)
        state.access = access if access.restricted else None
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
        viewer = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        chosen = await current_pass(
            event_pass,
            staff=await is_staff(interaction),
            player=viewer,
            role_ids=role_ids_of(interaction.user, self.bot),
        )
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
        viewer = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        chosen = await current_pass(
            event_pass,
            staff=await is_staff(interaction),
            player=viewer,
            role_ids=role_ids_of(interaction.user, self.bot),
        )
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
            f"{sum(1 for tier in my_state.tiers if tier.finished)} tiers finished",
            f"**{user.display_name}**: {their_state.completed_count}/{their_state.total_count} quests, "
            f"{sum(1 for tier in their_state.tiers if tier.finished)} tiers finished",
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
