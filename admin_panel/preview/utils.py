import os

from tortoise import Tortoise

from ballsdex.__main__ import init_tortoise
from ballsdex.core.models import (
    Ball,
    Economy,
    Regime,
    Special,
    balls,
    economies,
    regimes,
    specials,
)


async def refresh_cache():
    """
    Similar to the bot's `load_cache` function without the fancy display. Also handles
    initializing the connection to Tortoise.

    This must be called on every request, since the image generation relies on cache and we
    do *not* want caching in the admin panel to happen (since we're actively editing stuff).
    """
    if not Tortoise._inited:
        await init_tortoise(os.environ["BALLSDEXBOT_DB_URL"], skip_migrations=True)
    balls.clear()
    for ball in await Ball.all():
        balls[ball.pk] = ball

    regimes.clear()
    for regime in await Regime.all():
        regimes[regime.pk] = regime

    economies.clear()
    for economy in await Economy.all():
        economies[economy.pk] = economy

    specials.clear()
    for special in await Special.all():
        specials[special.pk] = special
