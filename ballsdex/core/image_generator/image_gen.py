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
artwork_width = CORNERS[1][0] - CORNERS[0][0]
artwork_height = CORNERS[1][1] - CORNERS[0][1]
artwork_size: tuple[int, int] = (artwork_width, artwork_height)

# Fonts
title_font = ImageFont.truetype(str(SOURCES_PATH / "ArsenicaTrial-Extrabold.ttf"), 160)
capacity_name_font_path = str(SOURCES_PATH / "Bobby Jones Soft.otf")
capacity_name_font = ImageFont.truetype(capacity_name_font_path, 110)
capacity_description_font = ImageFont.truetype(str(SOURCES_PATH / "OpenSans-Semibold.ttf"), 70)
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
    ball_health_color = (237, 115, 101, 255)
    card_name = ball.cached_regime.name
    
    # Initialize background
    if special_image := ball_instance.special_card:
        card_name = getattr(ball_instance, "specialcard", card_name)
        image = Image.open(media_path + special_image)
    else:
        image = Image.open(media_path + ball.cached_regime.background)
        
    image = image.convert("RGBA")
    draw = ImageDraw.Draw(image)

    # --- STEP 1: MAIN ARTWORK ---
    artwork = Image.open(media_path + ball.collection_card).convert("RGBA")
    image.paste(ImageOps.fit(artwork, artwork_size), CORNERS[0])
    artwork.close()

    # --- STEP 2: TEXT & ICONS ---

    # 1. NAME (Top Left)
    draw.text(
        (50, 20),
        ball.short_name or ball.country,
        font=title_font,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255),
    )

    # 2. RARITY (Top Right Aligned)
    draw.text(
        (WIDTH - 100, 20),
        str(ball.rarity),
        font=title_font,
        anchor="ra",
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255),
    )

    # 3. ECONOMY LOGO
    if ball.cached_economy:
        icon = Image.open(media_path + ball.cached_economy.icon).convert("RGBA")
        icon.thumbnail((192, 192), Image.Resampling.LANCZOS)
        image.paste(icon, (WIDTH - icon.width - 60, 1050), mask=icon)
        icon.close()

    # 4. HEALTH & 5. ATTACK
    attack_str = str(ball_instance.attack)
    health_str = str(ball_instance.health)

    draw.text(
        (WIDTH - 180, 1820), 
        attack_str,
        font=stats_font,
        fill=(252, 194, 76, 255),
        anchor="ra",
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255)
    )

    draw.text(
        (WIDTH - 500, 1820),
        health_str,
        font=stats_font,
        fill=ball_health_color,
        anchor="ra",
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
    )

    # --- DYNAMIC CODENAME SCALING ---
    full_cap_text = f"Codename: {ball.capacity_name}"
    max_cap_width = WIDTH - 350  # Leave space for the economy icon
    current_cap_font = capacity_name_font
    current_size = 110

    # Shrink font size until it fits on one line
    while current_cap_font.getlength(full_cap_text) > max_cap_width and current_size > 40:
        current_size -= 2
        current_cap_font = ImageFont.truetype(capacity_name_font_path, current_size)

    draw.text(
        (60, 1050),
        full_cap_text,
        font=current_cap_font,
        fill=(230, 230, 230, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255),
    )

    # --- CAPACITY DESCRIPTION ---
    capacity_description_lines = (
        wrapped_line
        for newline in ball.capacity_description.splitlines()
        for wrapped_line in textwrap.wrap(newline, 32)
    )
    
    # We use a fixed start for description so it doesn't jump around
    desc_y_start = 1180 
    for i, line in enumerate(capacity_description_lines):
        draw.text(
            (60, desc_y_start + 85 * i),
            line,
            font=capacity_description_font,
            stroke_width=1,
            stroke_fill=(0, 0, 0, 255),
        )

    # Credits (Bottom Left)
    if card_name in credits_color_cache:
        credits_color = credits_color_cache[card_name]
    else:
        credits_color = get_credit_color(
            image, (0, int(image.height * 0.8), image.width, image.height)
        )
        credits_color_cache[card_name] = credits_color

    draw.text(
        (30, 1870),
        f"Created by El Laggron\nOwners: Kingraph & I'm TS",
        font=credits_font,
        fill=credits_color,
        stroke_width=0,
        stroke_fill=(255, 255, 255, 255),
    )

    return image, {"format": "WEBP"}