import logging
import asyncio
import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from ballsdex.core.models import Player
from ballsdex.core.bot import BallsDexBot
from ballsdex.core.utils.logging import log_action

log = logging.getLogger("ballsdex.packages.countryballs")

async def dailycaughtreset(self, bot: BallsDexBot):
    top_players = await Player.all().order_by("-dailycaught").limit(30)
    lines = []
    for i, player in enumerate(top_players, 1):
        lines.append(f"{i}. {player.discord_id} —  {player.dailycaught}")
    lb_text = "\n".join(lines)
    try:
        await log_action(f"Daily caught has been reset.\n{lb_text}", self.bot)
        await Player.filter(dailycaught__gt=0).update(dailycaught=0)
    except Exception as e:
        log.error("An error occured while triggering the daily caught reset", exc_info=e)

scheduler = AsyncIOScheduler()
scheduler.add_job(dailycaughtreset, 'cron', hour=9, minute=0)
scheduler.start()
asyncio.get_event_loop().run_forever()
