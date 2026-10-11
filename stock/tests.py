import os
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from .importation import importer_catalogue, normaliser_categorie
from .models import Categorie, MouvementStock, Produit


def creer_classeur(lignes, stocks=()):
    """Classeur minimal au format du fichier Dynasty ; retourne son chemin."""
    classeur = Workbook()
    catalogue = classeur.active
    catalogue.title = 'Catalogue'
    catalogue.append(['ID_Produit', 'Designation', 'Categorie', 'Prix_Achat', 'Prix_Vente', 'Stock_Alerte'])
    for ligne in lignes:
        catalogue.append(list(ligne))
    stock = classeur.create_sheet('Stock_Reel')
    stock.append(['ID_Produit', 'Designation', 'Stock_Initial'])
    for code, quantite in stocks:
        stock.append([code, '', quantite])
    fichier = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    fichier.close()
    classeur.save(fichier.name)
    return fichier.name


class ImportCatalogueTests(TestCase):
    lignes = [
        ('P001', 'Castel Beer', 'Bières', 600, 1000, 24),
        ('Champ1', 'Les portes de bordeaux  ', 'Champagne', 600, 30000, 10),
        ('Liq19', 'Hennessy ', 'Liqueur', None, 50000, None),
        ('Bier01', 'Heineken ', 'Bière', None, 1000, None),
    ]

    def setUp(self):
        self.chemin = creer_classeur(self.lignes, stocks=[('Champ1', 11)])

    def tearDown(self):
        os.unlink(self.chemin)

    def test_import_et_nettoyage(self):
        rapport = importer_catalogue(self.chemin)
        self.assertEqual(len(rapport.crees), 4)
        self.assertEqual(Produit.objects.get(code='Champ1').nom, 'Les portes de bordeaux')
        # « Bières » et « Bière » ne forment plus qu'une catégorie
        self.assertEqual(Produit.objects.get(code='P001').categorie, Produit.objects.get(code='Bier01').categorie)
        self.assertEqual(Produit.objects.get(code='Liq19').categorie.nom, 'Cognac')

    def test_prix_achat_incoherent_ecarte(self):
        rapport = importer_catalogue(self.chemin)
        self.assertIsNone(Produit.objects.get(code='Champ1').prix_achat)
        self.assertEqual(Produit.objects.get(code='P001').prix_achat, 600)
        self.assertTrue(any('Les portes de bordeaux' in a for a in rapport.avertissements))

    def test_stock_initial_non_duplique(self):
        importer_catalogue(self.chemin)
        importer_catalogue(self.chemin)
        self.assertEqual(Produit.objects.count(), 4)
        self.assertEqual(Produit.objects.get(code='Champ1').stock_actuel, 11)

    def test_simulation_n_enregistre_rien(self):
        rapport = importer_catalogue(self.chemin, simulation=True)
        self.assertEqual(rapport.nb_produits, 4)
        self.assertFalse(Produit.objects.exists())

    def test_repartition_des_alcools_forts(self):
        self.assertEqual(normaliser_categorie('Liqueur', "Gordon's Pink (Rose)"), 'Gin')
        self.assertEqual(normaliser_categorie('Liqueur', 'JB'), 'Whisky')
        self.assertEqual(normaliser_categorie('Liqueur', 'Baileys'), 'Liqueur')


