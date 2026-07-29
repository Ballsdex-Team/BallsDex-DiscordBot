import logging

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from achievement_app.models import AchievementType, progress_achievement
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
    await progress_achievement(instance.player, AchievementType.PLAYTIME)
    await progress_achievement(instance.player, AchievementType.BALL_COUNT)
    if instance.trade_player_id is not None:
        await progress_achievement(
            instance.player,
            AchievementType.RECEIVE_BALL,
            user_id=instance.trade_player.discord_id,  # type: ignore
        )


async def _handle_created_ballinstance(instance: BallInstance):
    await progress_achievement(instance.player, AchievementType.FIRST_CATCH)
    await progress_achievement(instance.player, AchievementType.COMPLETE_GROUP)
    await progress_achievement(instance.player, AchievementType.COMPLETION_PERCENTAGE)
    await progress_achievement(instance.player, AchievementType.CATCH_BALL, instance=instance)
    if instance.catch_date and instance.spawned_time:
        await progress_achievement(
            instance.player,
            AchievementType.FASTEST_CATCHER,
            elapsed_seconds=(instance.catch_date - instance.spawned_time).total_seconds(),
        )
    if instance.specialcard is not None:
        await progress_achievement(instance.player, AchievementType.FIRST_SPECIAL, special=instance.specialcard)
    if instance.favorite:
        await progress_achievement(instance.player, AchievementType.FIRST_FAVORITE_BALL)
