from django.contrib import admin

from .models import Commande, LigneCommande, Paiement, Table


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('nom', 'zone', 'ordre', 'active')
    list_editable = ('zone', 'ordre', 'active')
    list_filter = ('zone', 'active')


class LigneInline(admin.TabularInline):
    model = LigneCommande
    extra = 0
    readonly_fields = ('produit', 'quantite', 'prix_unitaire', 'mouvement')
    can_delete = False


class PaiementInline(admin.TabularInline):
    model = Paiement
    extra = 0
    readonly_fields = ('mode', 'montant', 'reference', 'recu_par', 'date')
    can_delete = False


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ('numero', 'emplacement', 'serveur', 'statut', 'date_ouverture', 'date_cloture')
    list_filter = ('statut', 'table__zone', 'serveur')
    date_hierarchy = 'date_ouverture'
    inlines = [LigneInline, PaiementInline]
    # Les commandes se gèrent depuis la caisse : consultation seule ici
    readonly_fields = ('table', 'client', 'serveur', 'statut', 'date_ouverture', 'date_cloture', 'motif_annulation')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
