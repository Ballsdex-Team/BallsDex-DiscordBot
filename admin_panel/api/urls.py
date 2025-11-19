from django.urls import path
from .views import BallInstancesView

urlpatterns = [
    path('ball-instances/', BallInstancesView.as_view(), name='ball-instances'),
]