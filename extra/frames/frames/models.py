from django.db import models

from bd_models.models import Ball


class FrameBall(Ball):
    """
    Proxy of Ball used exclusively by the Frames admin section.
    No new database table is created; all frame data lives in Ball.capacity_logic
    as ``{"MM-DD-YYYY": {"card": "...", "spawn": "...", "credits": "...", "catch": "..."}}``, and
    ``{"MM-DD-YYYY:<special id>": {...}}`` for a frame of the treasures of a special only (``:0`` without special).
    """

    class Meta:
        proxy = True
        verbose_name = "Frame"
        verbose_name_plural = "Frames"
