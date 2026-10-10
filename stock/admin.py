from django.contrib import admin

from .models import Categorie, MouvementStock, Produit


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ('nom', 'ordre')
    list_editable = ('ordre',)


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ('code', 'nom', 'categorie', 'prix_achat', 'prix_vente', 'seuil_alerte', 'actif')
    list_filter = ('categorie', 'actif')
    search_fields = ('code', 'nom')


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ('date', 'produit', 'type', 'quantite', 'prix_unitaire', 'utilisateur', 'motif')
    list_filter = ('type', 'produit__categorie')
    search_fields = ('produit__nom', 'motif')
    date_hierarchy = 'date'
