from __future__ import annotations

from typing import TYPE_CHECKING

from .renderer_default import draw_card_blackscreen, draw_card_default, draw_card_fullart

if TYPE_CHECKING:
    from typing import Any, Callable

    from PIL import Image

    from bd_models.models import BallInstance

    Renderer = Callable[[BallInstance], tuple[Image.Image, dict[str, Any]]]

DEFAULT_RENDERER = draw_card_default
RENDERERS: dict[str, Renderer] = {
    "": draw_card_default,
    "blackscreen": draw_card_blackscreen,
    "fullart": draw_card_fullart,
}


def get_renderer(ball_instance: BallInstance) -> Renderer:
    if ball_instance.cached_variant and ball_instance.cached_variant.renderer:
        return RENDERERS.get(ball_instance.cached_variant.renderer) or DEFAULT_RENDERER
    if ball_instance.specialcard and ball_instance.specialcard.renderer:
        return RENDERERS.get(ball_instance.specialcard.renderer) or DEFAULT_RENDERER
    if ball_instance.countryball.renderer:
        return RENDERERS.get(ball_instance.countryball.renderer) or DEFAULT_RENDERER

    return DEFAULT_RENDERER


def draw_card(ball_instance: BallInstance) -> tuple[Image.Image, dict[str, Any]]:
    return get_renderer(ball_instance)(ball_instance)
