from django.contrib import admin

from .models import JournalAudit


@admin.register(JournalAudit)
class JournalAuditAdmin(admin.ModelAdmin):
    list_display = ('date', 'nom_utilisateur', 'action', 'type_objet', 'objet', 'montant', 'adresse_ip')
    list_filter = ('action', 'type_objet')
    search_fields = ('nom_utilisateur', 'objet', 'details')
    date_hierarchy = 'date'

    # Le journal ne se modifie pas : consultation seule, même pour le gérant
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
