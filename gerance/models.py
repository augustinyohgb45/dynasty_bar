from django.conf import settings
from django.db import models
from django.db.models import F, Sum
from django.utils import timezone

from stock.models import MouvementStock, Produit


class Achat(models.Model):
    """Achat de boissons auprès d'un fournisseur : chaque ligne fait entrer du stock."""
    fournisseur = models.CharField(max_length=120)
    reference = models.CharField("n° de facture ou de bon", max_length=60, blank=True)
    date = models.DateTimeField("date de l'achat", default=timezone.now)
    note = models.CharField(max_length=255, blank=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='achats')
    date_saisie = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"Achat {self.fournisseur}{f' · {self.reference}' if self.reference else ''} du {self.date:%d/%m/%Y}"

    @property
    def total(self):
        return self.lignes.aggregate(t=Sum(F('quantite') * F('prix_unitaire')))['t'] or 0


class LigneAchat(models.Model):
    achat = models.ForeignKey(Achat, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name='lignes_achat')
    quantite = models.PositiveIntegerField()
    prix_unitaire = models.PositiveIntegerField("prix d'achat unitaire (FCFA)")
    mouvement = models.OneToOneField(MouvementStock, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='ligne_achat')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.quantite} × {self.produit}"

    @property
    def montant(self):
        return self.quantite * self.prix_unitaire
