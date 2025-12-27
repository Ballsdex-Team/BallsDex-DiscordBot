import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat

if TYPE_CHECKING:
    from ballsdex.core.models import BallInstance


SOURCES_PATH = Path(os.path.dirname(os.path.abspath(__file__)), "./src")
WIDTH = 1500
HEIGHT = 2000

RECTANGLE_WIDTH = WIDTH - 40
RECTANGLE_HEIGHT = (HEIGHT // 5) * 2

CORNERS = ((34, 261), (1393, 992))
artwork_size = [b - a for a, b in zip(*CORNERS)]

title_font = ImageFont.truetype(str(SOURCES_PATH / "ArsenicaTrial-Extrabold.ttf"), 170)
capacity_name_font = ImageFont.truetype(str(SOURCES_PATH / "Bobby Jones Soft.otf"), 110)
capacity_description_font = ImageFont.truetype(str(SOURCES_PATH / "OpenSans-Semibold.ttf"), 75)
stats_font = ImageFont.truetype(str(SOURCES_PATH / "Bobby Jones Soft.otf"), 130)
credits_font = ImageFont.truetype(str(SOURCES_PATH / "arial.ttf"), 40)

credits_color_cache = {}


def get_credit_color(image: Image.Image, region: tuple) -> tuple:
    image = image.crop(region)
    brightness = ImageStat.Stat(image.convert("L")).mean[0]
    return (0, 0, 0, 255) if brightness > 100 else (255, 255, 255, 255)


def draw_card(ball_instance: "BallInstance", media_path: str = "./admin_panel/media/"):
    ball = ball_instance.countryball
    ball_health = (237, 115, 101, 255)
    ball_credits = ball.credits
    card_name = ball.cached_regime.name
    project_root = Path(__file__).resolve().parents[3]

    def resolve_path(p: str) -> Path:
        # Paths coming from DB can be either media-relative or repo-absolute like 
        # "/ballsdex/core/image_generator/src/shiny.png". Map absolute-like paths
        # to the project root, otherwise resolve under the media directory.
        if p.startswith("/"):
            return project_root / p.lstrip("/")
        return Path(media_path) / p
    if special_image := ball_instance.special_card:
        card_name = getattr(ball_instance.specialcard, "name", card_name)
        try:
            image = Image.open(resolve_path(special_image))
        except FileNotFoundError:
            # Use the ball's collection card first for specials, then fallback
            try:
                image = Image.open(resolve_path(ball.collection_card))
            except FileNotFoundError:
                try:
                    image = Image.open(resolve_path(ball.cached_regime.background))
                except FileNotFoundError:
                    image = Image.new("RGBA", (WIDTH, HEIGHT), (64, 64, 64, 255))
        if ball_instance.specialcard and ball_instance.specialcard.credits:
            ball_credits += f" • {ball_instance.specialcard.credits}"
    else:
        try:
            image = Image.open(resolve_path(ball.cached_regime.background))
        except FileNotFoundError:
            image = Image.new("RGBA", (WIDTH, HEIGHT), (64, 64, 64, 255))
    image = image.convert("RGBA")
    if ball.cached_economy:
        try:
            icon = Image.open(resolve_path(ball.cached_economy.icon)).convert("RGBA")
        except FileNotFoundError:
            icon = None
    else:
        icon = None

    draw = ImageDraw.Draw(image)
    draw.text(
        (50, 20),
        ball.short_name or ball.country,
        font=title_font,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255),
    )
    for i, line in enumerate(textwrap.wrap(f"Ability: {ball.capacity_name}", width=26)):
        draw.text(
            (100, 1050 + 100 * i),
            line,
            font=capacity_name_font,
            fill=(230, 230, 230, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 255),
        )
    for i, line in enumerate(textwrap.wrap(ball.capacity_description, width=32)):
        draw.text(
            (60, 1300 + 80 * i),
            line,
            font=capacity_description_font,
            stroke_width=1,
            stroke_fill=(0, 0, 0, 255),
        )
    draw.text(
        (320, 1670),
        str(ball_instance.health),
        font=stats_font,
        fill=ball_health,
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
    )
    draw.text(
        (1120, 1670),
        str(ball_instance.attack),
        font=stats_font,
        fill=(252, 194, 76, 255),
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
        anchor="ra",
    )
    if card_name in credits_color_cache:
        credits_color = credits_color_cache[card_name]
    else:
        credits_color = get_credit_color(
            image, (0, int(image.height * 0.8), image.width, image.height)
        )
        credits_color_cache[card_name] = credits_color
    draw.text(
        (30, 1870),
        # Modifying the line below is breaking the licence as you are removing credits
        # If you don't want to receive a DMCA, just don't
        "Created by El Laggron\n" f"Artwork author: {ball_credits}",
        font=credits_font,
        fill=credits_color,
        stroke_width=0,
        stroke_fill=(255, 255, 255, 255),
    )

    try:
        artwork = Image.open(resolve_path(ball.collection_card)).convert("RGBA")
        image.paste(ImageOps.fit(artwork, artwork_size), CORNERS[0])  # type: ignore
    except FileNotFoundError:
        artwork = None

    if icon:
        icon = ImageOps.fit(icon, (192, 192))
        image.paste(icon, (1200, 30), mask=icon)
        icon.close()
    if artwork:
        artwork.close()

    return image
