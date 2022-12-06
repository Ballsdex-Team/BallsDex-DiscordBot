import discord
import logging
import random
import string

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
        partial_countryballs = await Ball.filter(enabled=True).only("id", "rarity")
        if not partial_countryballs:
            raise RuntimeError("No ball to spawn")
        pks = [x.pk for x in partial_countryballs]
        rarities = [x.rarity for x in partial_countryballs]
        pk = random.choices(population=pks, weights=rarities, k=1)[0]
        return cls(await Ball.get(pk=pk))

    async def spawn(self, channel: discord.abc.Messageable):
        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
            return "".join(random.choices(source, k=15))

        extension = self.model.wild_card.split(".")[-1]
        file_location = "." + self.model.wild_card
        file_name = f"nt_{generate_random_name()}.{extension}"
        try:
            self.message = await channel.send(
                "A wild countryball appeared!",
                view=CatchView(self),
                file=discord.File(file_location, filename=file_name),
            )
        except discord.Forbidden:
            log.error(f"Missing permission to spawn ball in channel {channel}.")
        except discord.HTTPException:
            log.error("Failed to spawn ball", exc_info=True)
