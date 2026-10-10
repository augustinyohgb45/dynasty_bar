"""
Clôture de soirée.

1. Vérifications : plus aucune addition ouverte, soirée pas déjà clôturée.
2. Comptage de la caisse : pour chaque mode de paiement, le montant compté (espèces dans le tiroir,
   relevés MoMo, Orange Money, Moov Money, Wave, terminal de carte) est comparé au montant attendu.
   Pour les espèces, l'attendu comprend le fond de caisse du début de soirée.
3. Inventaire de fin de service : chaque boisson comptée est comparée au stock théorique ; les écarts
   sont corrigés dans le stock par un ajustement d'inventaire.
4. Le bilan est figé et la caisse n'accepte plus de nouvelle commande pour cette soirée, sauf
   réouverture par le gérant (motif obligatoire, inscrite au journal).
"""
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from audit.journal import fcfa, journaliser
from audit.models import JournalAudit
from stock.models import MouvementStock, Produit

from .models import Cloture, ComptageCloture, Commande, InventaireCloture, LigneCommande, Paiement
from .services import ErreurCaisse, bornes_soiree, debut_soiree, encaissements_par_mode


def soiree_courante():
    return timezone.localtime(debut_soiree()).date()


def cloture_validee(jour):
    return Cloture.objects.filter(soiree=jour, statut=Cloture.VALIDEE).select_related('par').first()


def bilan(jour, serveur=None):
    """Chiffres d'une soirée (commandes ouvertes pendant la soirée), éventuellement pour un seul serveur."""
    debut, fin = bornes_soiree(jour)
    commandes = Commande.objects.filter(date_ouverture__gte=debut, date_ouverture__lt=fin)
    if serveur is not None:
        commandes = commandes.filter(serveur=serveur)
    paiements = Paiement.objects.filter(commande__in=commandes)
    payees = commandes.filter(statut=Commande.PAYEE)
    lignes = LigneCommande.objects.filter(commande__in=payees)

    commandes_payees = list(payees.avec_totaux().select_related('table', 'serveur').order_by('-date_cloture'))
    par_serveur = {}
    for c in commandes_payees:
        ligne = par_serveur.setdefault(c.serveur_id, {'nom': c.serveur.username, 'nb': 0, 'total': 0})
        ligne['nb'] += 1
        ligne['total'] += c.montant_total

    pertes = (MouvementStock.objects.filter(type__in=[MouvementStock.CASSE, MouvementStock.OFFERT],
                                            date__gte=debut, date__lt=fin).select_related('produit', 'utilisateur'))
    return {
        'jour': jour,
        'debut': debut,
        'fin': fin,
        'encaissements': encaissements_par_mode(paiements),
        'total_encaisse': paiements.aggregate(t=Sum('montant'))['t'] or 0,
        'chiffre_affaires': lignes.aggregate(t=Sum(F('quantite') * F('prix_unitaire')))['t'] or 0,
        'nb_payees': len(commandes_payees),
        'commandes_payees': commandes_payees,
        'par_serveur': sorted(par_serveur.values(), key=lambda s: -s['total']),
        'articles': (lignes.values('produit__nom')
                     .annotate(nb=Sum('quantite'), total=Sum(F('quantite') * F('prix_unitaire'))).order_by('-total')),
        'ouvertes': commandes.filter(statut=Commande.OUVERTE).avec_totaux().select_related('table', 'serveur'),
        'annulees': commandes.filter(statut=Commande.ANNULEE).select_related('table', 'serveur'),
        'pertes': pertes,
        'retraits': JournalAudit.objects.filter(action=JournalAudit.RETRAIT, date__gte=debut, date__lt=fin),
    }


def produits_a_inventorier(jour):
    """Boissons en stock ou vendues pendant la soirée, avec leur stock théorique actuel."""
    debut, fin = bornes_soiree(jour)
    vendus = set(LigneCommande.objects.filter(commande__date_ouverture__gte=debut, commande__date_ouverture__lt=fin)
                 .values_list('produit_id', flat=True))
    produits = Produit.objects.avec_stock().select_related('categorie')
    return [p for p in produits if p.stock != 0 or p.pk in vendus]


def verifier(jour):
    """Liste des raisons empêchant de clôturer (vide si la clôture est possible)."""
    problemes = []
    if cloture_validee(jour) is not None:
        problemes.append("Cette soirée est déjà clôturée.")
    ouvertes = Commande.objects.filter(statut=Commande.OUVERTE).select_related('table')
    if ouvertes:
        liste = ", ".join(f"{c.emplacement} {c.numero}" for c in ouvertes)
        problemes.append(f"Des additions sont encore ouvertes : {liste}. Encaissez-les ou annulez-les avant de clôturer.")
    if jour > soiree_courante():
        problemes.append("Impossible de clôturer une soirée qui n'a pas commencé.")
    return problemes


