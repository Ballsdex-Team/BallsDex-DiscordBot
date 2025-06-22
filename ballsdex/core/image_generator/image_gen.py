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

CORNERS = ((35, 261), (1395, 991))
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
redits_font = ImageFont.truetype(str(SOURCES_PATH / "arial.ttf"), 40)

credits_color_cache = {}

def get_credit_color(image: Image.Image, region: tuple) -> tuple:
    image = image.crop(region)
    brightness = sum(image.convert("L").getdata()) / image.width / image.height
    return (0, 0, 0, 255) if brightness > 100 else (255, 255, 255, 255)

def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    paragraphs = text.split('%%')
    lines = []
    for para in paragraphs:
        words = para.strip().split(' ')
        current_line = ''
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if draw.textlength(test_line, font=font) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
    return lines

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

    draw = ImageDraw.Draw(image)
    shadow_color = "black"
    shadow_offset = 3
    
    draw.text(
        (50, 20 + shadow_offset),
        ball.short_name or ball.country,
        font=title_font,
        fill=shadow_color,
        stroke_width=8,
        stroke_fill=(0, 0, 0, 255),
    )

    # Title
    draw.text(
        (50, 20),
        ball.short_name or ball.country,
        font=title_font,
        fill=(255, 255, 255, 255),
        stroke_width=8,
       stroke_fill=(0, 0, 0, 255),
    )

    # Capacity Name
    cap_name = textwrap.wrap(f"{ball.capacity_name}", width=26)
    for i, line in enumerate(cap_name):
        draw.text(
            (100, 1050 + 100 * i),
            line,
            font=capacity_name_font,
            fill=(255, 255, 255, 255),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 255),
        )

    # Capacity Description with custom line breaks (%%)
    max_text_width = 1320
    wrapped_description = wrap_text(ball.capacity_description, capacity_description_font, max_text_width, draw)
    for i, line in enumerate(wrapped_description):
        draw.text(
            (60, 1100 + 100 * len(cap_name) + 80 * i + shadow_offset),
            line,
            font=capacity_description_font,
            fill=shadow_color,
            stroke_width=5,
            stroke_fill=(0, 0, 0, 255),
        )

    # Rarity display
    if settings.show_rarity:
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

    # Artwork
    artwork = Image.open(media_path + ball.collection_card).convert("RGBA")
    image.paste(ImageOps.fit(artwork, artwork_size), CORNERS[0])

    # Icon
    if icon:
        icon = ImageOps.fit(icon, (192, 192))
        image.paste(icon, (1200, 30), mask=icon)
        icon.close()
    artwork.close()

    return image, {"format": "PNG"}