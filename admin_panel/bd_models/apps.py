from django.apps import AppConfig

from ballsdex.settings import settings


class BdModelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bd_models"
    verbose_name = f"{settings.bot_name} models"
