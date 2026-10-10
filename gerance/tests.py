from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audit.models import JournalAudit
from caisse import services
from caisse.models import Commande, Paiement
from stock.models import Categorie, MouvementStock, Produit

from .models import Achat


def donnees_achat(lignes, **entete):
    donnees = {'fournisseur': 'SOLIBRA', 'reference': 'F-001', 'date': timezone.localdate().isoformat(), 'note': '',
               'lignes-TOTAL_FORMS': len(lignes), 'lignes-INITIAL_FORMS': 0,
               'lignes-MIN_NUM_FORMS': 0, 'lignes-MAX_NUM_FORMS': 1000}
    donnees.update(entete)
    for i, ligne in enumerate(lignes):
        for cle, valeur in ligne.items():
            donnees[f'lignes-{i}-{cle}'] = valeur
    return donnees


class AchatTests(TestCase):
    def setUp(self):
        self.whisky = Categorie.objects.create(nom='Whisky')
        self.jack = Produit.objects.create(code='Liq16', nom='Jack Daniel', categorie=self.whisky, prix_vente=40000)
        self.gerant = User.objects.create_superuser('gerant', password='motdepasse-test')
        self.client.force_login(self.gerant)

    def test_achat_fait_entrer_le_stock_et_met_a_jour_le_prix_d_achat(self):
        reponse = self.client.post(reverse('achat_nouveau'), donnees_achat([
            {'produit': self.jack.pk, 'quantite': 12, 'prix_unitaire': 18000},
        ]))
        achat = Achat.objects.get()
        self.assertRedirects(reponse, reverse('achat_detail', args=[achat.pk]))
        self.assertEqual(achat.total, 216000)
        self.jack.refresh_from_db()
        self.assertEqual((self.jack.stock_actuel, self.jack.prix_achat), (12, 18000))
        journal = JournalAudit.objects.get(action='achat')
        self.assertEqual(journal.montant, 216000)

    def test_achat_d_une_nouvelle_boisson(self):
        self.client.post(reverse('achat_nouveau'), donnees_achat([
            {'nouveau_nom': 'Glenfiddich 12 ans', 'nouvelle_categorie': self.whisky.pk, 'prix_vente': 60000,
             'quantite': 6, 'prix_unitaire': 30000},
        ]))
        nouveau = Produit.objects.get(nom='Glenfiddich 12 ans')
        self.assertEqual((nouveau.code, nouveau.prix_achat, nouveau.prix_vente, nouveau.stock_actuel),
                         ('WHIS01', 30000, 60000, 6))
        self.assertIn('Nouvelle boisson', JournalAudit.objects.get(action='achat').details)

    def test_nouvelle_boisson_incomplete_refusee(self):
        reponse = self.client.post(reverse('achat_nouveau'), donnees_achat([
            {'nouveau_nom': 'Glenfiddich', 'quantite': 6, 'prix_unitaire': 30000},
        ]))
        self.assertContains(reponse, 'Choisissez la catégorie')
        self.assertFalse(Achat.objects.exists())

    def test_boisson_en_double_refusee(self):
        reponse = self.client.post(reverse('achat_nouveau'), donnees_achat([
            {'produit': self.jack.pk, 'quantite': 1, 'prix_unitaire': 18000},
            {'produit': self.jack.pk, 'quantite': 2, 'prix_unitaire': 18000},
        ]))
        self.assertContains(reponse, 'plusieurs lignes')
        self.assertFalse(Achat.objects.exists())

    def test_reserve_au_gerant(self):
        self.client.force_login(User.objects.create_user('awa', password='motdepasse-test'))
        for nom in ('tableau_de_bord', 'achats', 'achat_nouveau'):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 403, nom)


class TableauDeBordTests(TestCase):
    def setUp(self):
        categorie = Categorie.objects.create(nom='Champagne')
        self.moet = Produit.objects.create(code='Champ5', nom='Moet', categorie=categorie,
                                           prix_achat=30000, prix_vente=50000, seuil_alerte=3)
        self.ruinart = Produit.objects.create(code='Champ8', nom='Ruinart', categorie=categorie, prix_vente=150000)
        MouvementStock.objects.create(produit=self.moet, type=MouvementStock.ENTREE, quantite=5)
        self.gerant = User.objects.create_superuser('gerant', password='motdepasse-test')
        commande = Commande.objects.create(serveur=self.gerant)
        services.ajouter_produit(commande, self.moet, 2, self.gerant)
        services.encaisser(commande, Paiement.WAVE, 100000, self.gerant, reference='W1')
        self.client.force_login(self.gerant)

    def test_vue_generale(self):
        contexte = self.client.get(reverse('tableau_de_bord')).context
        self.assertEqual(contexte['chiffre_affaires'], 100000)
        self.assertEqual(contexte['marge'], 40000)
        self.assertEqual(contexte['nb_articles'], 2)
        self.assertEqual(contexte['vendues'][0]['nom'], 'Moet')
        self.assertEqual([p.nom for p in contexte['alertes']], ['Moet'])  # 3 restants, seuil 3
        self.assertEqual([p.nom for p in contexte['ruptures']], ['Ruinart'])
        self.assertEqual(contexte['nb_bouteilles'], 3)

    def test_toutes_les_periodes(self):
        for periode in ('soiree', '7j', 'mois', '30j'):
            self.assertEqual(self.client.get(reverse('tableau_de_bord'), {'periode': periode}).status_code, 200)

    def test_accueil_selon_le_role(self):
        self.assertRedirects(self.client.get(reverse('accueil')), reverse('tableau_de_bord'))
        self.client.force_login(User.objects.create_user('awa', password='motdepasse-test'))
        self.assertRedirects(self.client.get(reverse('accueil')), reverse('tables'))
