import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from settings.models import settings

if TYPE_CHECKING:
    from bd_models.models import BallInstance


SOURCES_PATH = Path(os.path.dirname(os.path.abspath(__file__)), "./src")

CORNERS = ((34, 261), (1393, 992))
artwork_size = [b - a for a, b in zip(*CORNERS)]

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

title_font = ImageFont.truetype(str(SOURCES_PATH / "Hobeaux-Bold.otf"), 165) # if needed put this back to 170
capacity_name_font = ImageFont.truetype(str(SOURCES_PATH / "Bobby Jones Soft.otf"), 110)
capacity_description_font = ImageFont.truetype(str(SOURCES_PATH / "OpenDyslexic-Bold.ttf"), 65)
stats_font = ImageFont.truetype(str(SOURCES_PATH / "Bobby Jones Soft.otf"), 130)
credits_font = ImageFont.truetype(str(SOURCES_PATH / "arial.ttf"), 40)

credits_color_cache = {}

def alpha_paste(base: Image.Image, overlay: Image.Image, position: tuple[int, int] = (0, 0)) -> None:
    overlay = overlay.convert("RGBA")
    base.paste(overlay, position, overlay)

def alpha_fit_paste(base: Image.Image, overlay: Image.Image, position: tuple[int, int], size: tuple[int, int] | list[int]) -> None:
    fitted = ImageOps.fit(overlay.convert("RGBA"), size)
    base.paste(fitted, position, fitted)
    fitted.close()

def has_artwork_hole(background: Image.Image, threshold: float = 0.25, alpha_cutoff: int = 240) -> bool:
    x1, y1 = CORNERS[0]
    x2, y2 = CORNERS[1]

    alpha = background.convert("RGBA").getchannel("A").crop((x1, y1, x2, y2))
    histogram = alpha.histogram()

    transparent_pixels = sum(histogram[:alpha_cutoff])
    total_pixels = alpha.width * alpha.height

    return (transparent_pixels / total_pixels) >= threshold


def get_credit_color(image: Image.Image, region: tuple) -> tuple:
    image = image.crop(region)
    brightness = sum(image.convert("L").getdata()) / image.width / image.height  # type: ignore
    return (0, 0, 0, 255) if brightness > 100 else (255, 255, 255, 255)


def draw_card(ball_instance: "BallInstance") -> tuple[Image.Image, dict[str, Any]]:
    ball = ball_instance.countryball
    ball_health = (237, 115, 101, 255)
    ball_credits = ball.credits
    special_credits = ""
    card_name = ball.cached_regime.name
    background_overlay = None

    ball_card_name = ball.short_name if ball.short_name else ball.country
    if ball_instance.nickname != "None":
        ball_card_name = ball_instance.nickname

    if ball_instance.specialcard:
        if ball_instance.specialcard.name.endswith("(Variant)"):
            image = Image.open(ball.cached_regime.background).convert("RGBA")
            background_overlay = Image.open(ball.cached_regime.background).convert("RGBA")
        elif "Full Art" in ball_instance.specialcard.name:
            image = Image.open(ball.fullart_card).convert("RGBA")
            background_overlay = None

            if ball.credits.endswith("^^^"):
                ball_card_name = "" 
        else:
            image = Image.open(ball_instance.specialcard.background).convert("RGBA")
            background_overlay = Image.open(ball_instance.specialcard.background).convert("RGBA")
            special_credits = f" ● {ball_instance.specialcard.credits}"
    else:
        image = Image.open(ball.cached_regime.background).convert("RGBA")
        background_overlay = Image.open(ball.cached_regime.background).convert("RGBA")
    image = image.convert("RGBA")
    icon = Image.open(ball.cached_economy.icon).convert("RGBA") if ball.cached_economy else None

    artwork = None

    if ball_instance.specialcard:
        if ball_instance.specialcard.name.endswith("(Variant)"):
            artwork = Image.open(ball_instance.specialcard.background).convert("RGBA")
            alpha_fit_paste(image, artwork, CORNERS[0], artwork_size)
        elif "Full Art" in ball_instance.specialcard.name:
            artwork = None
        else:
            artwork = Image.open(ball.collection_card).convert("RGBA")
            alpha_fit_paste(image, artwork, CORNERS[0], artwork_size)
    else:
        artwork = Image.open(ball.collection_card).convert("RGBA")
        alpha_fit_paste(image, artwork, CORNERS[0], artwork_size)
    
    if background_overlay is not None and has_artwork_hole(background_overlay):
        alpha_paste(image, background_overlay, (0, 0))
    
    if background_overlay is not None:
        background_overlay.close()
    
    if artwork is not None:
        artwork.close()

    draw = ImageDraw.Draw(image)

    draw.text((50, 20), ball_card_name, font=title_font, stroke_width=2, stroke_fill=(0, 0, 0, 255))


    if ball.capacity_name == "Plus":
        if str(ball_instance.pk).endswith("1") or str(ball_instance.pk).endswith("3") or str(ball_instance.pk).endswith("5") or str(ball_instance.pk).endswith("7") or str(ball_instance.pk).endswith("9"):
            ability_real = "Plus"
            desk_real = f"{ball.country}'s stats are doubled if an active team member has the Minus ability."
        elif str(ball_instance.pk).endswith("0") or str(ball_instance.pk).endswith("2") or str(ball_instance.pk).endswith("4") or str(ball_instance.pk).endswith("6") or str(ball_instance.pk).endswith("8"):
            ability_real = "Minus"
            desk_real = f"{ball.country}'s stats are doubled if an active team member has the Plus ability."
    else:
        ability_real = ball.capacity_name
        desk_real = ball.capacity_description

    for i, line in enumerate(textwrap.wrap(ability_real)): #width=26
        draw.text(
            (60, 1015 + 100 * i),
            line,
            font=capacity_name_font,
            fill=(255, 255, 255, 255),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 255),
        )

    for i, line in enumerate(textwrap.wrap(desk_real, width=32)):
        draw.text(
            (60, 1150 + 70 * i),
            line,
            font=capacity_description_font,
            stroke_width=2,
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
        credits_color = get_credit_color(image, (0, int(image.height * 0.8), image.width, image.height))
        credits_color_cache[card_name] = credits_color
    
    the_credits = ball.credits[:-3] if ball.credits.endswith("^^^") else ball.credits 

    draw.text(
        (30, 1870),
        # Modifying the line below is breaking the licence as you are removing credits
        # If you don't want to receive a DMCA, just don't
        f"Created by El Laggron{special_credits}\nArtwork author: {the_credits}",
        font=credits_font,
        fill=credits_color,
        stroke_width=0,
        stroke_fill=(255, 255, 255, 255),
    )

    if icon:
        icon = ImageOps.fit(icon, (192, 192))
        image.paste(icon, (1200, 30), mask=icon)
        icon.close()

    return image, {"format": "PNG"}