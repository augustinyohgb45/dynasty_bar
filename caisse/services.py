"""
Règles de la caisse : ajout et retrait d'articles, encaissement, annulation.

Chaque article servi sort immédiatement du stock (mouvement « Vente » rattaché à la ligne).
Retirer un article ou annuler une commande supprime la sortie correspondante.
"""
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from stock.models import MouvementStock, Produit

from .models import Commande, LigneCommande, Paiement


class ErreurCaisse(Exception):
    pass


def _verrouiller(commande):
    """Recharge la commande en la verrouillant (deux serveurs sur la même table)."""
    commande = Commande.objects.select_for_update().get(pk=commande.pk)
    if not commande.est_ouverte:
        raise ErreurCaisse(f"La commande {commande.numero} est déjà {commande.get_statut_display().lower()}.")
    return commande


@transaction.atomic
def ajouter_produit(commande, produit, quantite, utilisateur):
    if quantite < 1:
        raise ErreurCaisse("La quantité doit être d'au moins 1.")
    commande = _verrouiller(commande)
    produit = Produit.objects.select_for_update().get(pk=produit.pk)
    if not produit.actif:
        raise ErreurCaisse(f"{produit} n'est plus en vente.")
    stock = Produit.objects.avec_stock().get(pk=produit.pk).stock
    if stock < quantite:
        raise ErreurCaisse(f"Stock insuffisant : il reste {max(stock, 0)} × {produit}.")

    # Même produit au même prix : on regroupe sur une seule ligne
    ligne = commande.lignes.filter(produit=produit, prix_unitaire=produit.prix_vente).select_related('mouvement').first()
    if ligne is None:
        mouvement = MouvementStock.objects.create(
            produit=produit, type=MouvementStock.VENTE, quantite=-quantite, prix_unitaire=produit.prix_vente,
            motif=f"Commande {commande.numero} · {commande.emplacement}", utilisateur=utilisateur)
        return LigneCommande.objects.create(commande=commande, produit=produit, quantite=quantite,
                                            prix_unitaire=produit.prix_vente, mouvement=mouvement)
    ligne.quantite += quantite
    ligne.save(update_fields=['quantite'])
    if ligne.mouvement is not None:
        ligne.mouvement.quantite = -ligne.quantite
        ligne.mouvement.save(update_fields=['quantite'])
    return ligne


@transaction.atomic
def retirer_produit(ligne, quantite=1):
    """Retire des articles d'une commande ouverte et les remet en stock."""
    commande = _verrouiller(ligne.commande)
    ligne = LigneCommande.objects.select_related('mouvement').get(pk=ligne.pk, commande=commande)
    quantite = min(quantite, ligne.quantite)
    if commande.total - quantite * ligne.prix_unitaire < commande.total_paye:
        raise ErreurCaisse("Impossible : le montant déjà encaissé dépasserait le total de la commande.")
    ligne.quantite -= quantite
    if ligne.quantite == 0:
        if ligne.mouvement is not None:
            ligne.mouvement.delete()
        ligne.delete()
        return None
    ligne.save(update_fields=['quantite'])
    if ligne.mouvement is not None:
        ligne.mouvement.quantite = -ligne.quantite
        ligne.mouvement.save(update_fields=['quantite'])
    return ligne


@transaction.atomic
def encaisser(commande, mode, montant, utilisateur, reference=''):
    """
    Enregistre un paiement. En espèces, un montant supérieur au reste est accepté
    et la monnaie à rendre est retournée. Retourne (paiement, monnaie, commande).
    """
    commande = _verrouiller(commande)
    reste = commande.reste
    if commande.total == 0:
        raise ErreurCaisse("La commande est vide.")
    if montant < 1:
        raise ErreurCaisse("Le montant doit être supérieur à zéro.")
    if mode not in dict(Paiement.MODES):
        raise ErreurCaisse("Mode de paiement inconnu.")
    reference = (reference or '').strip()
    if mode in Paiement.MODES_AVEC_REFERENCE and not reference:
        raise ErreurCaisse("Saisissez la référence de la transaction.")

    monnaie = 0
    if montant > reste:
        if mode != Paiement.ESPECES:
            raise ErreurCaisse(f"Le montant dépasse le reste à payer ({reste} FCFA).")
        monnaie = montant - reste
        montant = reste

    paiement = Paiement.objects.create(commande=commande, mode=mode, montant=montant,
                                       reference=reference, recu_par=utilisateur)
    if commande.reste == 0:
        commande.statut = Commande.PAYEE
        commande.date_cloture = timezone.now()
        commande.save(update_fields=['statut', 'date_cloture'])
    return paiement, monnaie, commande


@transaction.atomic
def annuler(commande, motif):
    """Annule une commande non encaissée et remet les articles en stock."""
    commande = _verrouiller(commande)
    if not (motif or '').strip():
        raise ErreurCaisse("Indiquez le motif de l'annulation.")
    if commande.paiements.exists():
        raise ErreurCaisse("Impossible d'annuler une commande déjà partiellement encaissée.")
    MouvementStock.objects.filter(ligne_commande__commande=commande).delete()
    commande.statut = Commande.ANNULEE
    commande.motif_annulation = motif.strip()
    commande.date_cloture = timezone.now()
    commande.save(update_fields=['statut', 'motif_annulation', 'date_cloture'])
    return commande


# ---------- Soirées ----------

def debut_soiree(moment=None):
    """
    Une soirée va de HEURE_DEBUT_SOIREE (12 h par défaut) au même horaire le lendemain,
    pour que les ventes après minuit restent rattachées à la bonne soirée.
    """
    moment = timezone.localtime(moment or timezone.now())
    heure = getattr(settings, 'HEURE_DEBUT_SOIREE', 12)
    jour = moment.date() if moment.hour >= heure else moment.date() - timedelta(days=1)
    return timezone.make_aware(datetime.combine(jour, time(hour=heure)))


def bornes_soiree(jour):
    """Début et fin de la soirée commencée le jour donné."""
    heure = getattr(settings, 'HEURE_DEBUT_SOIREE', 12)
    debut = timezone.make_aware(datetime.combine(jour, time(hour=heure)))
    return debut, debut + timedelta(days=1)


def encaissements_par_mode(paiements):
    totaux = dict(paiements.order_by().values_list('mode').annotate(total=Sum('montant')))
    return [(cle, libelle, totaux.get(cle, 0)) for cle, libelle in Paiement.MODES]
