from django.urls import path

from .views import render_image

urlpatterns = [
    path("ball/generate/<int:ball_pk>", render_image),
]
