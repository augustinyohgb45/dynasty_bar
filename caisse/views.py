from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from comptes.decorators import gerant_requis
from stock.models import Categorie, Produit

from . import cloture, services
from .models import Cloture, Commande, LigneCommande, Paiement, Table
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
        'sans_table': [c for c in ouvertes if not c.table_id],
        'toutes_occupees': bool(zones) and all(t.commande for _, liste in zones for t in liste),
        'cloture': cloture.cloture_validee(cloture.soiree_courante()),
        'nb_occupees': len(par_table),
        'montant_en_cours': sum(c.reste_du for c in ouvertes),
    }
    return render(request, 'caisse/tables.html', context)


@login_required
@require_POST
def ouvrir(request, table_id=None):
    table = get_object_or_404(Table, pk=table_id, active=True) if table_id else None
    try:
        commande = services.ouvrir_commande(table, request.user, request.POST.get('client', ''),
                                            nature=request.POST.get('nature'), telephone=request.POST.get('telephone', ''))
    except ErreurCaisse as e:
        messages.error(request, str(e))
        return redirect('tables')
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
        'monnaie_rendue': _entier(request.GET.get('rendu'), 0),
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
        services.retirer_produit(ligne, request.user, _entier(request.POST.get('quantite'), 1))
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
        # On reste sur la commande pour proposer d'imprimer le reçu
        messages.success(request, f"Commande {commande.numero} soldée. {texte}")
        return redirect(f"{reverse('commande', args=[commande.pk])}?rendu={monnaie}#addition")
    messages.success(request, f"{texte} Reste à payer : {commande.reste:,} FCFA.".replace(',', ' '))
    return redirect('commande', commande.pk)


@gerant_requis
@require_POST
def annuler(request, commande_id):
    commande = get_object_or_404(Commande, pk=commande_id)
    try:
        services.annuler(commande, request.POST.get('motif', ''), request.user)
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


def _jour_demande(request):
    try:
        return date.fromisoformat(request.GET['jour'])
    except (KeyError, ValueError):
        return cloture.soiree_courante()


@login_required
def ventes(request):
    """Bilan d'une soirée : encaissements par mode, ventes par serveur, articles vendus."""
    jour = _jour_demande(request)
    # Le personnel ne voit que ses propres commandes
    context = cloture.bilan(jour, serveur=None if request.user.is_superuser else request.user)
    context.update({
        'veille': jour - timedelta(days=1),
        'lendemain': jour + timedelta(days=1),
        'est_soiree_actuelle': jour == cloture.soiree_courante(),
        'cloture': cloture.cloture_validee(jour),
    })
    return render(request, 'caisse/ventes.html', context)


@gerant_requis
def cloturer(request):
    """Clôture de la soirée : vérifications, comptage de la caisse, inventaire de fin de service."""
    jour = _jour_demande(request)
    existante = cloture.cloture_validee(jour)
    if existante is not None:
        return redirect('cloture_detail', existante.pk)

    bilan = cloture.bilan(jour)
    produits = cloture.produits_a_inventorier(jour)
    erreurs, saisie = [], {}
    if request.method == 'POST':
        saisie = request.POST
        fond = _entier(request.POST.get('fond_de_caisse'), 0)
        comptes_modes = {}
        for mode, libelle, _ in bilan['encaissements']:
            valeur = request.POST.get(f'compte_{mode}', '').strip()
            if valeur:
                comptes_modes[mode] = _entier(valeur, None)
                if comptes_modes[mode] is None:
                    erreurs.append(f"Montant compté invalide pour {libelle}.")
        comptes_produits = {}
        for produit in produits:
            valeur = request.POST.get(f'stock_{produit.pk}', '').strip()
            if valeur:
                quantite = _entier(valeur, None)
                if quantite is None or quantite < 0:
                    erreurs.append(f"Quantité comptée invalide pour {produit}.")
                else:
                    comptes_produits[produit.pk] = quantite
        if fond < 0:
            erreurs.append("Le fond de caisse ne peut pas être négatif.")
        if not erreurs:
            try:
                resultat = cloture.cloturer(jour, request.user, fond, comptes_modes, comptes_produits,
                                            request.POST.get('note', ''))
            except ErreurCaisse as e:
                erreurs.append(str(e))
            else:
                messages.success(request, f"Soirée du {jour:%d/%m/%Y} clôturée.")
                return redirect('cloture_detail', resultat.pk)

    for produit in produits:
        produit.saisie = saisie.get(f'stock_{produit.pk}', '')
    context = dict(bilan)
    context.update({
        'comptage': [{'cle': cle, 'libelle': libelle, 'montant': montant, 'saisie': saisie.get(f'compte_{cle}', '')}
                     for cle, libelle, montant in bilan['encaissements']],
        'problemes': cloture.verifier(jour),
        'erreurs': erreurs,
        'saisie': saisie,
        'produits': produits,
        'modes_avec_reference': Paiement.MODES_AVEC_REFERENCE,
        'est_soiree_actuelle': jour == cloture.soiree_courante(),
    })
    return render(request, 'caisse/cloturer.html', context)


@gerant_requis
def clotures(request):
    liste = Cloture.objects.select_related('par', 'rouverte_par')
    return render(request, 'caisse/clotures.html', {'page_clotures': Paginator(liste, 30).get_page(request.GET.get('page'))})


@gerant_requis
def cloture_detail(request, cloture_id):
    resultat = get_object_or_404(Cloture.objects.select_related('par', 'rouverte_par'), pk=cloture_id)
    context = cloture.bilan(resultat.soiree)
    context.update({
        'cloture': resultat,
        'comptages': resultat.comptages.all(),
        'inventaire': resultat.inventaire.select_related('produit__categorie'),
        'ecarts_inventaire': [l for l in resultat.inventaire.select_related('produit') if l.ecart],
    })
    return render(request, 'caisse/cloture_detail.html', context)


@gerant_requis
@require_POST
def rouvrir(request, cloture_id):
    resultat = get_object_or_404(Cloture, pk=cloture_id)
    try:
        cloture.rouvrir(resultat, request.user, request.POST.get('motif', ''))
    except ErreurCaisse as e:
        messages.error(request, str(e))
        return redirect('cloture_detail', resultat.pk)
    messages.success(request, f"Soirée du {resultat.soiree:%d/%m/%Y} rouverte : la caisse accepte de nouveau les commandes.")
    return redirect('tables')
