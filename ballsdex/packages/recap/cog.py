from typing import TYPE_CHECKING, Optional, cast

import discord
from discord import app_commands
from discord.ext import commands
import random
import io
import datetime
from ballsdex.core.models import GuildConfig
from ballsdex.core.models import (
    BallInstance,
    Ball,
    DonationPolicy,
    Player,
    Special,
    Trade,
    TradeObject,
)
from tortoise.expressions import Q

from ballsdex.packages.config.components import AcceptTOSView
from ballsdex.settings import settings
import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

title_font = ImageFont.truetype(str(Path('./ballsdex/core/image_generator/src/') / "Bobby Jones Soft.otf"), 110)
sub_font = ImageFont.truetype(str(Path('./ballsdex/core/image_generator/src/') / "Bobby Jones Soft.otf"), 90)
sub_font_2 = ImageFont.truetype(str(Path('./ballsdex/core/image_generator/src/') / "Bobby Jones Soft.otf"), 75)

user_font = ImageFont.truetype(str(Path('./ballsdex/core/image_generator/src/') / "arial.ttf"), 70)



if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Recap(commands.Cog):
    """
    View and manage your 2025 recap.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.choices(
        theme=[
            app_commands.Choice(name="Sea", value="sea"),
            app_commands.Choice(name="Sunset", value="sunset"),
            app_commands.Choice(name="Fireworks", value="fireworks"),
        ]
    )
    async def recap(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        theme: app_commands.Choice[str]| None = None
    ):
        """
        View your 2025 countryballs recap.
        
        """
        await interaction.response.defer(ephemeral=True)
        player = await Player.get_or_none(discord_id=interaction.user.id)
        if not player:
            await interaction.followup.send(
                "You don't have a player profile yet. Start catching balls to create one!",
                ephemeral=True
            )
            return
        first_jan = datetime.datetime(year=2025, month=1, day=1)
        last_dec = datetime.datetime(year=2025, month=12, day=26, hour=23, minute=59, second=59)
        balls = await BallInstance.filter(player=player, catch_date__gte=first_jan, catch_date__lte=last_dec).prefetch_related('trade_player', 'ball')
        trades_received = await Trade.filter(
            player2=player,
            date__gte=first_jan,
            date__lte=last_dec
        ).prefetch_related('player1')
        total_received = 0
        for trade in trades_received:
            trade_objects = await TradeObject.filter(trade=trade, player=trade.player1)
            total_received += len(trade_objects)
        total_self_caught = len([x for x in balls if x.trade_player is None])
        total_trades = await Trade.filter(
            Q(player1=player) | Q(player2=player),
            date__gte=first_jan,
            date__lte=last_dec
        ).prefetch_related('player1', 'player2')
        # best friend is user they traded the most with, could be player1 or player2
        friend_trade_counts = {}
        for trade in total_trades:
            if trade.player1.discord_id == player.discord_id:
                friend_id = trade.player2.discord_id
            else:
                friend_id = trade.player1.discord_id
            if friend_id not in friend_trade_counts:
                friend_trade_counts[friend_id] = 0
            friend_trade_counts[friend_id] += 1
        if friend_trade_counts:
            best_friend_id = max(friend_trade_counts, key=lambda x: friend_trade_counts[x])
            try:
                best_friend_player = await self.bot.fetch_user(int(best_friend_id))
            except Exception:
                best_friend_player = "Not found"
            if best_friend_player != "Not found":
                best_friend = best_friend_player.display_name
            else:
                best_friend = "Unknown"
        else:
            best_friend = "No trades"
        # fastest catch is catch_date minus spawn_date in BallInstance
        fastest_time = None
        for ball in balls:
            if ball.spawned_time and ball.catch_date and ball.trade_player is None:
                catch_time = (ball.catch_date - ball.spawned_time).total_seconds()
                if fastest_time is None or catch_time < fastest_time:
                    fastest_time = catch_time
        # best ball is the ball caught the most times
        ball_counts = {}
        for ball in balls:
            ball_name = ball.ball.country
            if ball_name not in ball_counts:
                ball_counts[ball_name] = 0
            ball_counts[ball_name] += 1
        best_ball = "N/A"
        best_ball = max(ball_counts, key=lambda x: ball_counts[x]) if ball_counts else "N/A"
        best_ball_self_caught = 0
        best_ball_trade_caught = 0
        if best_ball == "N/A":
            best_ball_self_caught = 0
            best_ball_trade_caught = 0
        for ball in balls:
            if ball.ball.country == best_ball and ball.trade_player is None:
                best_ball_self_caught += 1
            elif ball.ball.country == best_ball and ball.trade_player is not None:
                best_ball_trade_caught += 1
        if best_ball != "N/A":
            ball = await Ball.get(country=best_ball)
            best_ball = ball.short_name	or ball.country
        total_trades = len(total_trades)
        # save user_avatar to a io
        avatar_bytes = await interaction.user.display_avatar.read()
        art = gen_recap_image(
            theme,
            interaction.user,
            user_avatar=avatar_bytes,
            total=len(balls),
            total_self=total_self_caught,
            total_trade_Receied=total_received,	
            total_trades=total_trades,
            best_friend=best_friend,
            best_ball=best_ball,
            fastest_catch=f"{fastest_time:.3f}" if fastest_time is not None else "N/A",
            self_caught=best_ball_self_caught,
            traded=best_ball_trade_caught
        )
        with io.BytesIO() as image_binary:
            art.save(image_binary, 'WEBP')
            image_binary.seek(0)
            file = discord.File(fp=image_binary, filename='recap.webp')
            await interaction.followup.send(file=file, ephemeral=True)

    @app_commands.command()
    async def daily(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        type: bool = False
    ):
        """
        View your daily recap.
        
        """
        await interaction.response.defer(ephemeral=True)
        balls = await Ball.filter(enabled=True)
        ball_countries = [ball.country for ball in balls]
        selected_countries = random.sample(ball_countries, k=5)
        selected_balls = []
        for country in selected_countries:
            ball = await Ball.get(country=country)
            selected_balls.append("./admin_panel/media/" + ball.wild_card)
        if type:
            # CS:GO style animation
            animation_bytes = create_csgo_lootbox_animation(selected_balls, output_path="daily_recap.gif", frame_size=(500, 500), duration=50)
        else:
            animation_bytes = create_lootbox_animation(selected_balls, output_path="daily_recap.gif", frame_size=(500, 500), duration=100)
        file = discord.File(fp=animation_bytes, filename='daily_recap.gif')
        await interaction.followup.send(file=file, ephemeral=True)

def gen_recap_image(theme, user, user_avatar, total:int, total_self: int, total_trade_Receied:int, total_trades:int, best_friend: str, best_ball: str, fastest_catch: str, self_caught: int, traded: int) -> Image.Image:
    if theme is None:
        images = ['./ballsdex/core/image_generator/src/bd_recap1.png', './ballsdex/core/image_generator/src/bd_recap2.png', './ballsdex/core/image_generator/src/bd_recap3.png']
        random.seed(user.id)
        img_path = random.choice(images)
    else:
        if theme.value == "sea":
            img_path = './ballsdex/core/image_generator/src/bd_recap1.png'
        elif theme.value == "sunset":
            img_path = './ballsdex/core/image_generator/src/bd_recap3.png'
        elif theme.value == "fireworks":
            img_path = './ballsdex/core/image_generator/src/bd_recap2.png'
        else:
            img_path = './ballsdex/core/image_generator/src/bd_recap1.png'
    image = Image.open(img_path).convert("RGBA")
    # Paste the avatar as a circle in the middle top
    avatar_size = (330, 330)
    avatar = Image.open(io.BytesIO(user_avatar)).convert("RGBA")
    avatar = avatar.resize(avatar_size)

    mask = Image.new("L", avatar_size, 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0) + avatar_size, fill=255)
    avatar = ImageOps.fit(avatar, mask.size, centering=(0.5, 0.5))
    avatar.putalpha(mask)
    image.paste(avatar, (380, 45), avatar)


    draw = ImageDraw.Draw(image)
    draw.text(
        (550, 820),
        f"{total:,}",
        font=title_font,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255),
        anchor="mm"
    )

    draw.text(
        (550, 450),
        "2025",
        font=title_font,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255),
        anchor="mm"
    )

    # Tit


    # Total self caught value slot
    draw.text((230, 1150), f"{total_self:,}", font=sub_font, fill=(255, 255, 255, 255),
            stroke_width=2, stroke_fill=(0, 0, 0, 255), anchor="mm")

    # # Total trades label
    # # Total trades value slot
    draw.text((530, 1280), f"{total_trades:,}", font=sub_font, fill=(255, 255, 255, 255),
            stroke_width=2, stroke_fill=(0, 0, 0, 255), anchor="mm")

    # # Total received from trade label
    # # Total received from trade value slot
    draw.text((850, 1150), f"{total_trade_Receied:,}", font=sub_font, fill=(255, 255, 255, 255),
            stroke_width=2, stroke_fill=(0, 0, 0, 255), anchor="mm")

    # # Best friend label
    # # Best friend 13 slot
    if len(best_friend) > 15:
        best_friend = best_friend[:12] + "..."
        draw.text((400, 1420), best_friend, font=user_font, fill=(255, 255, 255, 255),
                stroke_width=1, stroke_fill=(0, 0, 0, 255), anchor="mm")
    elif len(best_friend) > 8:
        draw.text((250, 1420), best_friend, font=user_font, fill=(255, 255, 255, 255),
                stroke_width=1, stroke_fill=(0, 0, 0, 255), anchor="mm")
    else:
        draw.text((230, 1420), best_friend, font=user_font, fill=(255, 255, 255, 255),
                stroke_width=1, stroke_fill=(0, 0, 0, 255), anchor="mm")

    # # Fastest catch value slot
    draw.text((850, 1430), fastest_catch, font=sub_font, fill=(255, 255, 255, 255),
            stroke_width=1, stroke_fill=(0, 0, 0, 255), anchor="mm")

    # # Best country value slot (image would go here, but text version)
    draw.text((530, 1635), best_ball, font=sub_font_2, fill=(255, 255, 255, 255),
            stroke_width=1, stroke_fill=(0, 0, 0, 255), anchor="mm")

    # # Self caught value slot
    draw.text((230, 1780), f"{self_caught:,}", font=sub_font_2, fill=(255, 255, 255, 255),
            stroke_width=1, stroke_fill=(0, 0, 0, 255), anchor="mm")

    # # Traded value slot
    draw.text((820, 1780), f"{traded:,}", font=sub_font_2, fill=(255, 255, 255, 255),
            stroke_width=1, stroke_fill=(0, 0, 0, 255), anchor="mm")
    return image


def create_lootbox_animation(image_paths, output_path, frame_size=(500, 500), duration=100):
    """
    Create a lootbox-style opening animation GIF.

    :param image_paths: List of paths to the images to include in the animation.
    :param output_path: Path to save the resulting GIF.
    :param frame_size: Size of each frame in the animation (width, height).
    :param duration: Duration of each frame in milliseconds.
    """
    frames = []

    # Load images and resize them to fit the frame size (use high-quality resampling)
    images = []
    for path in image_paths:
        img = Image.open(path).convert("RGBA")
        img = img.resize(frame_size, resample=Image.LANCZOS)
        images.append(img)

    # Create animation frames with a transparent background
    for image in images:
        for scale in range(10, 21):  # Zoom-in effect
            frame = Image.new("RGBA", frame_size, (0, 0, 0, 0))  # fully transparent background
            scaled_size = (frame_size[0] * scale // 20, frame_size[1] * scale // 20)
            scaled_image = image.resize(scaled_size, resample=Image.Resampling.LANCZOS)
            pos = ((frame_size[0] - scaled_image.width) // 2, (frame_size[1] - scaled_image.height) // 2)
            frame.paste(scaled_image, pos, scaled_image)  # use alpha mask for smooth edges
            frames.append(frame)

    for _ in range(10):  # Final display of the last image
        frame = Image.new("RGBA", frame_size, (0, 0, 0, 0))  # fully transparent background
        last = images[-1].resize(images[-1].size, resample=Image.Resampling.LANCZOS)
        pos = ((frame_size[0] - last.width) // 2, (frame_size[1] - last.height) // 2)
        frame.paste(last, pos, last)
        frames.append(frame)

    # Save as GIF
    output = io.BytesIO()
    frames[0].save(
        output,
        format='GIF',
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        transparency=0  # Ensure transparency is preserved
    )
    output.seek(0)
    return output


def create_csgo_lootbox_animation(image_paths, output_path, frame_size=(500, 500), duration=50):
    """
    Create a CS:GO-style lootbox animation GIF with a vertical bar.

    :param image_paths: List of paths to the images to include in the animation.
    :param output_path: Path to save the resulting GIF.
    :param frame_size: Size of each frame in the animation (width, height).
    :param duration: Duration of each frame in milliseconds.
    """
    frames = []

    # Load images and resize them to fit the frame height
    images = []
    for path in image_paths:
        with open(path, 'rb') as f:
            img = Image.open(f)
            img = img.convert("RGBA")
            f.seek(0)
            img.load()
            
        # Make images smaller (60% of frame height) so they fit better
        aspect_ratio = img.width / img.height
        new_height = int(frame_size[1] * 0.6)
        new_width = int(new_height * aspect_ratio)
        img = img.resize((new_width, new_height), resample=Image.LANCZOS)
        images.append(img)

    # Create animation frames
    # Calculate where to stop so the last image is centered
    total_images_width = sum(img.width for img in images[:-1])  # Width of all images except the last
    last_image_center_x = (frame_size[0] - images[-1].width) // 2  # Where last image should be centered
    stop_offset = last_image_center_x - total_images_width  # Offset needed to center the last image
    
    x_offset = frame_size[0]  # Start with all images off-screen to the right

    while x_offset > stop_offset:
        # Create a fresh frame with white background for each iteration
        frame = Image.new("RGBA", frame_size, (255, 255, 255, 255))

        current_x = x_offset
        for img in images:
            # Only paste if the image is visible in the current frame
            if current_x + img.width > 0 and current_x < frame_size[0]:
                # Center images vertically
                y_pos = (frame_size[1] - img.height) // 2
                # Create a copy of the image to avoid modifying the original
                img_copy = img.copy()
                # Paste using alpha channel as mask for proper transparency
                frame.paste(img_copy, (current_x, y_pos), img_copy)
            current_x += img.width

        # Draw the vertical bar in the middle (lottery wheel style)
        draw = ImageDraw.Draw(frame)
        bar_width = 20
        bar_x = (frame_size[0] - bar_width) // 2
        
        # Draw shadow/outline
        draw.rectangle(
            [(bar_x - 3, 0), (bar_x + bar_width + 3, frame_size[1])], 
            fill=(0, 0, 0, 180)
        )
        
        # Draw main bar with gradient effect using multiple rectangles
        for i in range(bar_width):
            color_value = int(255 - (i * 30 / bar_width))  # Gradient effect
            draw.rectangle(
                [(bar_x + i, 0), (bar_x + i + 1, frame_size[1])], 
                fill=(255, color_value, 0, 255)  # Orange-yellow gradient
            )
        
        # Draw border
        draw.rectangle(
            [(bar_x, 0), (bar_x + bar_width, frame_size[1])], 
            outline=(255, 255, 255, 255),
            width=2
        )
        
        # Draw arrows at top and bottom pointing inward
        bar_center_x = bar_x + bar_width // 2
        arrow_size = 30
        
        # Top arrow pointing down
        draw.polygon(
            [(bar_center_x, 10 + arrow_size), (bar_center_x - arrow_size, 10), (bar_center_x + arrow_size, 10)],
            fill=(255, 200, 0, 255),
            outline=(255, 255, 255, 255)
        )
        
        # Bottom arrow pointing up
        draw.polygon(
            [(bar_center_x, frame_size[1] - 10 - arrow_size), (bar_center_x - arrow_size, frame_size[1] - 10), (bar_center_x + arrow_size, frame_size[1] - 10)],
            fill=(255, 200, 0, 255),
            outline=(255, 255, 255, 255)
        )

        frames.append(frame)
        x_offset -= 20  # Move images to the left

    # Create the final frame with the last image centered and hold it for a few seconds
    final_frame = Image.new("RGBA", frame_size, (255, 255, 255, 255))  # White background
    last_image = images[-1]
    last_image_x = (frame_size[0] - last_image.width) // 2
    last_image_y = (frame_size[1] - last_image.height) // 2
    final_frame.paste(last_image, (last_image_x, last_image_y), last_image)

    draw = ImageDraw.Draw(final_frame)
    bar_width = 20
    bar_x = (frame_size[0] - bar_width) // 2
    
    # Draw shadow/outline
    draw.rectangle(
        [(bar_x - 3, 0), (bar_x + bar_width + 3, frame_size[1])], 
        fill=(0, 0, 0, 180)
    )
    
    # Draw main bar with gradient effect using multiple rectangles
    for i in range(bar_width):
        color_value = int(255 - (i * 30 / bar_width))  # Gradient effect
        draw.rectangle(
            [(bar_x + i, 0), (bar_x + i + 1, frame_size[1])], 
            fill=(255, color_value, 0, 255)  # Orange-yellow gradient
        )
    
    # Draw border
    draw.rectangle(
        [(bar_x, 0), (bar_x + bar_width, frame_size[1])], 
        outline=(255, 255, 255, 255),
        width=2
    )
    
    # Draw arrows at top and bottom pointing inward
    bar_center_x = bar_x + bar_width // 2
    arrow_size = 30
    
    # Top arrow pointing down
    draw.polygon(
        [(bar_center_x, 10 + arrow_size), (bar_center_x - arrow_size, 10), (bar_center_x + arrow_size, 10)],
        fill=(255, 200, 0, 255),
        outline=(255, 255, 255, 255)
    )
    
    # Bottom arrow pointing up
    draw.polygon(
        [(bar_center_x, frame_size[1] - 10 - arrow_size), (bar_center_x - arrow_size, frame_size[1] - 10), (bar_center_x + arrow_size, frame_size[1] - 10)],
        fill=(255, 200, 0, 255),
        outline=(255, 255, 255, 255)
    )

    # Add the final frame multiple times to hold it for longer (e.g., 100 frames at 50ms = 5 seconds)
    for _ in range(100):
        frames.append(final_frame.copy())

    # Save as GIF with white background
    output = io.BytesIO()
    # Convert all frames to RGB with white background for consistent rendering
    rgb_frames = []
    for frame in frames:
        rgb_frame = Image.new("RGB", frame.size, (255, 255, 255))
        rgb_frame.paste(frame, (0, 0), frame if frame.mode == 'RGBA' else None)
        rgb_frames.append(rgb_frame)
    
    rgb_frames[0].save(
        output,
        format='GIF',
        save_all=True,
        append_images=rgb_frames[1:],
        duration=duration,
        loop=0
    )
    output.seek(0)
    return output

# Example usage
# image_paths = ["path_to_image1.png", "path_to_image2.png", "path_to_image3.png"]
# create_lootbox_animation(image_paths, "output.gif")


