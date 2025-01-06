import os

from django.http import HttpRequest, HttpResponse
from tortoise import Tortoise

from ballsdex.__main__ import init_tortoise
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


async def render_image(request: HttpRequest, ball_pk: int) -> HttpResponse:
    from ballsdex.core.image_generator.image_gen import draw_card

    if not Tortoise._inited:
        await init_tortoise(os.environ["BALLSDEXBOT_DB_URL"])
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

    ball = await Ball.get(pk=ball_pk)
    instance = BallInstance(ball=ball, count=1)
    image = draw_card(instance)

    response = HttpResponse(content_type="image/png")
    image.save(response, "PNG")  # type: ignore
    return response
