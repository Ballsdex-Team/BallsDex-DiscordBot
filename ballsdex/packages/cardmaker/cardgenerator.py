import os
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ballsdex.settings import settings
from ballsdex.core.models import Ball  # Adjust import as needed

SOURCES_PATH = Path(os.path.dirname(os.path.abspath(__file__)), "ballsdex/core/image_generator/src")
WIDTH = 1500
HEIGHT = 2000

CORNERS = ((34, 261), (1393, 992))
artwork_size = [b - a for a, b in zip(*CORNERS)]

title_font = ImageFont.truetype(str(SOURCES_PATH / "LilitaOne-Regular.ttf"), 170)
capacity_name_font = ImageFont.truetype(str(SOURCES_PATH / "LilitaOne-Regular.ttf"), 110)
capacity_description_font = ImageFont.truetype(str(SOURCES_PATH / "LilitaOne-Regular.ttf"), 75)
stats_font = ImageFont.truetype(str(SOURCES_PATH / "LilitaOne-Regular.ttf"), 130)
credits_font = ImageFont.truetype(str(SOURCES_PATH / "arial.ttf"), 40)

credits_color_cache = {}

class CardGenerator:
    def __init__(self, ball: Ball, special: Special, media_path: str = "./admin_panel/media/"):
        self.ball = ball
        self.special = special | None = None
        self.media_path = media_path
        self.image = None
        self.draw = None

    def wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        paragraphs = text.split('%%')
        lines = []
        for para in paragraphs:
            words = para.strip().split(' ')
            current_line = ''
            for word in words:
                test_line = f"{current_line} {word}".strip()
                if self.draw.textlength(test_line, font=font) <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
        return lines

    def get_credit_color(self, region: tuple) -> tuple:
        region_crop = self.image.crop(region)
        brightness = sum(region_crop.convert("L").getdata()) / region_crop.width / region_crop.height
        return (255, 255, 255, 255) if brightness > 100 else (255, 255, 255, 255)

    def generate_image(self) -> tuple[Image.Image, dict[str, Any]]:
        ball = self.ball
        ball_health_color = (86, 255, 100, 255)
        card_name = ball.cached_regime.name

        # Load background image
        if self.special:
            card_name = getattr(self.special, "name", card_name)
            self.image = Image.open(self.media_path + self.special).convert("RGBA")
        else:
            self.image = Image.open(self.media_path + ball.cached_regime.background).convert("RGBA")

        icon = (
            Image.open(self.media_path + ball.cached_economy.icon).convert("RGBA")
            if ball.cached_economy else None
        )

        self.draw = ImageDraw.Draw(self.image)
        shadow_color = "black"
        shadow_offset = 3

        # Title
        self.draw.text((50, 20 + shadow_offset), ball.short_name or ball.country, font=title_font,
                       fill=shadow_color, stroke_width=8, stroke_fill=(0, 0, 0, 255))
        self.draw.text((50, 20), ball.short_name or ball.country, font=title_font,
                       fill=(255, 255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0, 255))

        # Capacity Name
        cap_name_lines = textwrap.wrap(ball.capacity_name, width=26)
        for i, line in enumerate(cap_name_lines):
            y = 1025 + 100 * i
            self.draw.text((100, y + shadow_offset), line, font=capacity_name_font, fill=shadow_color,
                           stroke_width=6, stroke_fill=(0, 0, 0, 255))
            self.draw.text((100, y), line, font=capacity_name_font, fill=(255, 255, 255, 255),
                           stroke_width=6, stroke_fill=(0, 0, 0, 255))

        # Capacity Description
        max_width = 1325
        wrapped_desc = self.wrap_text(ball.capacity_description, capacity_description_font, max_width)
        for i, line in enumerate(wrapped_desc):
            y = 1060 + 100 * len(cap_name_lines) + 80 * i
            self.draw.text((60, y + shadow_offset), line, font=capacity_description_font, fill=shadow_color,
                           stroke_width=5, stroke_fill=(0, 0, 0, 255))
            self.draw.text((60, y), line, font=capacity_description_font, fill=(255, 255, 255, 255),
                           stroke_width=5, stroke_fill=(0, 0, 0, 255))

        # Rarity
        if settings.show_rarity:
            self.draw.text((60, y + 100), ball.rarity_name, font=capacity_description_font,
                           stroke_width=5, stroke_fill=(0, 0, 0, 255))

        # Stats
        self.draw.text((320, 1670 + shadow_offset), str(ball.health), font=stats_font,
                       fill=shadow_color, stroke_width=7, stroke_fill=(0, 0, 0, 255))
        self.draw.text((320, 1670), str(ball.health), font=stats_font,
                       fill=ball_health_color, stroke_width=7, stroke_fill=(0, 0, 0, 255))

        self.draw.text((1120, 1670 + shadow_offset), str(ball.attack), font=stats_font,
                       fill=shadow_color, stroke_width=7, stroke_fill=(0, 0, 0, 255), anchor="ra")
        self.draw.text((1120, 1670), str(ball.attack), font=stats_font,
                       fill=(255, 66, 92, 255), stroke_width=7, stroke_fill=(0, 0, 0, 255), anchor="ra")

        # Credits
        if card_name not in credits_color_cache:
            credits_color_cache[card_name] = self.get_credit_color((0, int(self.image.height * 0.8),
                                                                    self.image.width, self.image.height))
        self.draw.text((30, 1870),
                       f"Ballsdex by El Laggron, BrawlDex by AngerRandom, Brawl Stars by Supercell\n{ball.credits}",
                       font=credits_font,
                       fill=credits_color_cache[card_name],
                       stroke_width=3,
                       stroke_fill=(0, 0, 0, 255))

        # Artwork
        artwork = Image.open(self.media_path + ball.collection_card).convert("RGBA")
        self.image.paste(ImageOps.fit(artwork, artwork_size), CORNERS[0])
        artwork.close()

        # Icon
        if icon:
            icon = ImageOps.fit(icon, (192, 192))
            self.image.paste(icon, (1200, 30), mask=icon)
            icon.close()

        return self.image, {"format": "PNG"}
