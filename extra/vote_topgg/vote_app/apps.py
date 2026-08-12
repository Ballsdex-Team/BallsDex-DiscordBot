import os

from django.apps import AppConfig


class VoteAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vote_app"
    dpy_package = "vote_app.vote_ext"
    path = os.path.dirname(os.path.abspath(__file__))
