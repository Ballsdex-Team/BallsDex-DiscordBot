from django.apps import AppConfig


class CollectibleAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "collectible_app"
    verbose_name = "Collectible Models"
    dpy_package = "collectible_app.collectible_ext"
