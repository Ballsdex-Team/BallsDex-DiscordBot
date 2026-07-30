import logging

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from achievement_app import models
from achievement_app.models import AchievementType, notify_user, progress_achievement
from bd_models.models import BallInstance

logger = logging.getLogger(__name__)


@receiver(post_save, sender=BallInstance)
def on_instance_created(sender, instance: BallInstance, created: bool, **kwargs):
    if not created:
        return

    transaction.on_commit(lambda: async_to_sync(_handle_created_ballinstance)(instance))


@receiver(post_save, sender=BallInstance)
def on_instance_modified(sender, instance: BallInstance, created: bool, **kwargs):
    if created:
        return

    transaction.on_commit(lambda: async_to_sync(_handle_modified_ballinstance)(instance))


async def _handle_modified_ballinstance(instance: BallInstance):
    unlocked = []
    unlocked += await progress_achievement(instance.player, AchievementType.PLAYTIME)
    unlocked += await progress_achievement(instance.player, AchievementType.BALL_COUNT)
    if instance.trade_player_id is not None:
        unlocked += await progress_achievement(
            instance.player,
            AchievementType.RECEIVE_BALL,
            user_id=instance.trade_player.discord_id,  # type: ignore
        )
    if instance.favorite:
        unlocked += await progress_achievement(instance.player, AchievementType.FIRST_FAVORITE_BALL)

    if unlocked and models._BOT is not None:
        user = await models._BOT.fetch_user(instance.player.discord_id)
        await notify_user(unlocked, user=user)


async def _handle_created_ballinstance(instance: BallInstance):
    unlocked = []
    unlocked += await progress_achievement(instance.player, AchievementType.FIRST_CATCH)
    unlocked += await progress_achievement(instance.player, AchievementType.COMPLETE_GROUP)
    unlocked += await progress_achievement(instance.player, AchievementType.COMPLETION_PERCENTAGE)
    unlocked += await progress_achievement(instance.player, AchievementType.CATCH_BALL, instance=instance)
    if instance.catch_date and instance.spawned_time:
        unlocked += await progress_achievement(
            instance.player,
            AchievementType.FASTEST_CATCHER,
            elapsed_seconds=(instance.catch_date - instance.spawned_time).total_seconds(),
        )
    if instance.specialcard is not None:
        unlocked += await progress_achievement(
            instance.player, AchievementType.FIRST_SPECIAL, special=instance.specialcard
        )

    if unlocked and models._BOT is not None:
        user = await models._BOT.fetch_user(instance.player.discord_id)
        await notify_user(unlocked, user=user)
