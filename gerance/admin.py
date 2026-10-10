from django.contrib import admin

from .models import Achat, LigneAchat


class LigneAchatInline(admin.TabularInline):
    model = LigneAchat
    extra = 0
    readonly_fields = ('produit', 'quantite', 'prix_unitaire', 'mouvement')
    can_delete = False


@admin.register(Achat)
class AchatAdmin(admin.ModelAdmin):
    list_display = ('date', 'fournisseur', 'reference', 'utilisateur')
    search_fields = ('fournisseur', 'reference')
    date_hierarchy = 'date'
    inlines = [LigneAchatInline]
    # Les achats se saisissent depuis l'espace gérance (le stock et le journal suivent)
    readonly_fields = ('fournisseur', 'reference', 'date', 'note', 'utilisateur')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
