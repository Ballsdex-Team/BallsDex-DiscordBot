from django.urls import path

from .views import topgg_webhook

urlpatterns = [
    path("topgg", topgg_webhook),
]
