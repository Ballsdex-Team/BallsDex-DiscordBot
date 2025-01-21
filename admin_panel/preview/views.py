import os

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from tortoise import Tortoise

from ballsdex.__main__ import init_tortoise
from ballsdex.core.image_generator.image_gen import draw_card
from ballsdex.core.models import (
    Ball,
    BallInstance,
    Economy,
    Regime,
    Special,
    balls,
    economies,
    regimes,
    specials,
)


async def _refresh_cache():
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


async def render_ballinstance(request: HttpRequest, ball_pk: int) -> HttpResponse:
    await _refresh_cache()

    ball = await Ball.get(pk=ball_pk)
    instance = BallInstance(ball=ball)
    image = draw_card(instance, media_path="./media/")

    response = HttpResponse(content_type="image/png")
    image.save(response, "PNG")  # type: ignore
    return response


async def render_special(request: HttpRequest, special_pk: int) -> HttpResponse:
    await _refresh_cache()

    ball = await Ball.first()
    if ball is None:
        messages.warning(
            request,
            "You must create a countryball before being able to generate a special's preview.",
        )
        return HttpResponse(status_code=422)

    special = await Special.get(pk=special_pk)
    instance = BallInstance(ball=ball, special=special)
    image = draw_card(instance, media_path="./media/")

    response = HttpResponse(content_type="image/png")
    image.save(response, "PNG")  # type: ignore
    return response
