from fastapi import Depends, Path
from tortoise.exceptions import DoesNotExist
from starlette.requests import Request
from starlette.responses import Response

from fastapi_admin.app import app
from fastapi_admin.depends import get_resources
from fastapi_admin.template import templates

from ballsdex.core.models import Ball, BallInstance, Player, GuildConfig, Special


@app.get("/")
async def home(
    request: Request,
    resources=Depends(get_resources),
):
    return templates.TemplateResponse(
        "dashboard.html",
        context={
            "request": request,
            "resources": resources,
            "ball_count": await Ball.all().count(),
            "player_count": await Player.all().count(),
            "guild_count": await GuildConfig.all().count(),
            "resource_label": "Dashboard",
            "page_pre_title": "overview",
            "page_title": "Dashboard",
        },
    )


@app.get("/ball/generate/{pk}")
async def generate_card(
    request: Request,
    pk: str = Path(...),
):
    ball = await Ball.get(pk=pk)
    temp_instance = BallInstance(ball=ball, player=await Player.first(), count=1)
    buffer = temp_instance.draw_card()
    return Response(content=buffer.read(), media_type="image/png")


@app.get("/special/generate/{pk}")
async def generate_special_card(
    request: Request,
    pk: str = Path(...),
):
    special = await Special.get(pk=pk)
    try:
        ball = await Ball.first()
    except DoesNotExist:
        return Response(
            content="At least one ball must exist", status_code=422, media_type="text/html"
        )
    temp_instance = BallInstance(ball=ball, special=special, player=await Player.first(), count=1)
    buffer = temp_instance.draw_card()
    return Response(content=buffer.read(), media_type="image/png")