class MouvementsTests(TestCase):
    def setUp(self):
        categorie = Categorie.objects.create(nom='Champagne')
        self.produit = Produit.objects.create(code='Champ5', nom='Moet', categorie=categorie,
                                              prix_achat=30000, prix_vente=50000, seuil_alerte=3)
        self.serveur = User.objects.create_user('serveur', password='motdepasse-test')
        self.admin = User.objects.create_superuser('admin', password='motdepasse-test')

    def poster(self, **donnees):
        return self.client.post(reverse('mouvements'), dict({'produit': self.produit.pk}, **donnees))

    def test_reception_au_prix_saisi(self):
        self.client.force_login(self.admin)
        self.poster(type='entree', quantite=5, prix_achat=28000)
        entree = MouvementStock.objects.get(type='entree')
        self.assertEqual((entree.quantite, entree.prix_unitaire, entree.montant), (5, 28000, 140000))
        self.assertEqual(self.produit.stock_actuel, 5)

    def test_vente_manuelle_impossible(self):
        # Les ventes passent uniquement par la caisse
        self.client.force_login(self.admin)
        self.poster(type='entree', quantite=5)
        self.poster(type='vente', quantite=2)
        self.assertEqual(self.produit.stock_actuel, 5)

    def test_sortie_refusee_si_stock_insuffisant(self):
        self.client.force_login(self.admin)
        reponse = self.poster(type='casse', quantite=1, motif='tombée')
        self.assertContains(reponse, 'Stock insuffisant')
        self.assertFalse(MouvementStock.objects.exists())

    def test_mouvements_reserves_a_l_admin(self):
        self.client.force_login(self.serveur)
        self.assertEqual(self.poster(type='entree', quantite=5).status_code, 403)
        self.assertEqual(self.client.get(reverse('mouvements')).status_code, 403)
        self.assertEqual(self.produit.stock_actuel, 0)

    def test_casse_exige_un_motif(self):
        self.client.force_login(self.admin)
        self.poster(type='entree', quantite=5)
        self.assertContains(self.poster(type='casse', quantite=1), 'Indiquez le motif')
        self.poster(type='casse', quantite=1, motif='bouteille tombée')
        self.assertEqual(self.produit.stock_actuel, 4)

    def test_inventaire_ajuste_au_stock_compte(self):
        self.client.force_login(self.admin)
        self.poster(type='entree', quantite=10)
        self.poster(type='inventaire', quantite=7, motif='inventaire de fin de soirée')
        self.assertEqual(self.produit.stock_actuel, 7)
        self.assertEqual(MouvementStock.objects.get(type='inventaire').quantite, -3)


class PagesTests(TestCase):
    def setUp(self):
        self.serveur = User.objects.create_user('serveur', password='motdepasse-test')
        self.admin = User.objects.create_superuser('admin', password='motdepasse-test')

    def test_stock_reserve_a_l_admin(self):
        self.assertEqual(self.client.get(reverse('stock')).status_code, 302)
        self.client.force_login(self.serveur)
        self.assertEqual(self.client.get(reverse('stock')).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('stock')).status_code, 200)

    def test_catalogue_et_import_reserves_aux_administrateurs(self):
        self.client.force_login(self.serveur)
        self.assertEqual(self.client.get(reverse('importer')).status_code, 403)
        self.assertEqual(self.client.get(reverse('produit_nouveau')).status_code, 403)

    def test_creation_produit_avec_nouvelle_categorie(self):
        self.client.force_login(self.admin)
        reponse = self.client.post(reverse('produit_nouveau'), {
            'code': 'Soft01', 'nom': 'Coca-Cola', 'nouvelle_categorie': 'soft',
            'prix_vente': 1000, 'seuil_alerte': 24, 'actif': 'on'})
        self.assertRedirects(reponse, reverse('stock'))
        self.assertEqual(Produit.objects.get(code='Soft01').categorie.nom, 'Soft')

    def test_import_par_la_page(self):
        chemin = creer_classeur([('P001', 'Castel Beer', 'Bières', 600, 1000, 24)])
        with open(chemin, 'rb') as f:
            envoi = SimpleUploadedFile('catalogue.xlsx', f.read())
        os.unlink(chemin)
        self.client.force_login(self.admin)
        reponse = self.client.post(reverse('importer'), {'fichier': envoi})
        self.assertContains(reponse, 'Rapport d')
        self.assertTrue(Produit.objects.filter(code='P001').exists())
