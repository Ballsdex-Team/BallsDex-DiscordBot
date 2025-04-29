from bd_models.models import Ball, Economy, Regime, Special, balls, economies, regimes, specials


async def refresh_cache():
    """
    Similar to the bot's `load_cache` function without the fancy display. Also handles
    initializing the connection to Tortoise.

    This must be called on every request, since the image generation relies on cache and we
    do *not* want caching in the admin panel to happen (since we're actively editing stuff).
    """
    balls.clear()
    async for ball in Ball.objects.all():
        balls[ball.pk] = ball

    regimes.clear()
    async for regime in Regime.objects.all():
        regimes[regime.pk] = regime

    economies.clear()
    async for economy in Economy.objects.all():
        economies[economy.pk] = economy

    specials.clear()
    async for special in Special.objects.all():
        specials[special.pk] = special
