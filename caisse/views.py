from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from comptes.decorators import gerant_requis
from stock.models import Categorie, Produit

from . import services
from .models import Commande, LigneCommande, Paiement, Table
from .services import ErreurCaisse


def _entier(valeur, defaut=0):
    try:
        return int(str(valeur).replace(' ', '').replace(' ', ''))
    except (TypeError, ValueError):
        return defaut


@login_required
def tables(request):
    """Plan des tables avec leur commande en cours, et ventes au comptoir."""
    ouvertes = list(Commande.objects.filter(statut=Commande.OUVERTE).avec_totaux()
                    .select_related('table', 'serveur').order_by('date_ouverture'))
    for c in ouvertes:
        c.reste_du = c.montant_total - c.montant_paye
    par_table = {c.table_id: c for c in ouvertes if c.table_id}
    zones = []
    for cle, libelle in Table.ZONES:
        liste = [t for t in Table.objects.filter(active=True, zone=cle)]
        for table in liste:
            table.commande = par_table.get(table.pk)
        if liste:
            zones.append((libelle, liste))
    context = {
        'zones': zones,
        'comptoir': [c for c in ouvertes if not c.table_id],
        'nb_occupees': len(par_table),
        'montant_en_cours': sum(c.reste_du for c in ouvertes),
    }
    return render(request, 'caisse/tables.html', context)


@login_required
@require_POST
def ouvrir(request, table_id=None):
    table = get_object_or_404(Table, pk=table_id, active=True) if table_id else None
    if table is not None:
        existante = Commande.objects.filter(table=table, statut=Commande.OUVERTE).first()
        if existante is not None:
            return redirect('commande', existante.pk)
    commande = Commande.objects.create(table=table, serveur=request.user,
                                       client=request.POST.get('client', '').strip()[:80])
    return redirect('commande', commande.pk)


@login_required
def commande(request, commande_id):
    commande = get_object_or_404(Commande.objects.select_related('table', 'serveur'), pk=commande_id)
    produits = list(Produit.objects.filter(actif=True).avec_stock().select_related('categorie'))
    context = {
        'commande': commande,
        'lignes': commande.lignes.select_related('produit'),
        'paiements': commande.paiements.select_related('recu_par'),
        'total': commande.total,
        'total_paye': commande.total_paye,
        'reste': commande.reste,
        'produits': produits,
        'categories': Categorie.objects.filter(produits__actif=True).distinct(),
        'modes': Paiement.MODES,
        'modes_avec_reference': sorted(Paiement.MODES_AVEC_REFERENCE),
        'billets': [5000, 10000, 20000, 50000],
    }
    return render(request, 'caisse/commande.html', context)


@login_required
@require_POST
def ajouter(request, commande_id):
    commande = get_object_or_404(Commande, pk=commande_id)
    produit = get_object_or_404(Produit, pk=request.POST.get('produit'))
    try:
        services.ajouter_produit(commande, produit, _entier(request.POST.get('quantite'), 1), request.user)
    except ErreurCaisse as e:
        messages.error(request, str(e))
    return redirect('commande', commande.pk)


@gerant_requis
@require_POST
def retirer(request, ligne_id):
    ligne = get_object_or_404(LigneCommande.objects.select_related('commande'), pk=ligne_id)
    try:
        services.retirer_produit(ligne, _entier(request.POST.get('quantite'), 1))
    except ErreurCaisse as e:
        messages.error(request, str(e))
    return redirect('commande', ligne.commande_id)


