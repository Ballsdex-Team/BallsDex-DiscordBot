from typing import TYPE_CHECKING

from ballsdex.core.game_events import bus

from ..engine import engine
from ..notifications import AchievementNotifier
from .cog import Achievement

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

SUBSCRIBER = "achievements"


async def setup(bot: "BallsDexBot"):
    engine.configure(bot, AchievementNotifier(bot))
    bus.subscribe(SUBSCRIBER, engine.handle_event, listens_to_command=engine.listens_to_command)
    await bot.add_cog(Achievement(bot))


async def teardown(bot: "BallsDexBot"):
    bus.unsubscribe(SUBSCRIBER)
    engine.configure(None, None)
