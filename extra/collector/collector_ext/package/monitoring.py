"""
Watches the collector cards of monitored tiers. When the owner of a card stops meeting its requirements, a timer starts
and they are warned. If the requirements are met again in time the card is safe, otherwise it is taken back.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from collector_app.models import CollectorInstance, CollectorSettings
from discord.ui import Container, LayoutView, TextDisplay
from discord.utils import format_dt
from django.utils import timezone

from ballsdex.core.utils.background import run_on_bot_loop
from ballsdex.core.utils.notifications import notify_player
from bd_models.models import BallInstance, Player
from settings.models import settings

from .requirements import RequirementStatus, collector_card_special_ids, evaluate_requirements, tier_requirements

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)


class CollectorMonitor:
    # several changes in a row (a bulk give, a trade...) are checked once
    CHECK_DELAY = 5

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._lock = asyncio.Lock()
        self._scheduled: set[int] = set()

    def on_ownership_changed(self, sender, gained: dict, lost: dict, **kwargs):
        """
        Receiver of `bd_models.signals.ownership_changed`, may be called from any thread.
        """
        player_ids = set(gained) | set(lost)
        run_on_bot_loop(lambda: self.schedule_checks(player_ids))

    async def schedule_checks(self, player_ids: set[int]):
        loop = asyncio.get_running_loop()
        for player_id in player_ids - self._scheduled:
            self._scheduled.add(player_id)
            loop.call_later(self.CHECK_DELAY, lambda pid=player_id: run_on_bot_loop(lambda: self._check_later(pid)))

    async def _check_later(self, player_id: int):
        self._scheduled.discard(player_id)
        await self.check_player(player_id)

    def _monitored(self):
        return CollectorInstance.objects.filter(monitored=True, revoked_at__isnull=True).select_related(
            "collector", "level"
        )

    async def check_player(self, player_id: int):
        async for instance in self._monitored().filter(ball_instance__player_id=player_id):
            await self.check_instance(instance)

    async def sweep(self):
        instances = [instance async for instance in self._monitored()]
        for instance in instances:
            try:
                await self.check_instance(instance)
            except Exception:
                log.exception("Failed to check collector card %s", instance.pk)

    async def check_instance(self, instance: CollectorInstance):
        async with self._lock:
            # the instance may have changed while waiting for the lock, or stopped being monitored
            fresh = await self._monitored().filter(pk=instance.pk).afirst()
            if fresh is None:
                return
            instance = fresh
            collector_settings = await CollectorSettings.aload()
            if not collector_settings.monitoring_enabled:
                return

            card = None
            if instance.ball_instance_id is not None:
                card = await BallInstance.all_objects.filter(pk=instance.ball_instance_id).afirst()
            if card is None or card.deleted:
                # the card itself is gone (sold, converted, deleted by an admin), there is nothing to watch anymore
                instance.monitored = False
                instance.at_risk_since = instance.grace_ends_at = None
                await instance.asave(update_fields=("monitored", "at_risk_since", "grace_ends_at"))
                return

            requirements = await sync_to_async(tier_requirements)(instance, include_consumed=False)
            excluded = await sync_to_async(collector_card_special_ids)()
            statuses = await sync_to_async(evaluate_requirements)(card.player_id, requirements, excluded)
            missing = [status for status in statuses if not status.met]
            now = timezone.now()

            if not missing:
                if instance.at_risk_since is not None:
                    instance.at_risk_since = instance.grace_ends_at = None
                    await instance.asave(update_fields=("at_risk_since", "grace_ends_at"))
                    await self.notify(card, instance, "safe")
                return

            if instance.at_risk_since is None:
                instance.at_risk_since = now
                instance.grace_ends_at = now + collector_settings.grace_period
                await instance.asave(update_fields=("at_risk_since", "grace_ends_at"))
                await self.notify(card, instance, "at_risk", missing)
                return

            if instance.grace_ends_at is not None and now >= instance.grace_ends_at:
                if await card.is_locked():
                    return  # the card is in a trade, it will be taken back on the next check
                card.deleted = True
                await card.asave(update_fields=("deleted",))
                instance.revoked_at = now
                await instance.asave(update_fields=("revoked_at",))
                log.info(
                    "Collector card %s (collector %s, tier %s) taken back from player %s",
                    card.pk,
                    instance.collector_id,
                    instance.level_id,
                    card.player_id,
                )
                await self.notify(card, instance, "revoked", missing)

    async def notify(
        self,
        card: BallInstance,
        instance: CollectorInstance,
        event: str,
        missing: list[RequirementStatus] | None = None,
    ):
        player = await Player.objects.aget(pk=card.player_id)
        name = f"**{instance.collector.name}** collector card ({instance.level.name})"
        missing_lines = "\n".join(status.describe(self.bot) for status in missing or [])

        if event == "at_risk":
            title = "\N{WARNING SIGN} Collector card at risk"
            body = (
                f"You don't meet the requirements of your {name} anymore:\n{missing_lines}\n\n"
                f"Get them back {format_dt(instance.grace_ends_at, 'R')} or the card will be taken back."  # type: ignore
            )
        elif event == "safe":
            title = "\N{WHITE HEAVY CHECK MARK} Collector card safe"
            body = f"You meet the requirements of your {name} again, the card is safe."
        else:
            title = "\N{BROKEN HEART} Collector card lost"
            body = (
                f"Your {name} was taken back, the requirements weren't met in time:\n{missing_lines}\n\n"
                "You can claim it again once you have the required treasures."
            )

        view = LayoutView()
        view.add_item(TextDisplay(f"<@{player.discord_id}>"))
        view.add_item(
            Container(
                TextDisplay(f"## {title}"),
                TextDisplay(f"{card.description(include_emoji=True, bot=self.bot)}\n\n{body}"),
                accent_colour=settings.embed_colour,
            )
        )
        # a lost card is found out later, a direct message is more reliable than the last channel used
        await notify_player(
            self.bot, player.discord_id, view, use_recent_channel=event != "revoked", mention=player.can_be_mentioned
        )
