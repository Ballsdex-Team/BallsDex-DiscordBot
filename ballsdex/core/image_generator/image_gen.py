import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.models import BallInstance


SOURCES_PATH = Path(os.path.dirname(os.path.abspath(__file__)), "./src")
WIDTH = 1500
HEIGHT = 2000

RECTANGLE_WIDTH = WIDTH - 40
RECTANGLE_HEIGHT = (HEIGHT // 5) * 2

CORNERS = ((34, 261), (1393, 992))
artwork_size = [b - a for a, b in zip(*CORNERS)]

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

credits_color_cache = {}


def get_credit_color(image: Image.Image, region: tuple) -> tuple:
    image = image.crop(region)
    brightness = sum(image.convert("L").getdata()) / image.width / image.height  # type: ignore
    return (0, 0, 0, 255) if brightness > 100 else (255, 255, 255, 255)


def draw_card(
    ball_instance: "BallInstance",
    media_path: str = "./admin_panel/media/",
) -> tuple[Image.Image, dict[str, Any]]:
    ball = ball_instance.countryball
    ball_health = (237, 115, 101, 255)
    ball_credits = ball.credits
    special_credits = ""
    card_name = ball.cached_regime.name
    if special_image := ball_instance.special_card:
        card_name = getattr(ball_instance.specialcard, "name", card_name)
        image = Image.open(media_path + special_image)
        if ball_instance.specialcard and ball_instance.specialcard.credits:
            special_credits += f" • Special Author: {ball_instance.specialcard.credits}"
    else:
        image = Image.open(media_path + ball.cached_regime.background)
    image = image.convert("RGBA")
    icon = (
        Image.open(media_path + ball.cached_economy.icon).convert("RGBA")
        if ball.cached_economy
        else None
    )

    draw = ImageDraw.Draw(image)
    draw.text(
        (50, 20),
        ball.short_name or ball.country,
        font=title_font,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255),
    )

    # Draw FIFA stats section instead of ability
    fifa_stats_font = ImageFont.truetype(str(SOURCES_PATH / "Bobby Jones Soft.otf"), 80)
    stats_label_font = ImageFont.truetype(str(SOURCES_PATH / "OpenSans-Semibold.ttf"), 50)
    
    # Show rating prominently
    draw.text(
        (100, 1050),
        f"RATING: {ball.rating}",
        font=capacity_name_font,
        fill=(252, 194, 76, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255),
    )
    
    # FIFA stats in 2 rows of 3
    stats_data = [
        ("PAC", ball.pace, (100, 1180)),
        ("SHO", ball.shooting, (500, 1180)),
        ("PAS", ball.passing, (900, 1180)),
        ("DRI", ball.dribbling, (100, 1320)),
        ("DEF", ball.defending, (500, 1320)),
        ("PHY", ball.physical, (900, 1320)),
    ]
    
    for label, value, pos in stats_data:
        # Color based on stat value
        if value >= 85:
            color = (76, 217, 100, 255)  # Green for high
        elif value >= 70:
            color = (252, 194, 76, 255)  # Yellow for medium
        else:
            color = (237, 115, 101, 255)  # Red for low
        
        draw.text(
            pos,
            f"{label}: {value}",
            font=fifa_stats_font,
            fill=color,
            stroke_width=1,
            stroke_fill=(0, 0, 0, 255),
        )
    
    # Position and Club info
    if ball.position:
        draw.text(
            (100, 1480),
            f"Position: {ball.position}",
            font=stats_label_font,
            fill=(230, 230, 230, 255),
            stroke_width=1,
            stroke_fill=(0, 0, 0, 255),
        )
    if ball.club:
        draw.text(
            (600, 1480),
            f"Club: {ball.club}",
            font=stats_label_font,
            fill=(230, 230, 230, 255),
            stroke_width=1,
            stroke_fill=(0, 0, 0, 255),
        )
    if settings.show_rarity:
        draw.text(
            (1200, 50),
            str(ball.rarity),
            font=stats_font,
            stroke_width=2,
            stroke_fill=(0, 0, 0, 255),
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
        f"Created by El Laggron{special_credits}\n" f"Artwork author: {ball_credits}",
        font=credits_font,
        fill=credits_color,
        stroke_width=0,
        stroke_fill=(255, 255, 255, 255),
    )

    artwork = Image.open(media_path + ball.collection_card).convert("RGBA")
    image.paste(ImageOps.fit(artwork, artwork_size), CORNERS[0])  # type: ignore

    if icon:
        icon = ImageOps.fit(icon, (192, 192))
        image.paste(icon, (1200, 30), mask=icon)
        icon.close()
    artwork.close()

    return image, {"format": "WEBP"}
