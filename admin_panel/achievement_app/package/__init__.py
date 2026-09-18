from typing import TYPE_CHECKING

from bd_models.signals import ownership_changed

from ..engine import engine
from ..notifications import AchievementNotifier
from .cog import Achievement

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

DISPATCH_UID = "achievement_engine"


async def setup(bot: "BallsDexBot"):
    engine.configure(bot, AchievementNotifier(bot))
    ownership_changed.connect(engine.on_ownership_changed, dispatch_uid=DISPATCH_UID)
    await bot.add_cog(Achievement(bot))


async def teardown(bot: "BallsDexBot"):
    ownership_changed.disconnect(dispatch_uid=DISPATCH_UID)
    engine.configure(None, None)
