from typing import TYPE_CHECKING

from ballsdex.packages.currency.cog import Credits, PowerPoints, Currency

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Credits(bot))
    await bot.add_cog(PowerPoints(bot))
    await bot.add_cog(Currency(bot))
