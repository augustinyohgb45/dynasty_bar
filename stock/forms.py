from django import forms

from .models import Categorie, MouvementStock, Produit


class ProduitForm(forms.ModelForm):
    nouvelle_categorie = forms.CharField(
        label="… ou nouvelle catégorie", required=False, max_length=60,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Ex. : Soft, Eau"}))

    class Meta:
        model = Produit
        fields = ['code', 'nom', 'categorie', 'prix_achat', 'prix_vente', 'seuil_alerte', 'actif',
                  'lot_de', 'nb_bouteilles']
        widgets = {
            'lot_de': forms.Select(attrs={'class': 'custom-select'}),
            'nb_bouteilles': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Ex. : Soft01"}),
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'categorie': forms.Select(attrs={'class': 'custom-select'}),
            'prix_achat': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'prix_vente': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'seuil_alerte': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'actif': forms.CheckboxInput(attrs={'class': 'custom-control-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categorie'].required = False
        lots = Produit.objects.unitaires().select_related('categorie')
        if self.instance.pk:
            lots = lots.exclude(pk=self.instance.pk)
        self.fields['lot_de'].queryset = lots
        self.fields['lot_de'].empty_label = "— Vendue à l'unité —"
        self.fields['lot_de'].label_from_instance = lambda p: f"{p.nom} — {p.categorie}"
        self.fields['nb_bouteilles'].required = False

    def clean(self):
        donnees = super().clean()
        base, nb = donnees.get('lot_de'), donnees.get('nb_bouteilles') or 1
        if base is not None:
            if self.instance.pk and self.instance.lots.exists():
                self.add_error('lot_de', "Cette boisson sert déjà de base à un lot : elle ne peut pas devenir un lot.")
            if nb < 2:
                self.add_error('nb_bouteilles', "Un lot contient au moins 2 bouteilles.")
            if self.instance.pk and self.instance.mouvements.exists():
                self.add_error('lot_de', "Cette boisson a déjà du stock ou des mouvements : créez plutôt un nouveau lot.")
        else:
            donnees['nb_bouteilles'] = 1
        nouvelle = (donnees.get('nouvelle_categorie') or '').strip()
        if nouvelle:
            categorie = Categorie.objects.filter(nom__iexact=nouvelle).first()
            donnees['categorie'] = categorie or Categorie.objects.create(nom=nouvelle[:1].upper() + nouvelle[1:])
            self.instance.categorie = donnees['categorie']
        elif not donnees.get('categorie'):
            self.add_error('categorie', "Choisissez une catégorie ou saisissez-en une nouvelle.")
        return donnees


class MouvementForm(forms.Form):
    produit = forms.ModelChoiceField(
        queryset=Produit.objects.unitaires().filter(actif=True).select_related('categorie'),
        widget=forms.Select(attrs={'class': 'custom-select'}))
    type = forms.ChoiceField(choices=MouvementStock.TYPES, widget=forms.Select(attrs={'class': 'custom-select'}))
    quantite = forms.IntegerField(
        label="Quantité", min_value=0,
        help_text="Pour un ajustement d'inventaire, saisissez le stock compté.",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0}))
    prix_achat = forms.IntegerField(
        label="Prix d'achat unitaire (FCFA)", required=False, min_value=0,
        help_text="Pour une entrée : laissez vide pour reprendre le prix du catalogue.",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0}))
    motif = forms.CharField(
        required=False, max_length=255,
        help_text="Obligatoire pour une casse, un offert ou un ajustement.",
        widget=forms.TextInput(attrs={'class': 'form-control',
                                      'placeholder': "Ex. : bouteille tombée, client VIP table 3…"}))

    def __init__(self, *args, utilisateur=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.utilisateur = utilisateur
        self.fields['produit'].label_from_instance = lambda p: f"{p.nom} — {p.categorie}"
        # Les ventes passent par la caisse, pour être rattachées à une commande et à un paiement
        exclus = {MouvementStock.VENTE}
        if utilisateur is None or not utilisateur.is_superuser:
            exclus |= MouvementStock.TYPES_RESERVES
        self.fields['type'].choices = [(cle, libelle) for cle, libelle in MouvementStock.TYPES if cle not in exclus]

    def clean(self):
        donnees = super().clean()
        produit, type_mvt, quantite = donnees.get('produit'), donnees.get('type'), donnees.get('quantite')
        if produit is None or type_mvt is None or quantite is None:
            return donnees
        if type_mvt in MouvementStock.TYPES_RESERVES and not (donnees.get('motif') or '').strip():
            self.add_error('motif', "Indiquez le motif.")

        stock = Produit.objects.avec_stock().get(pk=produit.pk).stock
        if type_mvt == MouvementStock.INVENTAIRE:
            variation = quantite - stock
            if variation == 0:
                self.add_error('quantite', f"Le stock compté est identique au stock théorique ({stock}) : rien à ajuster.")
        else:
            variation = -quantite if type_mvt in MouvementStock.TYPES_SORTANTS else quantite
            if quantite == 0:
                self.add_error('quantite', "La quantité doit être supérieure à zéro.")
            elif variation < 0 and stock + variation < 0:
                self.add_error('quantite', f"Stock insuffisant : il reste {stock} × {produit}.")
        donnees['variation'] = variation
        return donnees

    def creer_mouvement(self):
        d = self.cleaned_data
        produit, type_mvt = d['produit'], d['type']
        if type_mvt == MouvementStock.ENTREE and d.get('prix_achat') is not None:
            prix = d['prix_achat']
        else:
            prix = produit.prix_achat
        return MouvementStock.objects.create(
            produit=produit, type=type_mvt, quantite=d['variation'], prix_unitaire=prix,
            motif=(d.get('motif') or '').strip(), utilisateur=self.utilisateur)


class ImportForm(forms.Form):
    fichier = forms.FileField(
        label="Classeur Excel", help_text="Fichier .xlsx ou .xlsm contenant la feuille « Catalogue ».",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control-file', 'accept': '.xlsx,.xlsm'}))
    simulation = forms.BooleanField(
        label="Simulation (vérifier sans enregistrer)", required=False,
        widget=forms.CheckboxInput(attrs={'class': 'custom-control-input'}))

    def clean_fichier(self):
        fichier = self.cleaned_data['fichier']
        if not fichier.name.lower().endswith(('.xlsx', '.xlsm')):
            raise forms.ValidationError("Le fichier doit être au format .xlsx ou .xlsm.")
        return fichier
