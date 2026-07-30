from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer

from .models import Achievement


class AchievementTransformer(TTLModelTransformer[Achievement]):
    name = "achievement"
    model = Achievement


AchievementTransform = app_commands.Transform[Achievement, AchievementTransformer]
