from django import forms
from django.forms import formset_factory
from django.utils import timezone

from stock.models import Categorie, Produit


class AchatForm(forms.Form):
    fournisseur = forms.CharField(max_length=120, widget=forms.TextInput(attrs={'placeholder': "Ex. : SOLIBRA, dépôt Adjamé…", 'list': 'fournisseurs'}))
    reference = forms.CharField(label="N° de facture ou de bon", max_length=60, required=False)
    date = forms.DateField(label="Date de l'achat", initial=timezone.localdate,
                           widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    note = forms.CharField(max_length=255, required=False)

    def clean_date(self):
        date = self.cleaned_data['date']
        if date > timezone.localdate():
            raise forms.ValidationError("La date de l'achat ne peut pas être dans le futur.")
        return date


class LigneAchatForm(forms.Form):
    """Une boisson achetée : existante, ou nouvelle (nom, catégorie et prix de vente à renseigner)."""
    produit = forms.ModelChoiceField(queryset=Produit.objects.unitaires().select_related('categorie'), required=False,
                                     empty_label="— Nouvelle boisson —")
    nouveau_nom = forms.CharField(label="Nom de la nouvelle boisson", max_length=120, required=False)
    nouvelle_categorie = forms.ModelChoiceField(label="Catégorie", queryset=Categorie.objects.all(), required=False)
    prix_vente = forms.IntegerField(label="Prix de vente (FCFA)", min_value=0, required=False)
    quantite = forms.IntegerField(label="Quantité", min_value=1)
    prix_unitaire = forms.IntegerField(label="Prix unitaire (FCFA)", min_value=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['produit'].label_from_instance = lambda p: f"{p.nom} — {p.categorie}"

    def clean(self):
        donnees = super().clean()
        if donnees.get('produit') is None:
            nom = (donnees.get('nouveau_nom') or '').strip()
            if not nom:
                self.add_error('produit', "Choisissez une boisson ou saisissez le nom d'une nouvelle boisson.")
            else:
                if Produit.objects.filter(nom__iexact=nom).exists():
                    self.add_error('nouveau_nom', "Cette boisson existe déjà : choisissez-la dans la liste.")
                if donnees.get('nouvelle_categorie') is None:
                    self.add_error('nouvelle_categorie', "Choisissez la catégorie de la nouvelle boisson.")
                if donnees.get('prix_vente') is None:
                    self.add_error('prix_vente', "Indiquez le prix de vente de la nouvelle boisson.")
            donnees['nouveau_nom'] = nom
        return donnees


class BaseLignesAchat(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        lignes = [f.cleaned_data for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE')]
        if not lignes:
            raise forms.ValidationError("Ajoutez au moins une boisson à l'achat.")
        noms = [l['nouveau_nom'].lower() for l in lignes if not l.get('produit')]
        produits = [l['produit'].pk for l in lignes if l.get('produit')]
        if len(set(noms)) != len(noms) or len(set(produits)) != len(produits):
            raise forms.ValidationError("Une même boisson apparaît sur plusieurs lignes : regroupez les quantités.")


LignesAchatFormSet = formset_factory(LigneAchatForm, formset=BaseLignesAchat, extra=1)
