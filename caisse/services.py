"""
Règles de la caisse : ajout et retrait d'articles, encaissement, annulation.

Chaque article servi sort immédiatement du stock (mouvement « Vente » rattaché à la ligne).
Retirer un article ou annuler une commande supprime la sortie correspondante.
Toutes ces actions sont inscrites au journal d'audit.
"""
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from audit.journal import fcfa, journaliser
from audit.models import JournalAudit
from stock.models import MouvementStock, Produit

from .models import Cloture, Commande, LigneCommande, Paiement


class ErreurCaisse(Exception):
    pass


def _objet(commande):
    return f"{commande.emplacement} {commande.numero}"


def ouvrir_commande(table, utilisateur, client='', nature=None, telephone=''):
    """
    Ouvre une commande, ou reprend celle déjà ouverte sur la table.
    Sans table : vente au comptoir, ou commande client (nom du client obligatoire),
    utile notamment quand toutes les tables sont occupées.
    """
    client = (client or '').strip()[:80]
    telephone = (telephone or '').strip()[:20]
    if table is not None:
        nature = Commande.TABLE
    elif nature != Commande.CLIENT:
        nature = Commande.COMPTOIR
    if nature == Commande.CLIENT and not client:
        raise ErreurCaisse("Saisissez le nom du client pour ouvrir une commande client.")
    jour = timezone.localtime(debut_soiree()).date()
    if Cloture.objects.filter(soiree=jour, statut=Cloture.VALIDEE).exists():
        raise ErreurCaisse(f"La soirée du {jour:%d/%m/%Y} est clôturée : aucune nouvelle commande n'est possible. "
                           "L'admin peut la rouvrir si nécessaire.")
    if table is not None:
        existante = Commande.objects.filter(table=table, statut=Commande.OUVERTE).first()
        if existante is not None:
            return existante
    commande = Commande.objects.create(table=table, nature=nature, serveur=utilisateur, client=client,
                                       telephone=telephone)
    details = [f"Type : {commande.get_nature_display()}"]
    if client:
        details.append(f"Client : {client}{f' ({telephone})' if telephone else ''}")
    journaliser(JournalAudit.OUVERTURE, objet=_objet(commande), type_objet="Commande",
                details="\n".join(details), utilisateur=utilisateur)
    return commande


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

    journaliser(JournalAudit.AJOUT, objet=_objet(commande), type_objet="Commande",
                details=f"{quantite} × {produit} à {fcfa(produit.prix_vente)}",
                montant=quantite * produit.prix_vente, utilisateur=utilisateur)

    # Même produit au même prix : on regroupe sur une seule ligne
    ligne = commande.lignes.filter(produit=produit, prix_unitaire=produit.prix_vente).select_related('mouvement').first()
    if ligne is None:
        # Un lot fait sortir ses bouteilles de la boisson de base
        stocke, par_unite = (produit.lot_de, produit.nb_bouteilles) if produit.est_lot else (produit, 1)
        motif = f"Commande {commande.numero} · {commande.emplacement}"
        if produit.est_lot:
            motif += f" · {produit}"
        mouvement = MouvementStock.objects.create(
            produit=stocke, type=MouvementStock.VENTE, quantite=-quantite * par_unite,
            prix_unitaire=produit.prix_vente // par_unite, motif=motif, utilisateur=utilisateur)
        return LigneCommande.objects.create(commande=commande, produit=produit, quantite=quantite,
                                            prix_unitaire=produit.prix_vente, mouvement=mouvement)
    ligne.quantite += quantite
    ligne.save(update_fields=['quantite'])
    _ajuster_sortie(ligne)
    return ligne


def _ajuster_sortie(ligne):
    """Met la sortie de stock d'une ligne en accord avec sa quantité (× bouteilles pour un lot)."""
    if ligne.mouvement is not None:
        ligne.mouvement.quantite = -ligne.quantite * ligne.produit.nb_bouteilles
        ligne.mouvement.save(update_fields=['quantite'])


@transaction.atomic
def retirer_produit(ligne, utilisateur, quantite=1):
    """Retire des articles d'une commande ouverte et les remet en stock."""
    commande = _verrouiller(ligne.commande)
    ligne = LigneCommande.objects.select_related('mouvement', 'produit').get(pk=ligne.pk, commande=commande)
    quantite = min(quantite, ligne.quantite)
    if commande.total - quantite * ligne.prix_unitaire < commande.total_paye:
        raise ErreurCaisse("Impossible : le montant déjà encaissé dépasserait le total de la commande.")
    journaliser(JournalAudit.RETRAIT, objet=_objet(commande), type_objet="Commande",
                details=f"{quantite} × {ligne.produit} retiré(s) et remis en stock "
                        f"(commande servie par {commande.serveur.get_username()})",
                montant=quantite * ligne.prix_unitaire, utilisateur=utilisateur)
    ligne.quantite -= quantite
    if ligne.quantite == 0:
        if ligne.mouvement is not None:
            ligne.mouvement.delete()
        ligne.delete()
        return None
    ligne.save(update_fields=['quantite'])
    _ajuster_sortie(ligne)
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
    details = [f"{paiement.get_mode_display()} : {fcfa(montant)}"]
    if reference:
        details.append(f"Référence : {reference}")
    if monnaie:
        details.append(f"Reçu {fcfa(montant + monnaie)}, monnaie rendue {fcfa(monnaie)}")
    if commande.reste == 0:
        commande.statut = Commande.PAYEE
        commande.date_cloture = timezone.now()
        commande.save(update_fields=['statut', 'date_cloture'])
        details.append(f"Commande soldée (total {fcfa(commande.total)})")
    else:
        details.append(f"Reste à payer : {fcfa(commande.reste)}")
    journaliser(JournalAudit.PAIEMENT, objet=_objet(commande), type_objet="Commande",
                details="\n".join(details), montant=montant, utilisateur=utilisateur)
    return paiement, monnaie, commande


@transaction.atomic
def annuler(commande, motif, utilisateur):
    """Annule une commande non encaissée et remet les articles en stock."""
    commande = _verrouiller(commande)
    if not (motif or '').strip():
        raise ErreurCaisse("Indiquez le motif de l'annulation.")
    if commande.paiements.exists():
        raise ErreurCaisse("Impossible d'annuler une commande déjà partiellement encaissée.")
    articles = [f"{ligne.quantite} × {ligne.produit}" for ligne in commande.lignes.select_related('produit')]
    journaliser(JournalAudit.ANNULATION, objet=_objet(commande), type_objet="Commande",
                details=f"Motif : {motif.strip()}\nServie par {commande.serveur.get_username()}\n"
                        f"Articles remis en stock : {', '.join(articles) or 'aucun'}",
                montant=commande.total, utilisateur=utilisateur)
    MouvementStock.objects.filter(ligne_commande__commande=commande).delete()
    commande.statut = Commande.ANNULEE
    commande.motif_annulation = motif.strip()
    commande.date_cloture = timezone.now()
    commande.save(update_fields=['statut', 'motif_annulation', 'date_cloture'])
    return commande


@transaction.atomic
def abandonner(commande, utilisateur, motif="Commande vide abandonnée"):
    """
    Ferme une commande ouverte par erreur ou laissée sans article. Possible pour tout le
    personnel car rien n'a été servi ni encaissé ; une commande avec des articles doit
    être annulée par l'admin.
    """
    commande = _verrouiller(commande)
    if not commande.est_vide:
        raise ErreurCaisse("Cette commande contient des articles ou un paiement : seul l'admin peut l'annuler.")
    commande.statut = Commande.ANNULEE
    commande.motif_annulation = motif
    commande.date_cloture = timezone.now()
    commande.save(update_fields=['statut', 'motif_annulation', 'date_cloture'])
    journaliser(JournalAudit.ABANDON, objet=_objet(commande), type_objet="Commande",
                details=f"{motif} (ouverte à {timezone.localtime(commande.date_ouverture):%H:%M} "
                        f"par {commande.serveur.get_username()})", utilisateur=utilisateur)
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
