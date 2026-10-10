import re
import unicodedata
from datetime import datetime, time

from django.db import transaction
from django.utils import timezone

from audit.journal import fcfa, journaliser
from audit.models import JournalAudit
from stock.models import MouvementStock, Produit

from .models import Achat, LigneAchat


def code_disponible(categorie):
    """Code produit lisible pour une nouvelle boisson : WHIS01, CHAM12…"""
    lettres = unicodedata.normalize('NFKD', categorie.nom).encode('ascii', 'ignore').decode()
    prefixe = (re.sub(r'[^A-Za-z]', '', lettres).upper() or 'PROD')[:4]
    numero = 1
    while Produit.objects.filter(code=f"{prefixe}{numero:02d}").exists():
        numero += 1
    return f"{prefixe}{numero:02d}"


@transaction.atomic
def enregistrer_achat(entete, lignes, utilisateur):
    """
    Enregistre un achat : crée les nouvelles boissons, fait entrer le stock au prix payé
    et met à jour le prix d'achat de référence de chaque boisson.
    """
    date = entete['date']
    moment = timezone.now() if date == timezone.localdate() else timezone.make_aware(datetime.combine(date, time(12)))
    achat = Achat.objects.create(fournisseur=entete['fournisseur'].strip(), reference=entete.get('reference', '').strip(),
                                 date=moment, note=entete.get('note', '').strip(), utilisateur=utilisateur)
    details = []
    for ligne in lignes:
        produit = ligne.get('produit')
        if produit is None:
            categorie = ligne['nouvelle_categorie']
            produit = Produit.objects.create(code=code_disponible(categorie), nom=ligne['nouveau_nom'],
                                             categorie=categorie, prix_vente=ligne['prix_vente'],
                                             prix_achat=ligne['prix_unitaire'])
            details.append(f"Nouvelle boisson : {produit} ({categorie}), vendue {fcfa(produit.prix_vente)}")
        elif produit.prix_achat != ligne['prix_unitaire'] or not produit.actif:
            produit.prix_achat = ligne['prix_unitaire']
            produit.actif = True
            produit.save(update_fields=['prix_achat', 'actif'])

        mouvement = MouvementStock.objects.create(
            produit=produit, type=MouvementStock.ENTREE, quantite=ligne['quantite'],
            prix_unitaire=ligne['prix_unitaire'], date=moment, utilisateur=utilisateur,
            motif=f"Achat {achat.fournisseur}{f' · {achat.reference}' if achat.reference else ''}")
        LigneAchat.objects.create(achat=achat, produit=produit, quantite=ligne['quantite'],
                                  prix_unitaire=ligne['prix_unitaire'], mouvement=mouvement)
        details.append(f"{ligne['quantite']} × {produit} à {fcfa(ligne['prix_unitaire'])}")

    total = achat.total
    journaliser(JournalAudit.ACHAT, objet=achat, type_objet="Achat",
                details="\n".join(details + [f"Total : {fcfa(total)}"]), montant=total, utilisateur=utilisateur)
    return achat
