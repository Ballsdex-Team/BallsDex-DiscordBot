import os

from django.apps import AppConfig


class MerchantExtConfig(AppConfig):
    name = "merchant_ext"
    dpy_package = "merchant_ext.package"
    path = os.path.dirname(os.path.abspath(__file__))
