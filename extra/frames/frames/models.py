from django.db import models

from bd_models.models import Ball


class FrameBall(Ball):
    """
    Proxy of Ball used exclusively by the Frames admin section.
    No new database table is created; all frame data lives in Ball.capacity_logic
    as ``{"MM-DD": {"card": "...", "spawn": "...", "credits": "...", "catch": "..."}}``.
    """

    class Meta:
        proxy = True
        verbose_name = "Frame"
        verbose_name_plural = "Frames"