@login_required
@require_POST
def payer(request, commande_id):
    commande = get_object_or_404(Commande, pk=commande_id)
    try:
        paiement, monnaie, commande = services.encaisser(
            commande, request.POST.get('mode', ''), _entier(request.POST.get('montant')), request.user,
            request.POST.get('reference', ''))
    except ErreurCaisse as e:
        messages.error(request, str(e))
        return redirect('commande', commande.pk)

    texte = f"{paiement.get_mode_display()} : {paiement.montant:,} FCFA encaissés.".replace(',', ' ')
    if monnaie:
        texte += f" Monnaie à rendre : {monnaie:,} FCFA.".replace(',', ' ')
    if commande.statut == Commande.PAYEE:
        messages.success(request, f"Commande {commande.numero} soldée. {texte}")
        return redirect('tables')
    messages.success(request, f"{texte} Reste à payer : {commande.reste:,} FCFA.".replace(',', ' '))
    return redirect('commande', commande.pk)


@gerant_requis
@require_POST
def annuler(request, commande_id):
    commande = get_object_or_404(Commande, pk=commande_id)
    try:
        services.annuler(commande, request.POST.get('motif', ''))
    except ErreurCaisse as e:
        messages.error(request, str(e))
        return redirect('commande', commande.pk)
    messages.success(request, f"Commande {commande.numero} annulée, articles remis en stock.")
    return redirect('tables')


@login_required
def ticket(request, commande_id):
    commande = get_object_or_404(Commande.objects.select_related('table', 'serveur'), pk=commande_id)
    context = {
        'commande': commande,
        'lignes': commande.lignes.select_related('produit'),
        'paiements': commande.paiements.all(),
        'total': commande.total,
        'total_paye': commande.total_paye,
        'reste': commande.reste,
        'maintenant': timezone.now(),
    }
    return render(request, 'caisse/ticket.html', context)


@login_required
def ventes(request):
    """Bilan d'une soirée : encaissements par mode, ventes par serveur, articles vendus."""
    debut_actuelle = services.debut_soiree()
    try:
        jour = date.fromisoformat(request.GET['jour'])
    except (KeyError, ValueError):
        jour = timezone.localtime(debut_actuelle).date()
    debut, fin = services.bornes_soiree(jour)

    commandes = Commande.objects.filter(date_ouverture__gte=debut, date_ouverture__lt=fin)
    paiements = Paiement.objects.filter(commande__in=commandes)
    if not request.user.is_superuser:
        # Le personnel ne voit que ses propres commandes
        commandes = commandes.filter(serveur=request.user)
        paiements = paiements.filter(commande__serveur=request.user)

    payees = commandes.filter(statut=Commande.PAYEE)
    lignes_vendues = LigneCommande.objects.filter(commande__in=payees)
    commandes_payees = list(payees.avec_totaux().select_related('table', 'serveur').order_by('-date_cloture'))
    par_serveur = {}
    for c in commandes_payees:
        ligne = par_serveur.setdefault(c.serveur_id, {'nom': c.serveur.username, 'nb': 0, 'total': 0})
        ligne['nb'] += 1
        ligne['total'] += c.montant_total
    context = {
        'jour': jour,
        'veille': date.fromordinal(jour.toordinal() - 1),
        'lendemain': date.fromordinal(jour.toordinal() + 1),
        'est_soiree_actuelle': debut == debut_actuelle,
        'debut': debut,
        'fin': fin,
        'encaissements': services.encaissements_par_mode(paiements),
        'total_encaisse': paiements.aggregate(t=Sum('montant'))['t'] or 0,
        'chiffre_affaires': lignes_vendues.aggregate(t=Sum(F('quantite') * F('prix_unitaire')))['t'] or 0,
        'nb_payees': payees.count(),
        'ouvertes': commandes.filter(statut=Commande.OUVERTE).avec_totaux().select_related('table', 'serveur'),
        'annulees': commandes.filter(statut=Commande.ANNULEE).select_related('table', 'serveur'),
        'articles': (lignes_vendues.values('produit__nom')
                     .annotate(nb=Sum('quantite'), total=Sum(F('quantite') * F('prix_unitaire')))
                     .order_by('-total')),
        'commandes_payees': commandes_payees,
        'par_serveur': sorted(par_serveur.values(), key=lambda s: -s['total']),
    }
    return render(request, 'caisse/ventes.html', context)
