from django.urls import path

from . import views

urlpatterns = [
    path('', views.stock, name='stock'),  # état du stock
    path('mouvements/', views.mouvements, name='mouvements'),  # saisie et historique des mouvements
    path('produits/nouveau/', views.produit_nouveau, name='produit_nouveau'),
    path('produits/<int:produit_id>/modifier/', views.produit_modifier, name='produit_modifier'),
    path('importer/', views.importer, name='importer'),  # import du catalogue Excel (administrateurs)
]
