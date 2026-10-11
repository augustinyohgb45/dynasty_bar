import os
import tempfile

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from audit.journal import fcfa, journaliser
from audit.models import JournalAudit
from comptes.decorators import gerant_requis

from .forms import ImportForm, MouvementForm, ProduitForm
from .importation import ErreurImport, importer_catalogue
from .models import Categorie, MouvementStock, Produit

LIBELLES_ETAT = {'ok': "OK", 'alerte': "Alerte", 'rupture': "Rupture"}


@gerant_requis
def stock(request):
    produits = list(Produit.objects.filter(actif=True).avec_stock().select_related('categorie'))
    categorie_choisie = request.GET.get('categorie', '')

    valeur_vente = valeur_achat = nb_alertes = nb_ruptures = nb_sans_prix_achat = 0
    for produit in produits:
        produit.etat_stock = produit.etat(produit.stock)
        produit.libelle_etat = LIBELLES_ETAT[produit.etat_stock]
        produit.valeur = max(produit.stock, 0) * produit.prix_vente
        valeur_vente += produit.valeur
        if produit.prix_achat is None:
            nb_sans_prix_achat += 1
        else:
            valeur_achat += max(produit.stock, 0) * produit.prix_achat
        nb_alertes += produit.etat_stock == 'alerte'
        nb_ruptures += produit.etat_stock == 'rupture'

    context = {
        'produits': [p for p in produits if not categorie_choisie or str(p.categorie_id) == categorie_choisie],
        'categories': Categorie.objects.filter(produits__actif=True).distinct(),
        'categorie_choisie': categorie_choisie,
        'nb_produits': len(produits),
        'valeur_vente': valeur_vente,
        'valeur_achat': valeur_achat,
        'nb_sans_prix_achat': nb_sans_prix_achat,
        'nb_alertes': nb_alertes,
        'nb_ruptures': nb_ruptures,
    }
    return render(request, 'stock/stock.html', context)


@gerant_requis
def mouvements(request):
    if request.method == 'POST':
        form = MouvementForm(request.POST, utilisateur=request.user)
        with transaction.atomic():
            if form.is_valid():
                mouvement = form.creer_mouvement()
                _journaliser_mouvement(mouvement)
                messages.success(request, f"{mouvement.get_type_display()} enregistrée : {mouvement.produit} "
                                          f"({mouvement.quantite:+d}).")
                return redirect('mouvements')
    else:
        initial = {}
        if request.GET.get('produit'):
            initial['produit'] = request.GET['produit']
        if request.GET.get('type'):
            initial['type'] = request.GET['type']
        form = MouvementForm(initial=initial, utilisateur=request.user)

    context = {
        'form': form,
        'mouvements': MouvementStock.objects.select_related('produit', 'utilisateur')[:300],
        'types': MouvementStock.TYPES,
    }
    return render(request, 'stock/mouvements.html', context)


ACTIONS_MOUVEMENT = {
    MouvementStock.ENTREE: JournalAudit.RECEPTION,
    MouvementStock.CASSE: JournalAudit.PERTE,
    MouvementStock.OFFERT: JournalAudit.PERTE,
    MouvementStock.INVENTAIRE: JournalAudit.INVENTAIRE,
}


def _journaliser_mouvement(mouvement):
    details = [f"{mouvement.get_type_display()} : {mouvement.quantite:+d} × {mouvement.produit}"]
    if mouvement.prix_unitaire is not None:
        details.append(f"Prix unitaire : {fcfa(mouvement.prix_unitaire)}")
    if mouvement.motif:
        details.append(f"Motif : {mouvement.motif}")
    journaliser(ACTIONS_MOUVEMENT.get(mouvement.type, JournalAudit.MODIFICATION), objet=mouvement.produit,
                type_objet="Stock", details="\n".join(details), montant=mouvement.montant,
                utilisateur=mouvement.utilisateur)


@gerant_requis
def produit_nouveau(request):
    return _formulaire_produit(request, Produit())


@gerant_requis
def produit_modifier(request, produit_id):
    return _formulaire_produit(request, get_object_or_404(Produit, pk=produit_id))


def _formulaire_produit(request, produit):
    creation = produit.pk is None
    form = ProduitForm(request.POST or None, instance=produit)
    if request.method == 'POST' and form.is_valid():
        produit = form.save()
        messages.success(request, f"Produit « {produit} » {'créé' if creation else 'modifié'}.")
        return redirect('stock')
    return render(request, 'stock/produit_form.html', {'form': form, 'produit': produit, 'creation': creation})


@gerant_requis
def importer(request):
    rapport = None
    form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        fichier = form.cleaned_data['fichier']
        simulation = form.cleaned_data['simulation']
        # openpyxl a besoin d'un vrai fichier : on recopie l'envoi dans un fichier temporaire
        suffixe = os.path.splitext(fichier.name)[1].lower()
        with tempfile.NamedTemporaryFile(suffix=suffixe, delete=False) as temporaire:
            for morceau in fichier.chunks():
                temporaire.write(morceau)
        try:
            rapport = importer_catalogue(temporaire.name, utilisateur=request.user, simulation=simulation)
        except ErreurImport as e:
            messages.error(request, str(e))
        else:
            if simulation:
                messages.info(request, f"Simulation : {rapport.nb_produits} produits seraient importés. "
                                       "Rien n'a été enregistré.")
            else:
                resume = (f"{rapport.nb_produits} produits importés ({len(rapport.crees)} créés, "
                          f"{len(rapport.mis_a_jour)} mis à jour).")
                journaliser(JournalAudit.IMPORT, objet=fichier.name, type_objet="Catalogue",
                            details="\n".join([resume, *rapport.avertissements]))
                messages.success(request, resume)
        finally:
            os.unlink(temporaire.name)
    return render(request, 'stock/importer.html', {'form': form, 'rapport': rapport})
