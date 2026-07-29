import logging

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from achievement_app.models import AchievementType, progress_achievement
from bd_models.models import Friendship

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Friendship)
def on_friendship_created(sender, instance: Friendship, created: bool, **kwargs):
    if not created:
        return

    transaction.on_commit(lambda: async_to_sync(_handle_created_friendship)(instance))


async def _handle_created_friendship(instance: Friendship):
    await progress_achievement(instance.player1, AchievementType.FIRST_FRIEND)
    await progress_achievement(instance.player1, AchievementType.HAVE_FRIEND)
    await progress_achievement(instance.player2, AchievementType.FIRST_FRIEND)
    await progress_achievement(instance.player2, AchievementType.HAVE_FRIEND)
