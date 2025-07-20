from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ballsdex.core.image_generator.default_card_template import DEFAULT_CARD_TEMPLATE

if TYPE_CHECKING:
    from ballsdex.core.models import BallInstance

# ===== TIP =====
#
# If you want to quickly test the image generation, there is a CLI tool to quickly generate
# test images locally, without the bot or the admin panel running:
#
# With Docker: "docker compose run admin-panel python3 manage.py preview > image.png"
# Without: "cd admin_panel && poetry run python3 manage.py preview"
#
# This will either create a file named "image.png" or directly display it using your system's
# image viewer. There are options available to specify the ball or the special background,
# use the "--help" flag to view all options.

SOURCES_PATH = Path(os.path.dirname(os.path.abspath(__file__)), "./src")


def draw_card(
    ball_instance: "BallInstance",
    # template: dict[str, dict[str, Any]],
    media_path: str = "./admin_panel/media/",
) -> tuple[Image.Image, dict[Any, Any]]:
    template = None
    if ball_instance.card_template:
        template = ball_instance.card_template.template
    if not template:
        template = DEFAULT_CARD_TEMPLATE

    template = CardTemplate(**template)  # type: ignore

    image = Image.new("RGB", (template.canvas_size[0], template.canvas_size[1]))
    prior_layer_info: dict[str, LayerInfo] = {}

    layers = (TemplateLayer(**layer) for layer in template.layers)
    for layer in layers:
        draw_layer(image, layer, ball_instance, media_path, prior_layer_info)

    return image, {"format": "WEBP"}


class CardTemplate(NamedTuple):
    canvas_size: tuple[int, int]
    layers: list[dict[str, Any]]


class TemplateLayer(NamedTuple):
    # If absolute, source is a path / string, else it is an attribute
    name: str
    is_attribute: bool
    # Otherwise its a string
    is_image: bool
    source: list[str] | str
    anchor: tuple[int | str, int | str]
    size: tuple[int, int] = (0, 0)

    # Template string with $data to-be-replaced by the data
    text_template: str | None = None
    text_wrap: int = 0
    text_font_size: int = 11
    text_font: str = "arial.ttf"
    text_line_height: int = 80
    text_fill: list[int] = [255, 255, 255, 255]
    text_stroke_fill: list[int] = [0, 0, 0, 255]
    text_stroke_width: int = 2
    text_anchor: str = "la"


class LayerInfo(NamedTuple):
    finished_coords: tuple[int, int]


def get_attribute_recursive(object: Any, attribute: str) -> Any:
    data = object
    for subattr in attribute.split("."):
        data = getattr(data, subattr, None)
        if data is None:
            return None
    return data


def draw_layer(
    image: Image.Image,
    layer: TemplateLayer,
    ball_instance: BallInstance,
    media_path: str,
    prior_layer_info: dict[str, LayerInfo],
):
    name = layer.name
    if isinstance(layer.anchor[0], int):
        startx = layer.anchor[0]
    else:
        startx = prior_layer_info[layer.anchor[0]].finished_coords[0]

    if isinstance(layer.anchor[1], int):
        starty = layer.anchor[1]
    else:
        starty = prior_layer_info[layer.anchor[1]].finished_coords[1]

    start_coords = (startx, starty)
    end_coords = (startx + layer.size[0], starty + layer.size[1])
    draw = ImageDraw.Draw(image)

    data: str | None = None
    if layer.is_attribute:
        if isinstance(layer.source, list):
            for attribute in layer.source:
                data = get_attribute_recursive(ball_instance, attribute)
                if data is None:
                    continue
                else:
                    break
        else:
            data = get_attribute_recursive(ball_instance, layer.source)
    else:
        if isinstance(layer.source, list):
            data = layer.source[0]
        else:
            data = layer.source

    if not data:
        return
    else:
        data = str(data)

    if layer.is_image:
        if layer.is_attribute:
            path = Path(media_path + data)
        else:
            path = Path(data)

        layer_image = Image.open(path).convert("RGBA")
        layer_image = ImageOps.fit(layer_image, layer.size)
        image.paste(layer_image, start_coords, mask=layer_image)

        prior_layer_info[name] = LayerInfo(finished_coords=end_coords)
    else:
        final_str: str = (
            layer.text_template.replace("$data", data) if layer.text_template else data
        )

        final_strs: list[str]
        if layer.text_wrap:
            final_strs = textwrap.wrap(final_str, width=layer.text_wrap, expand_tabs=True)
        else:
            final_strs = [final_str]

        font = ImageFont.truetype(str(SOURCES_PATH / layer.text_font), layer.text_font_size)
        for i, line in enumerate(final_strs):
            draw.text(
                (start_coords[0], start_coords[1] + i * layer.text_line_height),
                line,
                font=font,
                fill=tuple(layer.text_fill),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 255),
                anchor=layer.text_anchor,
            )

        prior_layer_info[name] = LayerInfo(
            finished_coords=(
                start_coords[0],
                start_coords[1] + layer.text_line_height * len(final_strs) + 1,
            )
        )
