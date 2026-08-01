import logging

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from achievement_app import models
from achievement_app.models import AchievementType, notify_user, progress_achievement
from bd_models.models import BallInstance, GuildConfig, Player

logger = logging.getLogger(__name__)


@receiver(post_save, sender=BallInstance)
def on_instance_saved(sender, instance: BallInstance, created: bool, **kwargs):
    transaction.on_commit(lambda: async_to_sync(_handle_created_ballinstance)(instance))


async def _handle_created_ballinstance(instance: BallInstance, notify: bool = True):
    unlocked = []
    player = await Player.objects.aget(pk=instance.player_id)
    unlocked += await progress_achievement(player, AchievementType.FIRST_CATCH)
    unlocked += await progress_achievement(player, AchievementType.COMPLETE_GROUP)
    unlocked += await progress_achievement(player, AchievementType.COMPLETION_PERCENTAGE)
    unlocked += await progress_achievement(player, AchievementType.CATCH_BALL, instance=instance)
    if instance.catch_date and instance.spawned_time:
        unlocked += await progress_achievement(
            player,
            AchievementType.FASTEST_CATCHER,
            elapsed_seconds=(instance.catch_date - instance.spawned_time).total_seconds(),
        )
    if instance.specialcard is not None:
        unlocked += await progress_achievement(player, AchievementType.FIRST_SPECIAL, special=instance.specialcard)
    unlocked += await progress_achievement(player, AchievementType.PLAYTIME)
    unlocked += await progress_achievement(player, AchievementType.BALL_COUNT)
    if instance.trade_player_id is not None:
        unlocked += await progress_achievement(
            player,
            AchievementType.RECEIVE_BALL,
            user_id=instance.trade_player.discord_id,  # type: ignore
        )
    if instance.favorite:
        unlocked += await progress_achievement(player, AchievementType.FIRST_FAVORITE_BALL)

    if unlocked and notify and models._BOT is not None:
        user = await models._BOT.fetch_user(player.discord_id)
        if instance.server_id:
            guild = await models._BOT.fetch_guild(instance.server_id)
            config = await GuildConfig.objects.aget_or_none(guild_id=instance.server_id)
            if not config or not config.spawn_channel:
                await notify_user(unlocked, user=user)
                return unlocked
            channel = await guild.fetch_channel(config.spawn_channel)
            await notify_user(unlocked, user=user, channel=channel)  # type: ignore
        else:
            await notify_user(unlocked, user=user)

    return unlocked
