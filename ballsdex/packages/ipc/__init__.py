from ballsdex.packages.ipc.cog import IPC


async def setup(bot):
    await bot.wait_until_ready()
    await bot.add_cog(IPC(bot))
