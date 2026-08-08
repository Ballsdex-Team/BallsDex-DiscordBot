from typing import TYPE_CHECKING

from .cog import Vote
from .webhook import start_webhook_server

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    from ..models import VoteSettings

    vote_settings = await VoteSettings.aload()
    await bot.add_cog(Vote(bot, vote_settings))
    await start_webhook_server(bot, vote_settings)
