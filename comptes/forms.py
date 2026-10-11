from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User

CAISSE = 'caisse'
ADMIN = 'admin'
ROLES = [(CAISSE, "Caisse : tables, commandes, encaissements, ses ventes"),
         (ADMIN, "Admin : accès complet (stock, achats, tableau de bord, journal, clôture, comptes)")]


def appliquer_role(utilisateur, role):
    utilisateur.is_superuser = role == ADMIN
    utilisateur.is_staff = role == ADMIN


class CompteForm(UserCreationForm):
    role = forms.ChoiceField(label="Rôle", choices=ROLES, initial=CAISSE, widget=forms.RadioSelect)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'role']
        labels = {'username': "Identifiant de connexion", 'first_name': "Prénom", 'last_name': "Nom"}
        help_texts = {'username': "Ex. : awa, kone.m — lettres, chiffres et . _ - uniquement."}

    def save(self, commit=True):
        utilisateur = super().save(commit=False)
        appliquer_role(utilisateur, self.cleaned_data['role'])
        if commit:
            utilisateur.save()
        return utilisateur


class ModifierCompteForm(forms.ModelForm):
    role = forms.ChoiceField(label="Rôle", choices=ROLES, widget=forms.RadioSelect)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'is_active']
        labels = {'first_name': "Prénom", 'last_name': "Nom", 'is_active': "Compte actif (peut se connecter)"}

    def __init__(self, *args, demandeur=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.demandeur = demandeur
        self.fields['role'].initial = ADMIN if self.instance.is_superuser else CAISSE

    def clean(self):
        donnees = super().clean()
        # Un admin ne peut pas se retirer ses propres droits ni se bloquer lui-même
        if self.demandeur is not None and self.instance.pk == self.demandeur.pk:
            if donnees.get('role') != ADMIN:
                self.add_error('role', "Vous ne pouvez pas retirer vos propres droits d'admin.")
            if not donnees.get('is_active'):
                self.add_error('is_active', "Vous ne pouvez pas désactiver votre propre compte.")
        return donnees

    def save(self, commit=True):
        utilisateur = super().save(commit=False)
        appliquer_role(utilisateur, self.cleaned_data['role'])
        if commit:
            utilisateur.save()
        return utilisateur


class MotDePasseForm(SetPasswordForm):
    pass
