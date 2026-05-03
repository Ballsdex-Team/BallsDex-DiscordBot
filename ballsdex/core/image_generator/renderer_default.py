import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from settings.models import settings

if TYPE_CHECKING:
    from bd_models.models import BallInstance

SOURCES_PATH = Path(os.path.dirname(os.path.abspath(__file__)), "./src")

COLLECTION_CARD_CORNERS = ((34, 261), (1393, 992))
BALL_HEALTH = (237, 115, 101, 255)
artwork_size = [b - a for a, b in zip(*COLLECTION_CARD_CORNERS)]

# ===== TIP =====
#
# If you want to quickly test the image generation, there is a CLI tool to quickly generate
# test images locally, without the bot or the admin panel running:
#
# With Docker: "docker compose run admin-panel django-admin preview > image.png"
# Without: "DJANGO_SETTINGS_MODULE=admin_panel.settings python3 -m django preview"
#
# This will either create a file named "image.png" or directly display it using your system's
# image viewer. There are options available to specify the ball or the special background,
# use the "--help" flag to view all options.

title_font = ImageFont.truetype(str(SOURCES_PATH / "ArsenicaTrial-Extrabold.ttf"), 170)
capacity_name_font = ImageFont.truetype(str(SOURCES_PATH / "Bobby Jones Soft.otf"), 110)
capacity_description_font = ImageFont.truetype(str(SOURCES_PATH / "OpenSans-Semibold.ttf"), 75)
stats_font = ImageFont.truetype(str(SOURCES_PATH / "Bobby Jones Soft.otf"), 130)
credits_font = ImageFont.truetype(str(SOURCES_PATH / "arial.ttf"), 40)

credits_color_cache = {}


def get_credit_color(image: Image.Image, region: tuple) -> tuple:
    image = image.crop(region)
    brightness = sum(image.convert("L").getdata()) / image.width / image.height  # type: ignore
    return (0, 0, 0, 255) if brightness > 100 else (255, 255, 255, 255)


def draw_card_blackscreen(ball_instance: "BallInstance") -> tuple[Image.Image, dict[str, Any]]:
    image = Image.new(mode="RGB", size=(200, 200))
    return image, {"format": "webp"}


def draw_card_fullart(ball_instance: "BallInstance") -> tuple[Image.Image, dict[str, Any]]:
    ball = ball_instance.countryball
    if ball_instance.cached_variant:
        collection_card = ball_instance.cached_variant.collection_card
    else:
        collection_card = ball.collection_card

    image = Image.open(collection_card).convert("RGBA")
    cache_key = ball_instance.cached_variant.name if ball_instance.cached_variant else ball.country
    return put_card_info(ball_instance, image, cache_key)


def draw_card_default(ball_instance: "BallInstance") -> tuple[Image.Image, dict[str, Any]]:
    ball = ball_instance.countryball
    cache_key = ball.cached_regime.name

    if special_image := ball_instance.special_card:
        image = Image.open(special_image)
        cache_key = getattr(ball_instance.specialcard, "name", cache_key)
    else:
        image = Image.open(ball.cached_regime.background)

    image = image.convert("RGBA")

    if ball_instance.cached_variant:
        collection_card = ball_instance.cached_variant.collection_card
    else:
        collection_card = ball.collection_card

    artwork = Image.open(collection_card).convert("RGBA")
    image.paste(ImageOps.fit(artwork, artwork_size), COLLECTION_CARD_CORNERS[0])  # pyright: ignore[reportArgumentType]
    artwork.close()

    return put_card_info(ball_instance, image, cache_key)


def put_card_info(
    ball_instance: "BallInstance", image: Image.Image, cache_key: str
) -> tuple[Image.Image, dict[str, Any]]:
    ball = ball_instance.countryball

    ball_credits = ball.credits

    special_credits = ""
    if ball_instance.specialcard:
        special_credits += f" • Special Author: {ball_instance.specialcard.credits}"

    economy_icon = Image.open(ball.cached_economy.icon).convert("RGBA") if ball.cached_economy else None

    draw = ImageDraw.Draw(image)
    draw.text((50, 20), ball.short_name or ball.country, font=title_font, stroke_width=2, stroke_fill=(0, 0, 0, 255))

    cap_name = textwrap.wrap(f"Ability: {ball.capacity_name}", width=26)

    for i, line in enumerate(cap_name):
        draw.text(
            (100, 1050 + 100 * i),
            line,
            font=capacity_name_font,
            fill=(230, 230, 230, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 255),
        )

    capacity_description_lines = (
        wrapped_line
        for newline in ball.capacity_description.splitlines()
        for wrapped_line in textwrap.wrap(newline, 32)
    )

    for i, line in enumerate(capacity_description_lines):
        draw.text(
            (60, 1100 + 100 * len(cap_name) + 80 * i),
            line,
            font=capacity_description_font,
            stroke_width=1,
            stroke_fill=(0, 0, 0, 255),
        )

    draw.text(
        (320, 1670),
        str(ball_instance.health),
        font=stats_font,
        fill=BALL_HEALTH,
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
    if settings.show_rarity:
        draw.text((1200, 50), str(ball.rarity), font=stats_font, stroke_width=2, stroke_fill=(0, 0, 0, 255))
    if cache_key in credits_color_cache:
        credits_color = credits_color_cache[cache_key]
    else:
        credits_color = get_credit_color(image, (0, int(image.height * 0.8), image.width, image.height))
        credits_color_cache[cache_key] = credits_color
    draw.text(
        (30, 1870),
        # Modifying the line below is breaking the licence as you are removing credits
        # If you don't want to receive a DMCA, just don't
        f"Created by El Laggron{special_credits}\nArtwork author: {ball_credits}",
        font=credits_font,
        fill=credits_color,
        stroke_width=0,
        stroke_fill=(255, 255, 255, 255),
    )

    if economy_icon:
        economy_icon = ImageOps.fit(economy_icon, (192, 192))
        image.paste(economy_icon, (1200, 30), mask=economy_icon)
        economy_icon.close()

    return image, {"format": "WEBP"}
