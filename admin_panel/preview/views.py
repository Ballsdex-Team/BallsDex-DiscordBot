from django.contrib import messages
from django.http import HttpRequest, HttpResponse

from ballsdex.core.image_generator.image_gen import draw_card
from ballsdex.core.models import Ball, BallInstance, Special

from .utils import refresh_cache


async def render_ballinstance(request: HttpRequest, ball_pk: int) -> HttpResponse:
    await refresh_cache()

    ball = await Ball.get(pk=ball_pk)
    instance = BallInstance(ball=ball)
    image = draw_card(instance, media_path="./media/")

    response = HttpResponse(content_type="image/png")
    image.save(response, "PNG")  # type: ignore
    return response


async def render_special(request: HttpRequest, special_pk: int) -> HttpResponse:
    await refresh_cache()

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
