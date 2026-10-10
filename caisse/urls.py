from django.urls import path

from . import views

urlpatterns = [
    path('', views.tables, name='tables'),  # plan des tables
    path('ouvrir/', views.ouvrir, name='ouvrir_comptoir'),  # vente au comptoir
    path('ouvrir/<int:table_id>/', views.ouvrir, name='ouvrir_table'),
    path('commande/<int:commande_id>/', views.commande, name='commande'),
    path('commande/<int:commande_id>/ajouter/', views.ajouter, name='ajouter'),
    path('commande/<int:commande_id>/payer/', views.payer, name='payer'),
    path('commande/<int:commande_id>/annuler/', views.annuler, name='annuler'),
    path('commande/<int:commande_id>/ticket/', views.ticket, name='ticket'),
    path('ligne/<int:ligne_id>/retirer/', views.retirer, name='retirer'),
    path('ventes/', views.ventes, name='ventes'),  # bilan de la soirée
]
