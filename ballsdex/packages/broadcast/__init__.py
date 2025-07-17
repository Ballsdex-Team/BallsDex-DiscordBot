from .cog import Broadcast

async def setup(bot):
    await bot.add_cog(Broadcast(bot)) 