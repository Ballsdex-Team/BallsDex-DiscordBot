from django.apps import AppConfig


class AchievementAppConfig(AppConfig):
    name = "achievement_app"
    dpy_package = "achievement_app.package"

    def ready(self):
        from . import checkers  # noqa: F401

        return super().ready()
