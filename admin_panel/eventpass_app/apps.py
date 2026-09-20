from django.apps import AppConfig


class EventPassAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "eventpass_app"
    verbose_name = "Event passes"
    dpy_package = "eventpass_app.package"
