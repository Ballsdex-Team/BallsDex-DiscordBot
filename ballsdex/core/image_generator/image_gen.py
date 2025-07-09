import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

if TYPE_CHECKING:
    from ballsdex.core.models import BallInstance


SOURCES_PATH = Path(os.path.dirname(os.path.abspath(__file__)), "./src")
WIDTH = 1500
HEIGHT = 2000

RECTANGLE_WIDTH = WIDTH - 40
RECTANGLE_HEIGHT = (HEIGHT // 5) * 2

CORNERS = ((34, 261), (1393, 992))
artwork_size = [b - a for a, b in zip(*CORNERS)]

TEMPLATE = {
    "card_art": {
        "is_attribute": True,
        "is_image": True,
        "source": "collection_card",
        "top_left": (34, 261),
        "size": (1359, 731),
    }
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
    source: str
    top_left: tuple[int | str, int | str]
    size: tuple[int, int]
    # Template string with $data to-be-replaced by the data
    text_template: Optional[str]
    text_wrap: int = 80
    text_font_size: int = 11
    text_font: str = "arial.ttf"
    text_line_height: int = 80
    text_fill: tuple[int, int, int, int] = (255, 255, 255, 255)
    text_stroke_fill: tuple[int, int, int, int] = (0, 0, 0, 255)
    text_stroke_width: int = 2
    text_anchor: str = "ra"


class LayerInfo(NamedTuple):
    finished_coords: tuple[int, int]


def get_attribute_recursive(object: Any, attribute: str) -> Any:
    data = object
    for subattr in attribute.split("."):
        data = getattr(data, subattr)
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

    if layer.is_attribute:
        data = get_attribute_recursive(ball, layer.source)
    else:
        data = layer.source

    if layer.is_image:
        if layer.is_attribute:
            path = Path(media_path + data)
        else:
            path = Path(data)

        layer_image = Image.open(path)
        layer_image = ImageOps.fit(layer_image, layer.size)
        image.paste(layer_image, start_coords, mask=layer_image)

        prior_layer_info[name] = LayerInfo(
            finished_coords=(
                start_coords[0] + layer.size[0],
                start_coords[1] + layer.size[1],
            )
        )
    else:
        final_str = layer.text_template.replace("$data", data) if layer.text_template else data

        if layer.text_wrap:
            final_strs = textwrap.wrap(final_str, width=layer.text_wrap)
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
            finished_coords=(start_coords[0], start_coords[1] + i * len(final_strs))
        )


def draw_card(
    ball_instance: "BallInstance",
    # template: dict[str, dict[str, Any]],
    media_path: str = "./admin_panel/media/",
) -> tuple[Image.Image, dict[str, Any]]:
    ball = ball_instance.countryball
    image = Image.new("RGB", (HEIGHT, WIDTH))
    prior_layer_info = {}

    template = TEMPLATE

    layers = ((name, TemplateLayer(**x)) for (name, x) in template.items())
    for name, layer in layers:
        draw_layer(image, layer, ball, media_path, prior_layer_info, name)

    return image, {"format": "WEBP"}
