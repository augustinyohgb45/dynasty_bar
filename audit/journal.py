"""
Journal d'audit : qui a fait quoi, quand et depuis quel appareil.

- Les actions de caisse et de stock (ajout d'article, encaissement, annulation, réception…)
  sont journalisées explicitement par le code métier avec journaliser().
- Les créations, modifications et suppressions du catalogue, des tables et des comptes sont
  journalisées automatiquement, quel que soit l'écran utilisé (application ou administration).
- Les connexions, déconnexions et échecs de connexion sont aussi enregistrés.
"""
import datetime
import logging
import threading
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save, pre_save
from django.utils import timezone

from .models import JournalAudit

logger = logging.getLogger(__name__)
_contexte = threading.local()

# Champs techniques jamais affichés dans le détail des modifications
CHAMPS_IGNORES = {'id', 'password', 'last_login', 'date_joined', 'date_creation'}

LIBELLES = {
    'code': "Code", 'nom': "Nom", 'categorie': "Catégorie", 'prix_achat': "Prix d'achat",
    'prix_vente': "Prix de vente", 'seuil_alerte': "Seuil d'alerte", 'actif': "En vente",
    'ordre': "Ordre", 'zone': "Zone", 'active': "Active",
    'username': "Nom d'utilisateur", 'first_name': "Prénom", 'last_name': "Nom", 'email': "E-mail",
    'is_active': "Compte actif", 'is_superuser': "Gérant", 'is_staff': "Accès à l'administration",
}


class AuditMiddleware:
    """Mémorise la requête en cours pour connaître l'auteur et l'adresse IP des actions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _contexte.request = request
        try:
            return self.get_response(request)
        finally:
            _contexte.request = None


@contextmanager
def sans_suivi_automatique():
    """Suspend le suivi automatique (ex. : import en masse, résumé en une seule entrée)."""
    _contexte.pause = True
    try:
        yield
    finally:
        _contexte.pause = False


def _suivi_actif(sender):
    return sender in MODELES and not getattr(_contexte, 'pause', False)


def _requete():
    return getattr(_contexte, 'request', None)


def journaliser(action, objet='', type_objet='', details='', montant=None, utilisateur=None, request=None):
    """Ajoute une entrée au journal. Sans utilisateur connu, l'action est attribuée au « Système »."""
    request = request or _requete()
    if utilisateur is None and request is not None:
        compte = getattr(request, 'user', None)
        if compte is not None and compte.is_authenticated:
            utilisateur = compte
    try:
        JournalAudit.objects.create(
            utilisateur=utilisateur if utilisateur is not None and utilisateur.pk else None,
            nom_utilisateur=utilisateur.get_username() if utilisateur is not None else '',
            action=action,
            type_objet=type_objet,
            objet=str(objet)[:255],
            details=details,
            montant=montant,
            adresse_ip=request.META.get('REMOTE_ADDR') if request is not None else None,
        )
    except Exception as e:
        # L'audit ne doit jamais bloquer l'action elle-même
        logger.error(f"Impossible d'enregistrer l'audit ({action} {objet}) : {e}")


def fcfa(montant):
    return f"{int(montant):,}".replace(',', ' ') + " FCFA"


# ---------- Connexions ----------

def _connexion(sender, request, user, **kwargs):
    journaliser(JournalAudit.CONNEXION, objet=user.get_username(), type_objet="Session", utilisateur=user, request=request)


def _deconnexion(sender, request, user, **kwargs):
    if user is not None:
        journaliser(JournalAudit.DECONNEXION, objet=user.get_username(), type_objet="Session",
                    utilisateur=user, request=request)


def _echec_connexion(sender, credentials, request=None, **kwargs):
    nom = credentials.get('username', '')
    journaliser(JournalAudit.ECHEC_CONNEXION, objet=nom, type_objet="Session",
                details=f"Tentative avec le nom d'utilisateur « {nom} ».", request=request)


# ---------- Catalogue, tables et comptes ----------

def _valeur_lisible(instance, champ):
    if champ.choices:
        brute = getattr(instance, champ.attname)
        return str(dict(champ.flatchoices).get(brute, brute))
    valeur = getattr(instance, champ.name, None)
    if valeur is None or valeur == '':
        return "—"
    if isinstance(valeur, bool):
        return "oui" if valeur else "non"
    if isinstance(valeur, datetime.datetime):
        return timezone.localtime(valeur).strftime('%d/%m/%Y %H:%M') if timezone.is_aware(valeur) else str(valeur)
    return str(valeur)


def _instantane(instance):
    return {f.name: _valeur_lisible(instance, f) for f in instance._meta.concrete_fields if f.name not in CHAMPS_IGNORES}


def _modeles_suivis():
    from caisse.models import Table
    from stock.models import Categorie, Produit
    return {Produit: "Produit", Categorie: "Catégorie", Table: "Table", get_user_model(): "Compte"}


def _avant_enregistrement(sender, instance, **kwargs):
    if not _suivi_actif(sender) or not instance.pk:
        return
    ancien = sender.objects.filter(pk=instance.pk).first()
    if ancien is not None:
        instance._audit_avant = _instantane(ancien)
        instance._audit_mot_de_passe = getattr(ancien, 'password', None)


def _apres_enregistrement(sender, instance, created, **kwargs):
    if not _suivi_actif(sender):
        return
    if created:
        details = "\n".join(f"{LIBELLES.get(k, k)} : {v}" for k, v in _instantane(instance).items() if v != "—")
        journaliser(JournalAudit.CREATION, objet=instance, type_objet=MODELES[sender], details=details)
        return
    avant = getattr(instance, '_audit_avant', None)
    if avant is None:
        return
    apres = _instantane(instance)
    changements = [f"{LIBELLES.get(k, k)} : {avant[k]} → {v}" for k, v in apres.items() if avant.get(k) != v]
    if getattr(instance, '_audit_mot_de_passe', None) not in (None, getattr(instance, 'password', None)):
        changements.append("Mot de passe modifié")
    del instance._audit_avant
    if changements:
        journaliser(JournalAudit.MODIFICATION, objet=instance, type_objet=MODELES[sender], details="\n".join(changements))


def _apres_suppression(sender, instance, **kwargs):
    if _suivi_actif(sender):
        journaliser(JournalAudit.SUPPRESSION, objet=instance, type_objet=MODELES[sender])


MODELES = {}


def connecter():
    """Branche les signaux (appelé au démarrage de l'application)."""
    MODELES.update(_modeles_suivis())
    user_logged_in.connect(_connexion, dispatch_uid='audit_connexion')
    user_logged_out.connect(_deconnexion, dispatch_uid='audit_deconnexion')
    user_login_failed.connect(_echec_connexion, dispatch_uid='audit_echec')
    pre_save.connect(_avant_enregistrement, dispatch_uid='audit_avant')
    post_save.connect(_apres_enregistrement, dispatch_uid='audit_apres')
    post_delete.connect(_apres_suppression, dispatch_uid='audit_suppression')
