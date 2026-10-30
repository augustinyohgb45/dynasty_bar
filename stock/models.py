from django.conf import settings
from django.db import models
from django.db.models import Case, F, IntegerField, OuterRef, Subquery, Sum, Value, When
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


def _somme_mouvements(reference):
    return Subquery(MouvementStock.objects.filter(produit=reference).order_by().values('produit')
                    .annotate(s=Sum('quantite')).values('s'), output_field=IntegerField())


class ProduitQuerySet(models.QuerySet):
    def avec_stock(self):
        """
        Ajoute le stock actuel (somme des mouvements) à chaque produit. Pour un lot, c'est le
        nombre de lots complets possibles avec le stock de la boisson de base.
        """
        propre = Coalesce(_somme_mouvements(OuterRef('pk')), Value(0))
        de_la_base = Coalesce(_somme_mouvements(OuterRef('lot_de')), Value(0)) / F('nb_bouteilles')
        return self.annotate(stock=Case(When(lot_de__isnull=True, then=propre), default=de_la_base,
                                        output_field=IntegerField()))

    def unitaires(self):
        """Boissons stockées à l'unité (hors lots) : achats, mouvements, inventaires, valeur du stock."""
        return self.filter(lot_de__isnull=True)


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
    # Offre par lot (ex. : 3 Portes de Bordeaux pour 75 000 F) : pas de stock propre, chaque lot
    # vendu sort nb_bouteilles bouteilles de la boisson de base.
    lot_de = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='lots',
                               verbose_name="lot de", limit_choices_to={'lot_de__isnull': True},
                               help_text="Laisser vide pour une boisson vendue à l'unité.")
    nb_bouteilles = models.PositiveSmallIntegerField(
        "bouteilles par lot", default=1, help_text="Nombre de bouteilles de la boisson de base dans un lot.")
    date_creation = models.DateTimeField(auto_now_add=True)

    objects = ProduitQuerySet.as_manager()

    class Meta:
        ordering = ['categorie__ordre', 'categorie__nom', 'nom']

    def __str__(self):
        return self.nom

    @property
    def est_lot(self):
        return self.lot_de_id is not None

    @property
    def stock_actuel(self):
        """Stock calculé (utilise l'annotation de avec_stock() si elle est présente)."""
        if hasattr(self, 'stock'):
            return self.stock
        return Produit.objects.avec_stock().get(pk=self.pk).stock

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