@transaction.atomic
def cloturer(jour, utilisateur, fond_de_caisse, comptes_par_mode, comptes_par_produit, note=''):
    """
    Clôture la soirée. comptes_par_mode : {mode: montant compté} ; comptes_par_produit :
    {produit_id: quantité comptée} pour les seules boissons effectivement comptées.
    """
    problemes = verifier(jour)
    if problemes:
        raise ErreurCaisse(" ".join(problemes))
    donnees = bilan(jour)
    debut, fin = donnees['debut'], donnees['fin']
    cloture = Cloture.objects.create(
        soiree=jour, debut=debut, fin=fin, par=utilisateur, fond_de_caisse=fond_de_caisse, note=note.strip(),
        chiffre_affaires=donnees['chiffre_affaires'], total_encaisse=donnees['total_encaisse'],
        nb_commandes=donnees['nb_payees'], nb_annulees=len(donnees['annulees']))

    # Comptage de la caisse
    details, ecart_caisse = [], 0
    for mode, libelle, encaisse in donnees['encaissements']:
        attendu = encaisse + (fond_de_caisse if mode == Paiement.ESPECES else 0)
        compte = comptes_par_mode.get(mode)
        if compte is None:
            if attendu:
                raise ErreurCaisse(f"Indiquez le montant compté pour {libelle}.")
            continue
        comptage = ComptageCloture.objects.create(cloture=cloture, mode=mode, attendu=attendu, compte=compte)
        ecart_caisse += comptage.ecart
        if comptage.ecart:
            details.append(f"Caisse {libelle} : attendu {fcfa(attendu)}, compté {fcfa(compte)} "
                           f"(écart {comptage.ecart:+,} FCFA)".replace(',', ' '))

    # Inventaire de fin de service
    ecart_stock = 0
    produits = {p.pk: p for p in Produit.objects.avec_stock().filter(pk__in=comptes_par_produit)}
    for produit_id, compte in comptes_par_produit.items():
        produit = produits[produit_id]
        prix = produit.prix_achat if produit.prix_achat is not None else produit.prix_vente
        ligne = InventaireCloture(cloture=cloture, produit=produit, theorique=produit.stock, compte=compte,
                                  prix_unitaire=prix)
        if ligne.ecart:
            ligne.mouvement = MouvementStock.objects.create(
                produit=produit, type=MouvementStock.INVENTAIRE, quantite=ligne.ecart, prix_unitaire=prix,
                motif=f"Inventaire de clôture du {jour:%d/%m/%Y}", utilisateur=utilisateur)
            ecart_stock += ligne.valeur_ecart
            details.append(f"Stock {produit} : théorique {ligne.theorique}, compté {compte} ({ligne.ecart:+d})")
        ligne.save()

    cloture.ecart_caisse = ecart_caisse
    cloture.ecart_stock = ecart_stock
    cloture.save(update_fields=['ecart_caisse', 'ecart_stock'])

    resume = [f"Chiffre d'affaires : {fcfa(cloture.chiffre_affaires)} ({cloture.nb_commandes} commandes)",
              f"Encaissé : {fcfa(cloture.total_encaisse)} · fond de caisse : {fcfa(fond_de_caisse)}",
              f"Écart de caisse : {ecart_caisse:+,} FCFA".replace(',', ' '),
              f"Écart de stock : {ecart_stock:+,} FCFA ({len(comptes_par_produit)} boissons comptées)".replace(',', ' ')]
    journaliser(JournalAudit.CLOTURE, objet=f"Soirée du {jour:%d/%m/%Y}", type_objet="Soirée",
                details="\n".join(resume + details), montant=cloture.chiffre_affaires, utilisateur=utilisateur)
    return cloture


@transaction.atomic
def rouvrir(cloture, utilisateur, motif):
    """Rouvre une soirée clôturée. Les ajustements d'inventaire déjà faits sont conservés."""
    if not (motif or '').strip():
        raise ErreurCaisse("Indiquez le motif de la réouverture.")
    cloture = Cloture.objects.select_for_update().get(pk=cloture.pk)
    if not cloture.est_validee:
        raise ErreurCaisse("Cette clôture a déjà été annulée par une réouverture.")
    cloture.statut = Cloture.ROUVERTE
    cloture.motif_reouverture = motif.strip()
    cloture.rouverte_par = utilisateur
    cloture.date_reouverture = timezone.now()
    cloture.save(update_fields=['statut', 'motif_reouverture', 'rouverte_par', 'date_reouverture'])
    journaliser(JournalAudit.REOUVERTURE, objet=f"Soirée du {cloture.soiree:%d/%m/%Y}", type_objet="Soirée",
                details=f"Motif : {cloture.motif_reouverture}\nClôture initiale par {cloture.par.get_username()} "
                        f"le {timezone.localtime(cloture.date):%d/%m/%Y à %H:%M}", utilisateur=utilisateur)
    return cloture
