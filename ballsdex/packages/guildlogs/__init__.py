from typing import TYPE_CHECKING

from ballsdex.packages.guildlogs.cog import GuildLogs

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(GuildLogs(bot))
