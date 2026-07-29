import asyncio
import logging

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from achievement_app.models import AchievementType, progress_achievement
from bd_models.models import Trade

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Trade)
def on_trade_created(sender, instance: Trade, created: bool, **kwargs):
    if not created:
        return

    transaction.on_commit(lambda: async_to_sync(_handle_created_trade)(instance))


async def _handle_created_trade(instance: Trade):
    await progress_achievement(instance.player1, AchievementType.FIRST_TRADE)
    await progress_achievement(instance.player2, AchievementType.FIRST_TRADE)
    await progress_achievement(instance.player2, AchievementType.COMPLETE_TRADE, received_coins=instance.player1_money)
    await progress_achievement(instance.player1, AchievementType.COMPLETE_TRADE, received_coins=instance.player2_money)
