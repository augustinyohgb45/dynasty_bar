from django.urls import path

from . import views

urlpatterns = [
    path('', views.journal, name='journal'),  # journal d'audit (gérant)
]
