"""
Suivi en direct de la soirée pour l'admin : ce que fait chaque membre du personnel,
les commandes en cours avec leur contenu, les derniers encaissements et le fil des actions.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone

from audit.models import JournalAudit
from caisse.models import Commande, LigneCommande, Paiement
from caisse.services import bornes_soiree, debut_soiree

# Au-delà de ce délai sans action, la personne n'est plus considérée comme active
DELAI_ACTIVITE = timedelta(minutes=15)


def donnees_direct(personne=''):
    jour = timezone.localtime(debut_soiree()).date()
    debut, fin = bornes_soiree(jour)
    maintenant = timezone.now()

    # Commandes en cours, avec leur contenu
    ouvertes = list(Commande.objects.filter(statut=Commande.OUVERTE).avec_totaux()
                    .select_related('table', 'serveur').order_by('date_ouverture'))
    lignes = (LigneCommande.objects.filter(commande__in=ouvertes).select_related('produit').order_by('id'))
    contenu = {}
    for ligne in lignes:
        contenu.setdefault(ligne.commande_id, []).append(ligne)
    for c in ouvertes:
        c.articles = contenu.get(c.pk, [])
        c.reste_du = c.montant_total - c.montant_paye
        c.minutes = int((maintenant - c.date_ouverture).total_seconds() // 60)

    # Activité par membre du personnel
    paiements = Paiement.objects.filter(date__gte=debut, date__lt=fin)
    journal_soiree = JournalAudit.objects.filter(date__gte=debut, date__lt=fin)
    personnel = []
    for compte in get_user_model().objects.filter(is_active=True).order_by('is_superuser', 'username'):
        derniere = journal_soiree.filter(utilisateur=compte).exclude(action=JournalAudit.DECONNEXION).first()
        mes_ouvertes = [c for c in ouvertes if c.serveur_id == compte.pk]
        fiche = {
            'compte': compte,
            'encaisse': paiements.filter(recu_par=compte).aggregate(t=Sum('montant'))['t'] or 0,
            'nb_encaissements': paiements.filter(recu_par=compte).count(),
            'nb_soldees': Commande.objects.filter(serveur=compte, statut=Commande.PAYEE,
                                                  date_cloture__gte=debut, date_cloture__lt=fin).count(),
            'ouvertes': len([c for c in mes_ouvertes if c.articles]),
            'montant_ouvert': sum(c.reste_du for c in mes_ouvertes),
            'sensibles': journal_soiree.filter(utilisateur=compte, action__in=JournalAudit.SENSIBLES).count(),
            'derniere': derniere,
            'actif': derniere is not None and maintenant - derniere.date < DELAI_ACTIVITE,
        }
        # On n'affiche que les personnes qui ont travaillé ce soir (ou qui ont une commande ouverte)
        if derniere is not None or mes_ouvertes or fiche['encaisse']:
            personnel.append(fiche)

    fil = journal_soiree
    if personne:
        fil = fil.filter(nom_utilisateur=personne)

    return {
        'jour': jour,
        'debut': debut,
        'maintenant': maintenant,
        'personnel': personnel,
        'nb_actifs': sum(1 for p in personnel if p['actif']),
        'ouvertes': ouvertes,
        'nb_ouvertes': len([c for c in ouvertes if c.articles]),
        'montant_ouvert': sum(c.reste_du for c in ouvertes),
        'encaisse_soiree': paiements.aggregate(t=Sum('montant'))['t'] or 0,
        'derniers_paiements': paiements.select_related('commande__table', 'recu_par').order_by('-date')[:10],
        'fil': fil[:40],
        'personne': personne,
        'noms': (journal_soiree.exclude(nom_utilisateur='').order_by('nom_utilisateur')
                 .values_list('nom_utilisateur', flat=True).distinct()),
    }
