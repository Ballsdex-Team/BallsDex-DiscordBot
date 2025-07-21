from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ballsdex.core.image_generator.default_card_template import DEFAULT_CARD_TEMPLATE

if TYPE_CHECKING:
    from PIL.ImageFont import FreeTypeFont

    from ballsdex.core.models import BallInstance, Regime, Special

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

text_color_cache: dict[Regime | Special, dict["str", tuple[int, int, int, int]]] = {}
font_cache: dict[str, FreeTypeFont] = {}


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
    anchor: list[int | str]
    size: tuple[int, int] = (0, 0)

    # Template string with $data to-be-replaced by the data
    text_template: str | None = None
    text_wrap: int = 0
    text_font_size: int = 11
    text_font: str = "arial.ttf"
    text_line_height: int = 80
    text_fill: list[int] | str = [255, 255, 255, 255]
    text_stroke_fill: list[int] = [0, 0, 0, 255]
    text_stroke_width: int = 0
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


def get_region_best_color(image: Image.Image, region: tuple) -> tuple:
    image = image.crop(region)
    brightness = sum(image.convert("L").getdata()) / image.width / image.height  # type: ignore
    return (0, 0, 0, 255) if brightness > 100 else (255, 255, 255, 255)


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
        end_coords = (startx + layer.size[0], starty + layer.size[1])
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

        if layer.text_font in font_cache:
            font = font_cache[layer.text_font]
        else:
            font = ImageFont.truetype(str(SOURCES_PATH / layer.text_font), layer.text_font_size)
            font_cache[layer.text_font] = font

        text_width = max(draw.textlength(text=string, font=font) for string in final_strs)
        end_coords = (startx + text_width, starty + layer.text_font_size * len(final_strs))

        text_fill: tuple[int, int, int, int] | None = None
        if layer.text_fill == "auto":
            ball_bg_cache = (
                ball_instance.special
                if ball_instance.special
                else ball_instance.countryball.regime
            )
            if ball_bg_cache in text_color_cache:
                if layer.name in text_color_cache[ball_bg_cache]:
                    text_fill = text_color_cache[ball_bg_cache][layer.name]

            if not text_fill:
                text_fill = get_region_best_color(image, (*start_coords, *end_coords))
        if not text_fill:
            if isinstance(layer.text_fill, str):
                text_fill = (255, 255, 255, 255)
            else:
                text_fill = tuple(layer.text_fill)  # # pyright: ignore[reportAssignmentType]

        for i, line in enumerate(final_strs):
            draw.text(
                (start_coords[0], start_coords[1] + i * layer.text_line_height),
                line,
                font=font,
                fill=text_fill,
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
