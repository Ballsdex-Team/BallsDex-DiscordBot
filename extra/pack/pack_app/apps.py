import os

from django.apps import AppConfig


class PackAppConfig(AppConfig):
    name = "pack_app"
    dpy_package = "pack_app.pack_ext"
    path = os.path.dirname(os.path.abspath(__file__))
