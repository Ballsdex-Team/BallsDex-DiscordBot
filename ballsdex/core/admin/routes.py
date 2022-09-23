from fastapi import Depends, Path
from starlette.requests import Request
from starlette.responses import Response

from fastapi_admin.app import app
from fastapi_admin.depends import get_resources
from fastapi_admin.template import templates

from ballsdex.core.models import Ball, BallInstance, Player, GuildConfig


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
