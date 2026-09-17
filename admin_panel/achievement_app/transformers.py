from typing import TYPE_CHECKING

from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer

from .models import Achievement, AchievementCategory

if TYPE_CHECKING:
    from django.db.models import QuerySet


class AchievementTransformer(TTLModelTransformer[Achievement]):
    name = "achievement"
    model = Achievement

    def get_queryset(self) -> "QuerySet[Achievement]":
        # secret achievements can't be looked up, and drafts aren't live yet
        return (
            super()
            .get_queryset()
            .filter(hidden=False)
            .exclude(status=Achievement.Status.DRAFT)
            .select_related("ball", "special", "group", "category")
        )


class AchievementCategoryTransformer(TTLModelTransformer[AchievementCategory]):
    name = "category"
    model = AchievementCategory


AchievementTransform = app_commands.Transform[Achievement, AchievementTransformer]
AchievementCategoryTransform = app_commands.Transform[AchievementCategory, AchievementCategoryTransformer]
