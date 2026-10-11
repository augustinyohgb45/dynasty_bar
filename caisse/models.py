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

    TABLE = 'table'
    COMPTOIR = 'comptoir'
    CLIENT = 'client'
    NATURES = [(TABLE, "Table"), (COMPTOIR, "Comptoir"), (CLIENT, "Commande client")]

    nature = models.CharField("type de commande", max_length=10, choices=NATURES, default=COMPTOIR)
    table = models.ForeignKey(Table, on_delete=models.PROTECT, null=True, blank=True, related_name='commandes',
                              help_text="Uniquement pour une commande à table.")
    client = models.CharField("client", max_length=80, blank=True)
    telephone = models.CharField("téléphone du client", max_length=20, blank=True)
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
        if self.table_id:
            return str(self.table)
        if self.nature == self.CLIENT:
            return f"Client {self.client}" if self.client else "Commande client"
        return "Comptoir"

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


class Cloture(models.Model):
    """Clôture d'une soirée : comptage de la caisse, inventaire de fin de service et bilan figé."""
    VALIDEE = 'validee'
    ROUVERTE = 'rouverte'
    STATUTS = [(VALIDEE, "Clôturée"), (ROUVERTE, "Rouverte")]

    soiree = models.DateField("soirée du")
    debut = models.DateTimeField()
    fin = models.DateTimeField()
    statut = models.CharField(max_length=10, choices=STATUTS, default=VALIDEE)
    date = models.DateTimeField("clôturée le", default=timezone.now)
    par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='clotures')
    fond_de_caisse = models.PositiveIntegerField("fond de caisse (FCFA)", default=0,
                                                 help_text="Espèces présentes dans la caisse en début de soirée.")
    note = models.TextField(blank=True)
    # Bilan figé au moment de la clôture
    chiffre_affaires = models.IntegerField(default=0)
    total_encaisse = models.IntegerField(default=0)
    nb_commandes = models.PositiveIntegerField(default=0)
    nb_annulees = models.PositiveIntegerField(default=0)
    ecart_caisse = models.IntegerField(default=0, help_text="Total compté − total attendu, tous modes confondus.")
    ecart_stock = models.IntegerField(default=0, help_text="Valeur des écarts d'inventaire (prix d'achat, sinon prix de vente).")
    # Réouverture éventuelle par le gérant
    motif_reouverture = models.CharField(max_length=255, blank=True)
    rouverte_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='reouvertures')
    date_reouverture = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-soiree', '-date']
        verbose_name = "clôture de soirée"
        verbose_name_plural = "clôtures de soirée"
        constraints = [
            models.UniqueConstraint(fields=['soiree'], condition=models.Q(statut='validee'),
                                    name='une_cloture_validee_par_soiree'),
        ]

    def __str__(self):
        return f"Clôture de la soirée du {self.soiree:%d/%m/%Y}"

    @property
    def est_validee(self):
        return self.statut == self.VALIDEE


class ComptageCloture(models.Model):
    cloture = models.ForeignKey(Cloture, on_delete=models.CASCADE, related_name='comptages')
    mode = models.CharField(max_length=15, choices=Paiement.MODES)
    attendu = models.IntegerField()
    compte = models.IntegerField()

    class Meta:
        ordering = ['id']

    @property
    def ecart(self):
        return self.compte - self.attendu


class InventaireCloture(models.Model):
    cloture = models.ForeignKey(Cloture, on_delete=models.CASCADE, related_name='inventaire')
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name='+')
    theorique = models.IntegerField()
    compte = models.IntegerField()
    prix_unitaire = models.PositiveIntegerField(help_text="Prix servant à valoriser l'écart.")
    mouvement = models.OneToOneField(MouvementStock, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['id']

    @property
    def ecart(self):
        return self.compte - self.theorique

    @property
    def valeur_ecart(self):
        return self.ecart * self.prix_unitaire
