from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from audit.models import JournalAudit
from caisse.models import Commande, LigneCommande, Paiement
from caisse.cloture import cloture_validee, soiree_courante
from caisse.services import debut_soiree, encaissements_par_mode
from comptes.decorators import gerant_requis
from stock.models import MouvementStock, Produit

from .forms import AchatForm, LignesAchatFormSet
from .models import Achat
from .services import enregistrer_achat

PERIODES = [
    ('soiree', "Soirée en cours"),
    ('7j', "7 derniers jours"),
    ('mois', "Ce mois-ci"),
    ('30j', "30 derniers jours"),
]
NOMS_JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def _bornes(periode):
    maintenant = timezone.now()
    if periode == 'soiree':
        return debut_soiree(), maintenant
    if periode == 'mois':
        local = timezone.localtime()
        return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0), maintenant
    jours = 30 if periode == '30j' else 7
    debut = timezone.localtime() - timedelta(days=jours - 1)
    return debut.replace(hour=0, minute=0, second=0, microsecond=0), maintenant


def _pourcentages(lignes, cle='total'):
    maximum = max((l[cle] for l in lignes), default=0) or 1
    for ligne in lignes:
        ligne['largeur'] = round(100 * ligne[cle] / maximum)
    return lignes


@gerant_requis
def tableau_de_bord(request):
    periode = request.GET.get('periode') if request.GET.get('periode') in dict(PERIODES) else 'soiree'
    debut, fin = _bornes(periode)

    # Ventes : commandes soldées pendant la période
    payees = Commande.objects.filter(statut=Commande.PAYEE, date_cloture__gte=debut, date_cloture__lte=fin)
    lignes = list(LigneCommande.objects.filter(commande__in=payees)
                  .select_related('produit__categorie', 'commande'))
    chiffre_affaires = sum(l.montant for l in lignes)
    cout = sum(l.quantite * l.produit.prix_achat for l in lignes if l.produit.prix_achat is not None)
    ca_avec_cout = sum(l.montant for l in lignes if l.produit.prix_achat is not None)

    vendues, par_categorie, par_jour = {}, defaultdict(int), defaultdict(int)
    for l in lignes:
        v = vendues.setdefault(l.produit_id, {'nom': l.produit.nom, 'categorie': l.produit.categorie.nom,
                                               'quantite': 0, 'total': 0})
        v['quantite'] += l.quantite
        v['total'] += l.montant
        par_categorie[l.produit.categorie.nom] += l.montant
        par_jour[timezone.localtime(l.commande.date_cloture).date()] += l.montant

    jours = []
    if periode != 'soiree':
        jour = timezone.localtime(debut).date()
        while jour <= timezone.localdate():
            jours.append({'libelle': f"{NOMS_JOURS[jour.weekday()]} {jour.day}", 'total': par_jour.get(jour, 0)})
            jour += timedelta(days=1)

    # Stock restant
    produits = list(Produit.objects.filter(actif=True).avec_stock().select_related('categorie'))
    restants_categorie = defaultdict(lambda: {'quantite': 0, 'valeur': 0})
    for p in produits:
        p.etat_stock = p.etat(p.stock)
        r = restants_categorie[p.categorie.nom]
        r['quantite'] += max(p.stock, 0)
        r['valeur'] += max(p.stock, 0) * p.prix_vente

    # Pertes (casses et offerts) de la période
    pertes = (MouvementStock.objects.filter(type__in=[MouvementStock.CASSE, MouvementStock.OFFERT],
                                            date__gte=debut, date__lte=fin).select_related('produit', 'utilisateur'))
    ouvertes = Commande.objects.filter(statut=Commande.OUVERTE).avec_totaux()
    paiements = Paiement.objects.filter(date__gte=debut, date__lte=fin)

    context = {
        'periodes': PERIODES,
        'periode': periode,
        'debut': debut,
        'chiffre_affaires': chiffre_affaires,
        'marge': ca_avec_cout - cout,
        'marge_complete': ca_avec_cout == chiffre_affaires,
        'nb_commandes': payees.count(),
        'nb_articles': sum(l.quantite for l in lignes),
        'panier_moyen': chiffre_affaires // payees.count() if payees.exists() else 0,
        'encaissements': encaissements_par_mode(paiements),
        'total_encaisse': paiements.aggregate(t=Sum('montant'))['t'] or 0,
        'total_achats': sum(a.total for a in Achat.objects.filter(date__gte=debut, date__lte=fin)),
        'vendues': sorted(vendues.values(), key=lambda v: -v['total']),
        'par_categorie': _pourcentages(sorted(({'nom': k, 'total': v} for k, v in par_categorie.items()),
                                              key=lambda c: -c['total'])),
        'jours': _pourcentages(jours),
        'valeur_stock': sum(max(p.stock, 0) * p.prix_vente for p in produits),
        'nb_bouteilles': sum(max(p.stock, 0) for p in produits),
        'ruptures': [p for p in produits if p.etat_stock == 'rupture'],
        'alertes': [p for p in produits if p.etat_stock == 'alerte'],
        'nb_a_commander': sum(1 for p in produits if p.etat_stock != 'ok'),
        'restants': [p for p in produits if p.stock > 0],
        'restants_categorie': sorted(restants_categorie.items(), key=lambda r: -r[1]['valeur']),
        'pertes': pertes,
        'valeur_pertes': sum(abs(m.quantite) * (m.produit.prix_achat or 0) for m in pertes),
        'nb_ouvertes': ouvertes.count(),
        'montant_ouvert': sum(c.montant_total - c.montant_paye for c in ouvertes),
        'derniers_achats': Achat.objects.select_related('utilisateur')[:5],
        'activites': JournalAudit.objects.all()[:8],
        'cloture_soiree': cloture_validee(soiree_courante()),
    }
    return render(request, 'gerance/tableau_de_bord.html', context)


@gerant_requis
def achats(request):
    liste = Achat.objects.select_related('utilisateur').prefetch_related('lignes')
    return render(request, 'gerance/achats.html', {'page_achats': Paginator(liste, 25).get_page(request.GET.get('page'))})


@gerant_requis
def achat_detail(request, achat_id):
    achat = get_object_or_404(Achat.objects.select_related('utilisateur'), pk=achat_id)
    return render(request, 'gerance/achat_detail.html', {'achat': achat, 'lignes': achat.lignes.select_related('produit__categorie')})


@gerant_requis
def achat_nouveau(request):
    form = AchatForm(request.POST or None)
    lignes = LignesAchatFormSet(request.POST or None, prefix='lignes')
    if request.method == 'POST' and form.is_valid() and lignes.is_valid():
        donnees = [f.cleaned_data for f in lignes.forms if f.cleaned_data]
        achat = enregistrer_achat(form.cleaned_data, donnees, request.user)
        messages.success(request, f"Achat enregistré : {len(donnees)} boisson{'s' if len(donnees) > 1 else ''}, "
                                  f"{achat.total:,} FCFA. Le stock est à jour.".replace(',', ' '))
        return redirect('achat_detail', achat.pk)
    context = {
        'form': form,
        'lignes': lignes,
        'fournisseurs': Achat.objects.order_by('fournisseur').values_list('fournisseur', flat=True).distinct(),
        'prix_achat': {p.pk: p.prix_achat for p in Produit.objects.exclude(prix_achat=None)},
    }
    return render(request, 'gerance/achat_form.html', context)
