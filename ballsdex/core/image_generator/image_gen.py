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
    def get_font(layer: TemplateLayer) -> FreeTypeFont:
        if layer.text_font in font_cache:
            font = font_cache[layer.text_font]
        else:
            font = ImageFont.truetype(str(SOURCES_PATH / layer.text_font), layer.text_font_size)
            font_cache[layer.text_font] = font

        return font

    def get_text_fill_color(
        layer: TemplateLayer, ball_instance: BallInstance, region: tuple[int, int, int, int]
    ) -> tuple[int, int, int, int]:
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
                text_fill = get_region_best_color(image, region)
        if not text_fill:
            if isinstance(layer.text_fill, str):
                text_fill = (255, 255, 255, 255)
            else:
                text_fill = tuple(layer.text_fill)  # pyright: ignore[reportAssignmentType]

        return text_fill  # pyright: ignore[reportReturnType]

    def get_text_strings(layer: TemplateLayer, data) -> list[str]:
        final_str: str = (
            layer.text_template.replace("$data", data) if layer.text_template else data
        )

        final_strs: list[str]
        if layer.text_wrap:
            final_strs = textwrap.wrap(final_str, width=layer.text_wrap, expand_tabs=True)
        else:
            final_strs = [final_str]

        return final_strs

    def get_anchor_coords(layer, prior_layer_info) -> tuple[int, int]:
        if isinstance(layer.anchor[0], int):
            startx = layer.anchor[0]
        else:
            # Essentially putting in a string means, start this layer
            # where that other layer finished
            startx = prior_layer_info[layer.anchor[0]].finished_coords[0]

        if isinstance(layer.anchor[1], int):
            starty = layer.anchor[1]
        else:
            starty = prior_layer_info[layer.anchor[1]].finished_coords[1]

        return (startx, starty)

    def get_layer_data(layer: TemplateLayer, ball_instance: BallInstance) -> str | None:
        data: str | None = None

        if not layer.is_attribute:
            if isinstance(layer.source, list):
                data = layer.source[0]
            else:
                data = layer.source

            return str(data)

        if isinstance(layer.source, list):
            # for prioritised source lists, eg special > regime background
            for attribute in layer.source:
                data = get_attribute_recursive(ball_instance, attribute)
                if data:
                    break
        else:
            data = get_attribute_recursive(ball_instance, layer.source)

        if data:
            data = str(data)

        return data

    name = layer.name
    start_coords = get_anchor_coords(layer, prior_layer_info)

    data = get_layer_data(layer, ball_instance)
    if not data:
        return

    if layer.is_image:
        end_coords = (start_coords[0] + layer.size[0], start_coords[1] + layer.size[1])

        path = Path(media_path + data)

        layer_image = Image.open(path).convert("RGBA")
        layer_image = ImageOps.fit(layer_image, layer.size)
        image.paste(layer_image, start_coords, mask=layer_image)
    else:
        draw = ImageDraw.Draw(image)

        font = get_font(layer)
        final_strs = get_text_strings(layer, data)

        text_width = max(draw.textlength(text=string, font=font) for string in final_strs)
        end_coords = (
            int(start_coords[0] + text_width),
            start_coords[1] + layer.text_line_height * (len(final_strs)),
        )
        text_fill = get_text_fill_color(layer, ball_instance, (*start_coords, *end_coords))

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

    prior_layer_info[name] = LayerInfo(finished_coords=end_coords)
