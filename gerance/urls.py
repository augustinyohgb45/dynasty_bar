from django.urls import path

from . import views

urlpatterns = [
    path('', views.tableau_de_bord, name='tableau_de_bord'),  # vue générale du bar
    path('direct/', views.suivi_direct, name='suivi_direct'),  # suivi de la caisse en temps réel
    path('achats/', views.achats, name='achats'),
    path('achats/nouveau/', views.achat_nouveau, name='achat_nouveau'),
    path('achats/<int:achat_id>/', views.achat_detail, name='achat_detail'),
]
