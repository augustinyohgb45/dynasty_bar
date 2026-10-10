from django.conf import settings
from django.db import models


class JournalAudit(models.Model):
    # Sessions
    CONNEXION = 'connexion'
    DECONNEXION = 'deconnexion'
    ECHEC_CONNEXION = 'echec_connexion'
    # Caisse
    OUVERTURE = 'ouverture'
    AJOUT = 'ajout'
    RETRAIT = 'retrait'
    PAIEMENT = 'paiement'
    ANNULATION = 'annulation'
    # Stock
    RECEPTION = 'reception'
    ACHAT = 'achat'
    PERTE = 'perte'
    INVENTAIRE = 'inventaire'
    IMPORT = 'import'
    # Données (catalogue, tables, comptes…)
    CREATION = 'creation'
    MODIFICATION = 'modification'
    SUPPRESSION = 'suppression'

    ACTIONS = [
        (CONNEXION, "Connexion"),
        (DECONNEXION, "Déconnexion"),
        (ECHEC_CONNEXION, "Échec de connexion"),
        (OUVERTURE, "Ouverture de commande"),
        (AJOUT, "Ajout d'article"),
        (RETRAIT, "Retrait d'article"),
        (PAIEMENT, "Encaissement"),
        (ANNULATION, "Annulation de commande"),
        (RECEPTION, "Réception de stock"),
        (ACHAT, "Achat"),
        (PERTE, "Casse / offert"),
        (INVENTAIRE, "Ajustement d'inventaire"),
        (IMPORT, "Import du catalogue"),
        (CREATION, "Création"),
        (MODIFICATION, "Modification"),
        (SUPPRESSION, "Suppression"),
    ]
    # Actions à surveiller de près (pertes d'argent ou de marchandise possibles)
    SENSIBLES = {ECHEC_CONNEXION, RETRAIT, ANNULATION, PERTE, INVENTAIRE, SUPPRESSION}

    date = models.DateTimeField(auto_now_add=True, db_index=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='actions_journal')
    # Nom conservé même si le compte est supprimé plus tard
    nom_utilisateur = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=20, choices=ACTIONS, db_index=True)
    type_objet = models.CharField("élément", max_length=60, blank=True)
    objet = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True)
    montant = models.IntegerField(null=True, blank=True, help_text="Montant en FCFA concerné, le cas échéant.")
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = "entrée du journal d'audit"
        verbose_name_plural = "journal d'audit"

    def __str__(self):
        return f"{self.date:%d/%m/%Y %H:%M} · {self.nom_utilisateur or 'Système'} · {self.get_action_display()} {self.objet}"

    @property
    def est_sensible(self):
        return self.action in self.SENSIBLES
