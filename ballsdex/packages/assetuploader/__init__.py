from typing import TYPE_CHECKING

from ballsdex.packages.assetuploader.cog import AssetUploader

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

async def setup(bot: "BallsDexBot"):
    await bot.add_cog(AssetUploader(bot))
