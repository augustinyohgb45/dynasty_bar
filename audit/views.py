import csv
from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from comptes.decorators import gerant_requis

from .models import JournalAudit

PERIODES = [
    ('jour', "Aujourd'hui"),
    ('7j', "7 derniers jours"),
    ('30j', "30 derniers jours"),
    ('tout', "Tout"),
]


def _filtrer(request):
    filtres = {cle: request.GET.get(cle, '').strip() for cle in ('periode', 'utilisateur', 'action', 'type_objet', 'q')}
    filtres['periode'] = filtres['periode'] or '7j'
    filtres['sensibles'] = request.GET.get('sensibles') == '1'
    journal = JournalAudit.objects.all()

    maintenant = timezone.localtime()
    if filtres['periode'] == 'jour':
        journal = journal.filter(date__gte=maintenant.replace(hour=0, minute=0, second=0, microsecond=0))
    elif filtres['periode'] in ('7j', '30j'):
        journal = journal.filter(date__gte=maintenant - timedelta(days=int(filtres['periode'][:-1])))
    if filtres['utilisateur'] == 'systeme':
        journal = journal.filter(nom_utilisateur='')
    elif filtres['utilisateur']:
        journal = journal.filter(nom_utilisateur=filtres['utilisateur'])
    if filtres['action']:
        journal = journal.filter(action=filtres['action'])
    if filtres['type_objet']:
        journal = journal.filter(type_objet=filtres['type_objet'])
    if filtres['sensibles']:
        journal = journal.filter(action__in=JournalAudit.SENSIBLES)
    if filtres['q']:
        q = filtres['q']
        journal = journal.filter(Q(objet__icontains=q) | Q(details__icontains=q) | Q(nom_utilisateur__icontains=q))
    return journal, filtres


def _export_csv(journal):
    reponse = HttpResponse(content_type='text/csv; charset=utf-8')
    reponse['Content-Disposition'] = f'attachment; filename="journal-audit-{timezone.localdate():%Y-%m-%d}.csv"'
    reponse.write('﻿')  # pour qu'Excel lise correctement les accents
    ecrivain = csv.writer(reponse, delimiter=';')
    ecrivain.writerow(['Date', 'Utilisateur', 'Action', 'Élément', 'Objet', 'Montant (FCFA)', 'Détails', 'Adresse IP'])
    for e in journal.iterator():
        ecrivain.writerow([
            timezone.localtime(e.date).strftime('%d/%m/%Y %H:%M:%S'), e.nom_utilisateur or 'Système',
            e.get_action_display(), e.type_objet, e.objet, '' if e.montant is None else e.montant,
            e.details.replace('\n', ' | '), e.adresse_ip or '',
        ])
    return reponse


@gerant_requis
def journal(request):
    entrees, filtres = _filtrer(request)
    if request.GET.get('export') == 'csv':
        return _export_csv(entrees)

    debut_jour = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    du_jour = JournalAudit.objects.filter(date__gte=debut_jour)
    parametres = request.GET.copy()
    parametres.pop('page', None)
    parametres.pop('export', None)
    context = {
        'page_journal': Paginator(entrees, 50).get_page(request.GET.get('page')),
        'filtres': filtres,
        'parametres': parametres.urlencode(),
        'periodes': PERIODES,
        'actions': JournalAudit.ACTIONS,
        'utilisateurs': (JournalAudit.objects.exclude(nom_utilisateur='')
                         .order_by('nom_utilisateur').values_list('nom_utilisateur', flat=True).distinct()),
        'types_objet': (JournalAudit.objects.exclude(type_objet='')
                        .order_by('type_objet').values_list('type_objet', flat=True).distinct()),
        'nb_actions_jour': du_jour.count(),
        'encaisse_jour': du_jour.filter(action=JournalAudit.PAIEMENT).aggregate(t=Sum('montant'))['t'] or 0,
        'nb_sensibles_jour': du_jour.filter(action__in=JournalAudit.SENSIBLES).count(),
        'nb_echecs_7j': JournalAudit.objects.filter(action=JournalAudit.ECHEC_CONNEXION,
                                                    date__gte=timezone.now() - timedelta(days=7)).count(),
    }
    return render(request, 'audit/journal.html', context)
