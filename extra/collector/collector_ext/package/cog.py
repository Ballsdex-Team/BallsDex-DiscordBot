from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from collector_app.models import Collector as CollectorModel
from collector_app.models import CollectorInstance, CollectorRequirement, CollectorTier
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Separator, TextDisplay
from discord.utils import format_dt
from django.db.models import Prefetch

from ballsdex.core.discord import Container, LayoutView
from ballsdex.core.utils.menus import Menu, TextFormatter, TextSource
from ballsdex.core.utils.menus.old import FieldPageSource, Pages
from bd_models.models import Player
from bd_models.signals import ownership_changed
from settings.models import settings

from .monitoring import CollectorMonitor
from .requirements import (
    collector_card_special_ids,
    evaluate_requirements,
    evaluate_with_counts,
    owned_counts,
    tier_requirements,
)
from .transformers import CollectorEnabledTransform
from .views import CollectorClaimView, CollectorPage, TierState

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

MONITOR_DISPATCH_UID = "collector_monitoring"


class Collector(commands.GroupCog):
    """
    Claim your collector card!
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.monitor = CollectorMonitor(bot)

    async def cog_load(self):
        ownership_changed.connect(self.monitor.on_ownership_changed, dispatch_uid=MONITOR_DISPATCH_UID)
        self.monitoring_sweep.start()

    async def cog_unload(self):
        ownership_changed.disconnect(dispatch_uid=MONITOR_DISPATCH_UID)
        self.monitoring_sweep.cancel()

    @tasks.loop(minutes=10)
    async def monitoring_sweep(self):
        await self.monitor.sweep()

    @monitoring_sweep.before_loop
    async def before_monitoring_sweep(self):
        await self.bot.wait_until_ready()

    @app_commands.command()
    @app_commands.choices(
        show=[
            app_commands.Choice(name="Ready to claim", value="ready"),
            app_commands.Choice(name="Every collector", value="all"),
        ]
    )
    async def claim(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        collector: CollectorEnabledTransform | None = None,
        show: app_commands.Choice[str] | None = None,
    ):
        """
        Claim a collector card.

        Parameters
        ----------
        collector: Collector
            The collector to claim. Leave it empty to browse the collectors one by one.
        show: str
            When browsing, show the collectors you can claim right now or every collector.
        """
        await interaction.response.defer(thinking=True)
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        only_ready = show is None or show.value == "ready"

        if collector is not None:
            tiers = [
                tier
                async for tier in CollectorTier.objects.filter(collector=collector, enabled=True)
                .select_related("level")
                .order_by("level__position", "level_id")
            ]
            if not tiers:
                await interaction.followup.send("This collector can't be claimed right now.", ephemeral=True)
                return
            pages = [CollectorPage(collector, tiers)]
        else:
            pages = await self._browse_pages(player, only_ready=only_ready)
            if not pages:
                await interaction.followup.send(
                    "You can't claim any collector card right now. Use `show: Every collector` to see them all "
                    "and what you're missing."
                    if only_ready
                    else f"{settings.bot_name} doesn't have any collector active.",
                    ephemeral=True,
                )
                return

        view = CollectorClaimView(self.bot, player, pages)
        view.restrict_author(interaction.user.id)
        await view.refresh()
        view.message = await interaction.followup.send(view=view, wait=True)

    async def _browse_pages(self, player: Player, *, only_ready: bool) -> list[CollectorPage]:
        """
        One page per collector, with the player's progress on every tier. Everything is counted from a single
        summary of the player's treasures, so browsing hundreds of collectors stays cheap.
        """
        tiers = [
            tier
            async for tier in CollectorTier.objects.filter(enabled=True)
            .select_related("level", "collector")
            .order_by("collector__name", "level__position", "level_id")
        ]
        tiers = [tier for tier in tiers if tier.collector.active]
        if not tiers:
            return []

        requirements: dict[tuple[int, int], list[CollectorRequirement]] = defaultdict(list)
        async for requirement in CollectorRequirement.objects.filter(
            collector_id__in={tier.collector_id for tier in tiers}
        ).select_related("ball", "special"):
            requirements[(requirement.collector_id, requirement.level_id)].append(requirement)
        claimed = {
            (collector_id, level_id)
            async for collector_id, level_id in CollectorInstance.objects.filter(
                player=player, revoked_at__isnull=True
            ).values_list("collector_id", "level_id")
        }
        counts = await sync_to_async(owned_counts)(player.pk)

        pages: list[CollectorPage] = []
        by_collector: dict[int, CollectorPage] = {}
        for tier in tiers:
            page = by_collector.get(tier.collector_id)
            if page is None:
                page = by_collector[tier.collector_id] = CollectorPage(tier.collector, [])
                pages.append(page)
            page.tiers.append(tier)
            page.states.append(
                TierState(
                    tier=tier,
                    claimed=(tier.collector_id, tier.level_id) in claimed,
                    statuses=evaluate_with_counts(counts, requirements[(tier.collector_id, tier.level_id)]),
                )
            )

        if only_ready:
            return [page for page in pages if page.ready]
        pages.sort(key=lambda page: (not page.ready, page.missing_count, page.collector.name))
        return pages

    @app_commands.command(name="list")
    async def collector_list(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check all active collectors.
        """
        await interaction.response.defer(thinking=True)
        tiers = CollectorTier.objects.filter(enabled=True).select_related("level").order_by("level__position")
        requirements = CollectorRequirement.objects.select_related("ball", "special").order_by("amount", "pk")
        collectors = [
            x
            async for x in CollectorModel.objects.prefetch_related(
                Prefetch("tiers", tiers), Prefetch("requirements", requirements)
            ).order_by("name")
            if x.active
        ]
        collectors = [x for x in collectors if x.tiers.all()]  # type: ignore

        if not collectors:
            await interaction.followup.send(f"{settings.bot_name} doesn't have any collectors active.", ephemeral=True)
            return

        entries: list[tuple[str, str]] = []
        for collector in collectors:
            requirements_by_level: dict[int, list[str]] = defaultdict(list)
            for requirement in collector.requirements.all():
                name = " ".join(
                    x
                    for x in (
                        requirement.cached_special.name if requirement.cached_special else "",
                        requirement.cached_ball.country if requirement.cached_ball else "",
                    )
                    if x
                )
                requirements_by_level[requirement.level_id].append(
                    f"{requirement.amount}× {name or settings.plural_collectible_name}"
                )

            lines = [f"{settings.collectible_name.title()}: {collector.cached_ball}"]
            for tier in collector.tiers.all():
                soon = "" if tier.level.claimable else " *(not available yet)*"
                listed = ", ".join(requirements_by_level[tier.level_id]) or "no requirement"
                lines.append(f"**{tier.level.name}**{soon}: {listed}")
            entries.append((collector.name, "\n".join(lines)[:1024]))

        source = FieldPageSource(entries, per_page=3)
        source.embed.title = "Active Collector List"
        pages = Pages(source, interaction=interaction)
        await pages.start()

    @app_commands.command()
    async def status(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check your collector cards, and the ones you're about to lose.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        player = await Player.objects.aget_or_none(discord_id=interaction.user.id)
        instances = []
        if player:
            instances = [
                instance
                async for instance in CollectorInstance.objects.filter(player=player, revoked_at__isnull=True)
                .select_related("collector", "level")
                .order_by("collector__name", "level__position")
            ]
        if not instances:
            await interaction.followup.send("You haven't claimed any collector card yet.", ephemeral=True)
            return

        at_risk = [instance for instance in instances if instance.at_risk_since]
        excluded = await sync_to_async(collector_card_special_ids)()
        lines = []
        if at_risk:
            lines.append("## \N{WARNING SIGN} At risk")
            for instance in at_risk:
                requirements = await sync_to_async(tier_requirements)(instance, include_consumed=False)
                statuses = await sync_to_async(evaluate_requirements)(player.pk, requirements, excluded)  # type: ignore
                missing = "\n".join(status.describe(self.bot) for status in statuses if not status.met)
                lines.append(
                    f"**{instance.collector.name}** ({instance.level.name}), taken back "
                    f"{format_dt(instance.grace_ends_at, 'R')} unless you get back:\n{missing}\n"  # type: ignore
                )
        lines.append("## Your collector cards")
        for instance in instances:
            if instance.at_risk_since:
                continue
            icon = "\N{SHIELD}" if instance.monitored else "\N{SMALL BLUE DIAMOND}"
            lines.append(f"{icon} **{instance.collector.name}** ({instance.level.name})")
        lines.append(
            "\n-# \N{SHIELD} cards are taken back if you stop meeting their requirements for too long, "
            "\N{SMALL BLUE DIAMOND} cards were claimed before that rule and are never taken back."
        )

        view = LayoutView()
        display = TextDisplay("")
        view.add_item(
            Container(
                TextDisplay(f"# {interaction.user.display_name}'s collector cards"),
                Separator(),
                display,
                accent_colour=settings.embed_colour,
            )
        )
        menu = Menu(self.bot, view, TextSource("\n".join(lines), page_length=3000), TextFormatter(display))
        await menu.init()
        await interaction.followup.send(view=view, ephemeral=True)
