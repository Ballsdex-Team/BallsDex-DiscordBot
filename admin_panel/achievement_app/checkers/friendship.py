import logging

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from achievement_app import models
from achievement_app.models import AchievementType, notify_user, progress_achievement
from bd_models.models import Friendship

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Friendship)
def on_friendship_created(sender, instance: Friendship, created: bool, **kwargs):
    if not created:
        return

    transaction.on_commit(lambda: async_to_sync(_handle_created_friendship)(instance))


async def _handle_created_friendship(instance: Friendship):
    p1_unlocked = []
    p2_unlocked = []

    p1_unlocked += await progress_achievement(instance.player1, AchievementType.FIRST_FRIEND)
    p1_unlocked += await progress_achievement(instance.player1, AchievementType.HAVE_FRIEND)
    p2_unlocked += await progress_achievement(instance.player2, AchievementType.FIRST_FRIEND)
    p2_unlocked += await progress_achievement(instance.player2, AchievementType.HAVE_FRIEND)

    if models._BOT is not None:
        if p1_unlocked:
            user1 = await models._BOT.fetch_user(instance.player1.discord_id)
            await notify_user(p1_unlocked, user=user1)

        if p2_unlocked:
            user2 = await models._BOT.fetch_user(instance.player2.discord_id)
            await notify_user(p2_unlocked, user=user2)
