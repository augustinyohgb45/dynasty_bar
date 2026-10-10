from django.conf import settings
from django.db import models
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone


class Categorie(models.Model):
    nom = models.CharField(max_length=60, unique=True)
    ordre = models.PositiveSmallIntegerField(default=100, help_text="Ordre d'affichage (plus petit = en premier).")

    class Meta:
        ordering = ['ordre', 'nom']
        verbose_name = "catégorie"

    def __str__(self):
        return self.nom


class ProduitQuerySet(models.QuerySet):
    def avec_stock(self):
        """Ajoute le stock actuel (somme des mouvements) à chaque produit."""
        return self.annotate(stock=Coalesce(Sum('mouvements__quantite'), Value(0)))


class Produit(models.Model):
    code = models.CharField("code", max_length=20, unique=True)
    nom = models.CharField("désignation", max_length=120)
    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name='produits', verbose_name="catégorie")
    prix_achat = models.PositiveIntegerField("prix d'achat (FCFA)", null=True, blank=True)
    prix_vente = models.PositiveIntegerField("prix de vente (FCFA)")
    seuil_alerte = models.PositiveIntegerField(
        "seuil d'alerte", default=0,
        help_text="Alerte quand le stock descend à ce niveau. 0 = pas d'alerte (seule la rupture est signalée).")
    actif = models.BooleanField("en vente", default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    objects = ProduitQuerySet.as_manager()

    class Meta:
        ordering = ['categorie__ordre', 'categorie__nom', 'nom']

    def __str__(self):
        return self.nom

    @property
    def stock_actuel(self):
        """Stock calculé (utilise l'annotation de avec_stock() si elle est présente)."""
        if hasattr(self, 'stock'):
            return self.stock
        return self.mouvements.aggregate(total=Sum('quantite'))['total'] or 0

    def etat(self, stock=None):
        stock = self.stock_actuel if stock is None else stock
        if stock <= 0:
            return 'rupture'
        if self.seuil_alerte and stock <= self.seuil_alerte:
            return 'alerte'
        return 'ok'


class MouvementStock(models.Model):
    ENTREE = 'entree'
    VENTE = 'vente'
    CASSE = 'casse'
    OFFERT = 'offert'
    INVENTAIRE = 'inventaire'
    TYPES = [
        (ENTREE, "Entrée (réception)"),
        (VENTE, "Vente"),
        (CASSE, "Casse"),
        (OFFERT, "Offert"),
        (INVENTAIRE, "Ajustement d'inventaire"),
    ]
    # Mouvements qui font baisser le stock
    TYPES_SORTANTS = {VENTE, CASSE, OFFERT}
    # Mouvements réservés aux administrateurs (pertes et corrections)
    TYPES_RESERVES = {CASSE, OFFERT, INVENTAIRE}

    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name='mouvements')
    type = models.CharField(max_length=12, choices=TYPES)
    quantite = models.IntegerField(help_text="Positif pour une entrée, négatif pour une sortie.")
    prix_unitaire = models.PositiveIntegerField(
        null=True, blank=True, help_text="Prix figé au moment du mouvement (vente ou achat).")
    motif = models.CharField(max_length=255, blank=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='mouvements_stock')
    date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = "mouvement de stock"
        verbose_name_plural = "mouvements de stock"

    def __str__(self):
        return f"{self.get_type_display()} · {self.produit} ({self.quantite:+d})"

    @property
    def montant(self):
        if self.prix_unitaire is None:
            return None
        return abs(self.quantite) * self.prix_unitaire
