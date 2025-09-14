"""Utility functions for the Miner Wheel package"""

import os
from typing import List, Optional
from ballsdex.core.models import Ball


async def get_all_miners() -> List[Ball]:
    """Get all enabled miners from the database"""
    return [ball for ball in await Ball.filter(enabled=True) if ball.country]


def get_miner_image_path(ball: Ball) -> str:
    """Get the file path for a miner's image"""
    return f"/code/admin_panel/media/{ball.wild_card}"


def image_exists(path: str) -> bool:
    """Check if an image file exists"""
    return os.path.exists(path)