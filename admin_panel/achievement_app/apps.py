from django.apps import AppConfig


class AchievementAppConfig(AppConfig):
    name = "achievement_app"

    def ready(self):
        from . import checkers  # noqa: F401

        return super().ready()
