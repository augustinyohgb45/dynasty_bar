from django.conf import settings
from django.db import models
from django.db.models import F, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from stock.models import MouvementStock, Produit


class Table(models.Model):
    SALLE = 'salle'
    VIP = 'vip'
    TERRASSE = 'terrasse'
    ZONES = [(SALLE, "Salle"), (VIP, "Carré VIP"), (TERRASSE, "Terrasse")]

    nom = models.CharField(max_length=40, unique=True)
    zone = models.CharField(max_length=10, choices=ZONES, default=SALLE)
    ordre = models.PositiveSmallIntegerField(default=100, help_text="Ordre d'affichage dans la zone.")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['zone', 'ordre', 'nom']

    def __str__(self):
        return self.nom


class CommandeQuerySet(models.QuerySet):
    def avec_totaux(self):
        """Ajoute montant_total et montant_paye (sous-requêtes, sans double comptage)."""
        lignes = (LigneCommande.objects.filter(commande=OuterRef('pk')).order_by().values('commande')
                  .annotate(t=Sum(F('quantite') * F('prix_unitaire'))).values('t'))
        paiements = (Paiement.objects.filter(commande=OuterRef('pk')).order_by().values('commande')
                     .annotate(t=Sum('montant')).values('t'))
        return self.annotate(
            montant_total=Coalesce(Subquery(lignes, output_field=IntegerField()), Value(0)),
            montant_paye=Coalesce(Subquery(paiements, output_field=IntegerField()), Value(0)),
        )


class Commande(models.Model):
    OUVERTE = 'ouverte'
    PAYEE = 'payee'
    ANNULEE = 'annulee'
    STATUTS = [(OUVERTE, "En cours"), (PAYEE, "Payée"), (ANNULEE, "Annulée")]

    table = models.ForeignKey(Table, on_delete=models.PROTECT, null=True, blank=True, related_name='commandes',
                              help_text="Vide pour une vente au comptoir.")
    client = models.CharField("client", max_length=80, blank=True)
    serveur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='commandes')
    statut = models.CharField(max_length=10, choices=STATUTS, default=OUVERTE)
    date_ouverture = models.DateTimeField(default=timezone.now)
    date_cloture = models.DateTimeField(null=True, blank=True)
    motif_annulation = models.CharField(max_length=255, blank=True)

    objects = CommandeQuerySet.as_manager()

    class Meta:
        ordering = ['-date_ouverture']

    def __str__(self):
        return f"Commande {self.numero} · {self.emplacement}"

    @property
    def numero(self):
        return f"#{self.pk:05d}" if self.pk else "#—"

    @property
    def emplacement(self):
        return str(self.table) if self.table_id else "Comptoir"

    @property
    def est_ouverte(self):
        return self.statut == self.OUVERTE

    @property
    def total(self):
        return self.lignes.aggregate(total=Sum(F('quantite') * F('prix_unitaire')))['total'] or 0

    @property
    def total_paye(self):
        return self.paiements.aggregate(total=Sum('montant'))['total'] or 0

    @property
    def reste(self):
        return max(self.total - self.total_paye, 0)


class LigneCommande(models.Model):
    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name='lignes_commande')
    quantite = models.PositiveIntegerField()
    prix_unitaire = models.PositiveIntegerField(help_text="Prix de vente figé au moment de la commande.")
    # Sortie de stock correspondante (supprimée si la ligne est retirée ou la commande annulée)
    mouvement = models.OneToOneField(MouvementStock, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='ligne_commande')

    class Meta:
        ordering = ['id']
        verbose_name = "ligne de commande"
        verbose_name_plural = "lignes de commande"

    def __str__(self):
        return f"{self.quantite} × {self.produit}"

    @property
    def montant(self):
        return self.quantite * self.prix_unitaire


class Paiement(models.Model):
    ESPECES = 'especes'
    MTN_MOMO = 'mtn_momo'
    ORANGE_MONEY = 'orange_money'
    MOOV_MONEY = 'moov_money'
    WAVE = 'wave'
    CARTE = 'carte'
    MODES = [
        (ESPECES, "Espèces"),
        (MTN_MOMO, "MTN MoMo"),
        (ORANGE_MONEY, "Orange Money"),
        (MOOV_MONEY, "Moov Money"),
        (WAVE, "Wave"),
        (CARTE, "Carte bancaire"),
    ]
    # Modes pour lesquels la référence de transaction est demandée
    MODES_AVEC_REFERENCE = {MTN_MOMO, ORANGE_MONEY, MOOV_MONEY, WAVE, CARTE}

    commande = models.ForeignKey(Commande, on_delete=models.PROTECT, related_name='paiements')
    mode = models.CharField(max_length=15, choices=MODES)
    montant = models.PositiveIntegerField()
    reference = models.CharField("référence de transaction", max_length=60, blank=True)
    recu_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='paiements_recus')
    date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.get_mode_display()} {self.montant} FCFA · {self.commande.numero}"
