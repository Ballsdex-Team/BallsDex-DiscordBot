import discord
import logging
import random

from ballsdex.core.models import Ball
from ballsdex.packages.countryballs.components import CatchView

log = logging.getLogger("ballsdex.packages.countryballs")


class CountryBall:
    def __init__(self, model: Ball):
        self.name = model.country
        self.model = model
        self.message: discord.Message = discord.utils.MISSING
        self.catched = False

    @classmethod
    async def get_random(cls):
        partial_countryballs = await Ball.all().only("id", "rarity")
        if not partial_countryballs:
            raise RuntimeError("No ball to spawn")
        pks = [x.pk for x in partial_countryballs]
        rarities = [x.rarity for x in partial_countryballs]
        pk = random.choices(population=pks, weights=rarities, k=1)[0]
        return cls(await Ball.get(pk=pk))

    async def spawn(self, channel: discord.abc.Messageable):
        try:
            self.message = await channel.send(
                "A wild countryball appeared!",
                view=CatchView(self),
                file=discord.File("." + self.model.wild_card),
            )
        except discord.HTTPException:
            log.error("Failed to spawn ball", exc_info=True)
