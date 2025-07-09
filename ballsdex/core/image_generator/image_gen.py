import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

if TYPE_CHECKING:
    from ballsdex.core.models import BallInstance

SOURCES_PATH = Path(os.path.dirname(os.path.abspath(__file__)), "./src")
WIDTH = 1428
HEIGHT = 2000

CORNERS = ((34, 261), (1393, 992))
artwork_size = [b - a for a, b in zip(*CORNERS)]

TEMPLATE = {
    "background": {
        "is_attribute": True,
        "is_image": True,
        "source": ["specialcard", "cached_regime.background"],
        "top_left": (0, 0),
        "size": (WIDTH, HEIGHT),
    },
    "card_art": {
        "is_attribute": True,
        "is_image": True,
        "source": "collection_card",
        "top_left": (34, 261),
        "size": (1359, 731),
    },
    "title": {
        "is_attribute": True,
        "is_image": False,
        "source": ["short_name", "country"],
        "top_left": (50, 20),
        "text_font": "ArsenicaTrial-Extrabold.ttf",
        "text_font_size": 170,
        "text_stroke_width": 2,
        "text_stroke_fill": (0, 0, 0, 255),
    },
    "capacity_name": {
        "is_attribute": True,
        "is_image": False,
        "source": "capacity_name",
        "top_left": (100, 1050),
        "text_line_height": 100,
        "text_font": "Bobby Jones Soft.otf",
        "text_wrap": 26,
        "text_fill": (230, 230, 230, 255),
        "text_font_size": 110,
        "text_stroke_width": 2,
        "text_stroke_fill": (0, 0, 0, 255),
    },
    "capacity_description": {
        "is_attribute": True,
        "is_image": False,
        "source": "capacity_description",
        "top_left": (60, "capacity_name"),
        "text_line_height": 100,
        "text_font": "OpenSans-Semibold.ttf",
        "text_wrap": 32,
        "text_fill": (255, 255, 255, 255),
        "text_font_size": 75,
        "text_stroke_width": 1,
        "text_stroke_fill": (0, 0, 0, 255),
    },
    "health": {
        "is_attribute": True,
        "is_image": False,
        "source": "health",
        "top_left": (320, 1670),
        "text_line_height": 100,
        "text_font": "Bobby Jones Soft.otf",
        "text_wrap": 32,
        "text_fill": (237, 115, 101, 255),
        "text_font_size": 130,
        "text_stroke_width": 1,
        "text_stroke_fill": (0, 0, 0, 255),
    },
    "attack": {
        "is_attribute": True,
        "is_image": False,
        "source": "attack",
        "top_left": (1120, 1670),
        "text_line_height": 100,
        "text_font": "Bobby Jones Soft.otf",
        "text_wrap": 32,
        "text_fill": (252, 194, 76, 255),
        "text_anchor": "ra",
        "text_font_size": 130,
        "text_stroke_width": 1,
        "text_stroke_fill": (0, 0, 0, 255),
    },
    "lagg_credits": {
        "is_attribute": False,
        "is_image": False,
        "source": "Created by El Lagronn",
        "top_left": (30, 1870),
        "text_font": "arial.ttf",
        "text_line_height": 43,
        "text_fill": (255, 255, 255, 255),
        "text_font_size": 40,
        "text_stroke_width": 0,
    },
    "credits": {
        "is_attribute": True,
        "is_image": False,
        "source": "credits",
        "top_left": (30, "lagg_credits"),
        "text_font": "arial.ttf",
        "text_fill": (255, 255, 255, 255),
        "text_font_size": 40,
        "text_template": "Artwork author: $data",
        "text_stroke_width": 0,
    },
}

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

title_font = ImageFont.truetype(str(SOURCES_PATH / "ArsenicaTrial-Extrabold.ttf"), 170)
capacity_name_font = ImageFont.truetype(str(SOURCES_PATH / "Bobby Jones Soft.otf"), 110)
capacity_description_font = ImageFont.truetype(str(SOURCES_PATH / "OpenSans-Semibold.ttf"), 75)
stats_font = ImageFont.truetype(str(SOURCES_PATH / "Bobby Jones Soft.otf"), 130)
credits_font = ImageFont.truetype(str(SOURCES_PATH / "arial.ttf"), 40)


class TemplateLayer(NamedTuple):
    # If absolute, source is a path / string, else it is an attribute
    is_attribute: bool
    # Otherwise its a string
    is_image: bool
    source: list[str] | str
    top_left: tuple[int | str, int | str]
    size: tuple[int, int] = (0, 0)

    # Template string with $data to-be-replaced by the data
    text_template: str | None = None
    text_wrap: int = 0
    text_font_size: int = 11
    text_font: str = "arial.ttf"
    text_line_height: int = 80
    text_fill: tuple[int, int, int, int] = (255, 255, 255, 255)
    text_stroke_fill: tuple[int, int, int, int] = (0, 0, 0, 255)
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
    ball,
    media_path: str,
    prior_layer_info: dict[str, LayerInfo],
    name: str,
):
    if isinstance(layer.top_left[0], int):
        startx = layer.top_left[0]
    else:
        startx = prior_layer_info[layer.top_left[0]].finished_coords[0]

    if isinstance(layer.top_left[1], int):
        starty = layer.top_left[1]
    else:
        starty = prior_layer_info[layer.top_left[1]].finished_coords[1]

    start_coords = (startx, starty)
    draw = ImageDraw.Draw(image)

    data: str | None
    if layer.is_attribute:
        if isinstance(layer.source, list):
            for attribute in layer.source:
                data = get_attribute_recursive(ball, attribute)
                if data is None:
                    continue
                else:
                    break
        else:
            data = get_attribute_recursive(ball, layer.source)
    else:
        if isinstance(layer.source, list):
            data = layer.source[0]
        else:
            data = layer.source

    if "data" not in vars():
        return
    elif not data:  # type: ignore
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

        prior_layer_info[name] = LayerInfo(
            finished_coords=(
                start_coords[0] + layer.size[0],
                start_coords[1] + layer.size[1],
            )
        )
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
                fill=layer.text_fill,
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


def draw_card(
    ball_instance: "BallInstance",
    # template: dict[str, dict[str, Any]],
    media_path: str = "./admin_panel/media/",
) -> tuple[Image.Image, dict[str, Any]]:
    ball = ball_instance.countryball
    image = Image.new("RGB", (WIDTH, HEIGHT))
    prior_layer_info = {}

    template = TEMPLATE

    layers = ((name, TemplateLayer(**x)) for (name, x) in template.items())
    for name, layer in layers:
        draw_layer(image, layer, ball, media_path, prior_layer_info, name)

    return image, {"format": "WEBP"}
