from typing import TYPE_CHECKING

from ballsdex.core.game_events import bus

from ..engine import engine
from ..integrations import log_integration_warnings
from ..notifications import PassNotifier
from .cog import EventPassCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

SUBSCRIBER = "event_pass"


async def setup(bot: "BallsDexBot"):
    engine.configure(bot, PassNotifier(bot))
    bus.subscribe(SUBSCRIBER, engine.handle_event, listens_to_command=engine.listens_to_command)
    # say it out loud at startup: a quest whose package is missing would silently never progress
    quests = await engine.active_quests()
    log_integration_warnings({quest.type for quest in quests})
    await bot.add_cog(EventPassCog(bot))


async def teardown(bot: "BallsDexBot"):
    bus.unsubscribe(SUBSCRIBER)
    engine.configure(None, None)
