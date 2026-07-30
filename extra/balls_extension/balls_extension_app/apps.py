import os

from django.apps import AppConfig


class BallsExtensionAppConfig(AppConfig):
    name = "balls_extension_app"
    dpy_package = "balls_extension_app.balls_extension_ext"
    path = os.path.dirname(os.path.abspath(__file__))
