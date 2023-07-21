import os
from pathlib import Path
import textwrap
from PIL import Image, ImageFont, ImageDraw, ImageOps
from typing import TYPE_CHECKING
from ballsdex.core.models import Economy, StatBG, BallInstance

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


def draw_card(ball_instance: "BallInstance"):
    ball = ball_instance.countryball
    ball_health = (237, 115, 101, 255)

    if ball_instance.shiny:
        image = Image.open(str(SOURCES_PATH / "shiny.png"))
        ball_health = (255, 255, 255, 255)
    elif special_image := ball_instance.special_card:
        image = Image.open("." + special_image)
    elif ball_instance.statbg == StatBG.PERFECT:
        image = Image.open(str(SOURCES_PATH / "BG1.png"))
    elif ball_instance.statbg == StatBG.UNPERFECT:
        image = Image.open(str(SOURCES_PATH / "BG2.png"))
    elif ball_instance.statbg == StatBG.ZEROS:
        image = Image.open(str(SOURCES_PATH / "BG12.png"))
    elif ball_instance.statbg == StatBG.TWINS:
        image = Image.open(str(SOURCES_PATH / "BG3.png"))
    elif ball_instance.statbg == StatBG.VERYVERYLOW:
        image = Image.open(str(SOURCES_PATH / "BG4.png"))
    elif ball_instance.statbg == StatBG.VERYLOW:
        image = Image.open(str(SOURCES_PATH / "BG5.png"))
    elif ball_instance.statbg == StatBG.LOW:
        image = Image.open(str(SOURCES_PATH / "BG6.png"))
    elif ball_instance.statbg == StatBG.LILLOW:
        image = Image.open(str(SOURCES_PATH / "BG7.png"))
    elif ball_instance.statbg == StatBG.VERYVERYHIGH:
        image = Image.open(str(SOURCES_PATH / "BG8.png"))
    elif ball_instance.statbg == StatBG.VERYHIGH:
        image = Image.open(str(SOURCES_PATH / "BG9.png"))
    elif ball_instance.statbg == StatBG.HIGH:
        image = Image.open(str(SOURCES_PATH / "BG10.png"))
    elif ball_instance.statbg == StatBG.LILHIGH:
        image = Image.open(str(SOURCES_PATH / "BG11.png"))
    elif ball_instance.statbg == StatBG.OTHER:
        image = Image.open(str(SOURCES_PATH / "BG13.png"))
    else:
        raise RuntimeError(f"statbg unknown: {ball_instance.statbg}")

    if ball.economy == Economy.AFOA:
        icon = Image.open(str(SOURCES_PATH / "afoa.png"))
    elif ball.economy == Economy.AFOE:
        icon = Image.open(str(SOURCES_PATH / "afoe.png"))
    elif ball.economy == Economy.AFOS:
        icon = Image.open(str(SOURCES_PATH / "afos.png"))
    elif ball.economy == Economy.AHOE:
        icon = Image.open(str(SOURCES_PATH / "ahoe.png"))
    elif ball.economy == Economy.LEGION:
        icon = Image.open(str(SOURCES_PATH / "legion.png"))
    else:
        raise RuntimeError(f"Economy unknown: {ball.economy}")

    draw = ImageDraw.Draw(image)
    draw.text((50, 20), ball.short_name or ball.country, font=title_font)
    for i, line in enumerate(textwrap.wrap(f"Ability: {ball.capacity_name}", width=28)):
        draw.text(
            (100, 1050 + 100 * i),
            line,
            font=capacity_name_font,
            fill=(230, 230, 230, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 255),
        )
    for i, line in enumerate(textwrap.wrap(ball.capacity_description, width=33)):
        draw.text(
            (60, 1300 + 60 * i),
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
        (960, 1670),
        str(ball_instance.attack),
        font=stats_font,
        fill=(252, 194, 76, 255),
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
    )
    draw.text(
        (30, 1870),
        # Modifying the line below is breaking the licence as you are removing credits
        # If you don't want to receive a DMCA, just don't
        "Created by El Laggron\n" f"Artwork author: {ball.credits}",
        font=credits_font,
        fill=(0, 0, 0, 255),
        stroke_width=0,
        stroke_fill=(255, 255, 255, 255),
    )

    artwork = Image.open("." + ball.collection_card)
    image.paste(ImageOps.fit(artwork, artwork_size), CORNERS[0])

    icon = ImageOps.fit(icon, (192, 192))
    image.paste(icon, (1200, 30), mask=icon)

    icon.close()
    artwork.close()

    return image
