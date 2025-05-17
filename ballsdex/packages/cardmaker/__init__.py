from typing import TYPE_CHECKING

from ballsdex.packages.cardmaker.cog import CardMaker

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

async def setup(bot: "BallsDexBot"):
    await bot.add_cog(CardMaker(bot))