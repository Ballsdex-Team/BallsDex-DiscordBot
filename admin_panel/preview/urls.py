from django.urls import path

from .views import render_ballinstance, render_special

urlpatterns = [
    path("ball/generate/<int:ball_pk>", render_ballinstance),
    path("special/generate/<int:special_pk>", render_special),
]
