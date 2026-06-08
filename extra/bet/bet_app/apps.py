import os

from django.apps import AppConfig


class BetAppConfig(AppConfig):
    name = "bet_app"
    dpy_package = "bet_app.bet_ext"
    path = os.path.dirname(os.path.abspath(__file__))
