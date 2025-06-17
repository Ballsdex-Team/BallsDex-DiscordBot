import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

title_font = ImageFont.truetype(str(SOURCES_PATH / "LilitaOne-Regular.ttf"), 170)
capacity_name_font = ImageFont.truetype(str(SOURCES_PATH / "LilitaOne-Regular.ttf"), 110)
capacity_description_font = ImageFont.truetype(str(SOURCES_PATH / "LilitaOne-Regular.ttf"), 75)
stats_font = ImageFont.truetype(str(SOURCES_PATH / "LilitaOne-Regular.ttf"), 130)
credits_font = ImageFont.truetype(str(SOURCES_PATH / "arial.ttf"), 40)

credits_color_cache = {}


def get_credit_color(image: Image.Image, region: tuple) -> tuple:
    image = image.crop(region)
    brightness = sum(image.convert("L").getdata()) / image.width / image.height  # type: ignore
    return (255, 255, 255, 255) if brightness > 100 else (255, 255, 255, 255)


def draw_card(
    ball_instance: "BallInstance",
    media_path: str = "./admin_panel/media/",
) -> tuple[Image.Image, dict[str, Any]]:
    ball = ball_instance.countryball
    ball_health = (86, 255, 100, 255)
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

    name_text = ball.short_name or ball.country
    left_margin = 50
    right_limit = 1200 - 40
    max_text_width = right_limit - left_margin
    max_text_height = 160
    center_x = (left_margin + right_limit) // 2
    top_y = 20
    shadow_offset = 5

    base_font_size = 100
    temp_draw = ImageDraw.Draw(image)

# Load base font
    font = ImageFont.truetype(str(SOURCES_PATH / "LilitaOne-Regular.ttf"), base_font_size)

# Measure unscaled text
    bbox = temp_draw.textbbox((0, 0), name_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

# Compute stretch factors
    scale_x = min(1.0, max_text_width / text_width)
    scale_y = min(1.0, max_text_height / text_height)

# New image size
    new_width = int(text_width * scale_x)
    new_height = int(text_height * scale_y)

# ========== SHADOW ==========
    shadow_img = Image.new("RGBA", (text_width, text_height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_img)
    shadow_draw.text((-bbox[0], -bbox[1]), name_text, font=font,
                     fill="black", stroke_width=8, stroke_fill=(0, 0, 0, 255))

    shadow_img = shadow_img.resize((new_width, new_height), resample=Image.BICUBIC)
    x_shadow = center_x - new_width // 2 + shadow_offset
    y_shadow = top_y + (max_text_height - new_height) // 2 + shadow_offset
    image.paste(shadow_img, (x_shadow, y_shadow), shadow_img)

# ========== TEXT ==========
    text_img = Image.new("RGBA", (text_width, text_height), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_img)
    text_draw.text((-bbox[0], -bbox[1]), name_text, font=font,
                   fill=(255, 255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0, 255))

    text_img = text_img.resize((new_width, new_height), resample=Image.BICUBIC)
    x_text = center_x - new_width // 2
    y_text = top_y + (max_text_height - new_height) // 2
    image.paste(text_img, (x_text, y_text), text_img)




    cap_name = textwrap.wrap(f"{ball.capacity_name}", width=26)

    for i, line in enumerate(cap_name):
        draw.text(
            (100, 1025 + 100 * i + shadow_offset),
            line,
            font=capacity_name_font,
            fill=shadow_color,
            stroke_width=5,
            stroke_fill=(0, 0, 0, 255),
        )
        draw.text(
            (100, 1025 + 100 * i),
            line,
            font=capacity_name_font,
            fill=(255, 255, 255, 255),
            stroke_width=5,
            stroke_fill=(0, 0, 0, 255),
        )
    for i, line in enumerate(textwrap.wrap(ball.capacity_description, width=40)):
        draw.text(
            (60, 1160 + 80 * i + shadow_offset),
            line,
            font=capacity_description_font,
            fill=shadow_color,
            stroke_width=5,
            stroke_fill=(0, 0, 0, 255),
        )
        draw.text(
            (60, 1160 + 80 * i),
            line,
            font=capacity_description_font,
            stroke_width=5,
            stroke_fill=(0, 0, 0, 255),
        )

    draw.text(
        (320, 1670 + shadow_offset),
        str(ball_instance.health),
        font=stats_font,
        fill=shadow_color,
        stroke_width=5,
        stroke_fill=(0, 0, 0, 255),
    )
    draw.text(
        (320, 1670),
        str(ball_instance.health),
        font=stats_font,
        fill=ball_health,
        stroke_width=5,
        stroke_fill=(0, 0, 0, 255),
    )
    draw.text(
        (1120, 1670 + shadow_offset),
        str(ball_instance.attack),
        font=stats_font,
        fill=shadow_color,
        stroke_width=5,
        stroke_fill=(0, 0, 0, 255),
        anchor="ra",
    )
    draw.text(
        (1120, 1670),
        str(ball_instance.attack),
        font=stats_font,
        fill=(255, 66, 92, 255),
        stroke_width=5,
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
        f"Ballsdex by El Laggron, BrawlDex by AngerRandom, Brawl Stars by Supercell\n" f"{ball_credits}",
        font=credits_font,
        fill=credits_color,
        stroke_width=3,
        stroke_fill=(0, 0, 0, 255),
    )

    artwork = Image.open(media_path + ball.collection_card).convert("RGBA")
    image.paste(ImageOps.fit(artwork, artwork_size), CORNERS[0])  # type: ignore

    if icon:
        icon = ImageOps.fit(icon, (192, 192))
        image.paste(icon, (1200, 30), mask=icon)
        icon.close()
    artwork.close()

    return image, {"format": "WEBP"}
