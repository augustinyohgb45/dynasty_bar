from datetime import datetime

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from audit.models import JournalAudit
from stock.models import Categorie, MouvementStock, Produit

from . import services
from .models import Cloture, Commande, Paiement, Table


class BaseCaisse(TestCase):
    def setUp(self):
        categorie = Categorie.objects.create(nom='Champagne')
        self.moet = Produit.objects.create(code='Champ5', nom='Moet', categorie=categorie,
                                           prix_achat=30000, prix_vente=50000)
        self.biere = Produit.objects.create(code='Bier01', nom='Heineken', categorie=categorie, prix_vente=1000)
        for produit, quantite in ((self.moet, 5), (self.biere, 24)):
            MouvementStock.objects.create(produit=produit, type=MouvementStock.ENTREE, quantite=quantite)
        self.table = Table.objects.get(nom='Table 1')  # créée par la migration
        self.serveur = User.objects.create_user('serveur', password='motdepasse-test')
        self.gerant = User.objects.create_superuser('gerant', password='motdepasse-test')
        self.client.force_login(self.serveur)

    def ouvrir(self):
        self.client.post(reverse('ouvrir_table', args=[self.table.pk]))
        return Commande.objects.get(table=self.table, statut=Commande.OUVERTE)

    def ajouter(self, commande, produit, quantite=1):
        return self.client.post(reverse('ajouter', args=[commande.pk]), {'produit': produit.pk, 'quantite': quantite})

    def payer(self, commande, mode, montant, reference=''):
        return self.client.post(reverse('payer', args=[commande.pk]),
                                {'mode': mode, 'montant': montant, 'reference': reference})


class PriseDeCommandeTests(BaseCaisse):
    def test_ouvrir_une_table_deux_fois_reprend_la_meme_commande(self):
        premiere = self.ouvrir()
        self.assertEqual(self.ouvrir(), premiere)
        self.assertEqual(Commande.objects.count(), 1)

    def test_ajout_sort_du_stock_et_regroupe_les_lignes(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet)
        self.ajouter(commande, self.moet, 2)
        self.assertEqual(commande.lignes.count(), 1)
        self.assertEqual(commande.lignes.get().quantite, 3)
        self.assertEqual(commande.total, 150000)
        self.assertEqual(self.moet.stock_actuel, 2)
        vente = MouvementStock.objects.get(type=MouvementStock.VENTE)
        self.assertEqual((vente.quantite, vente.prix_unitaire), (-3, 50000))

    def test_prix_fige_a_la_commande(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet)
        Produit.objects.filter(pk=self.moet.pk).update(prix_vente=60000)
        self.assertEqual(commande.total, 50000)

    def test_stock_insuffisant(self):
        commande = self.ouvrir()
        reponse = self.ajouter(commande, self.moet, 6)
        self.assertContains(self.client.get(reponse.url), 'Stock insuffisant')
        self.assertEqual(commande.total, 0)

    def test_retrait_reserve_au_gerant_et_remet_en_stock(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet, 2)
        ligne = commande.lignes.get()
        self.assertEqual(self.client.post(reverse('retirer', args=[ligne.pk])).status_code, 403)
        self.client.force_login(self.gerant)
        self.client.post(reverse('retirer', args=[ligne.pk]))
        self.assertEqual(self.moet.stock_actuel, 4)
        self.client.post(reverse('retirer', args=[ligne.pk]))
        self.assertFalse(commande.lignes.exists())
        self.assertFalse(MouvementStock.objects.filter(type=MouvementStock.VENTE).exists())


class PaiementTests(BaseCaisse):
    def test_paiement_complet_en_especes_avec_monnaie(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet)
        reponse = self.payer(commande, Paiement.ESPECES, 60000)
        commande.refresh_from_db()
        self.assertEqual(commande.statut, Commande.PAYEE)
        self.assertEqual(commande.paiements.get().montant, 50000)
        # On reste sur la commande soldée, qui propose d'imprimer le reçu
        url = reverse('commande', args=[commande.pk])
        self.assertRedirects(reponse, f"{url}?rendu=10000#addition", fetch_redirect_response=False)
        page = self.client.get(url, {'rendu': 10000})
        self.assertContains(page, 'Commande soldée')
        self.assertContains(page, 'Imprimer le reçu')
        self.assertContains(page, 'Monnaie à rendre : 10')
        recu = self.client.get(reverse('ticket', args=[commande.pk]), {'imprimer': 1})
        self.assertContains(recu, 'window.print()')
        self.assertContains(recu, 'PAYÉ')

    def test_pas_de_recu_tant_que_la_commande_n_est_pas_soldee(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet)
        self.payer(commande, Paiement.ESPECES, 20000)
        self.assertNotContains(self.client.get(reverse('commande', args=[commande.pk])), 'Imprimer le reçu')

    def test_paiement_partage_entre_deux_modes(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet)
        self.payer(commande, Paiement.ESPECES, 20000)
        commande.refresh_from_db()
        self.assertEqual((commande.statut, commande.reste), (Commande.OUVERTE, 30000))
        self.payer(commande, Paiement.MTN_MOMO, 30000, reference='MP2610.1234')
        commande.refresh_from_db()
        self.assertEqual(commande.statut, Commande.PAYEE)

    def test_mobile_money_exige_une_reference_et_pas_de_trop_percu(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet)
        self.payer(commande, Paiement.WAVE, 50000)
        self.payer(commande, Paiement.WAVE, 60000, reference='T123')
        self.assertFalse(Paiement.objects.exists())

    def test_commande_soldee_n_accepte_plus_d_articles(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.biere)
        self.payer(commande, Paiement.ESPECES, 1000)
        self.ajouter(commande, self.biere)
        self.assertEqual(commande.total, 1000)
        # La table est de nouveau libre : une nouvelle commande s'ouvre
        self.assertNotEqual(self.ouvrir(), commande)

    def test_retrait_impossible_sous_le_montant_deja_paye(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet, 2)
        self.payer(commande, Paiement.ESPECES, 80000)
        with self.assertRaises(services.ErreurCaisse):
            services.retirer_produit(commande.lignes.get(), self.gerant)


class AnnulationTests(BaseCaisse):
    def test_annulation_par_le_gerant_remet_en_stock(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet, 2)
        self.assertEqual(self.client.post(reverse('annuler', args=[commande.pk]), {'motif': 'x'}).status_code, 403)
        self.client.force_login(self.gerant)
        self.client.post(reverse('annuler', args=[commande.pk]), {'motif': 'client parti'})
        commande.refresh_from_db()
        self.assertEqual(commande.statut, Commande.ANNULEE)
        self.assertEqual(self.moet.stock_actuel, 5)

    def test_annulation_refusee_apres_un_paiement(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet)
        self.payer(commande, Paiement.ESPECES, 10000)
        with self.assertRaises(services.ErreurCaisse):
            services.annuler(commande, 'erreur', self.gerant)


@override_settings(HEURE_DEBUT_SOIREE=12)
class SoireeTests(BaseCaisse):
    def test_apres_minuit_compte_dans_la_soiree_de_la_veille(self):
        nuit = timezone.make_aware(datetime(2026, 10, 11, 3, 30))
        self.assertEqual(timezone.localtime(services.debut_soiree(nuit)).date().isoformat(), '2026-10-10')
        soir = timezone.make_aware(datetime(2026, 10, 10, 22, 0))
        self.assertEqual(timezone.localtime(services.debut_soiree(soir)).date().isoformat(), '2026-10-10')

    def test_bilan_de_la_soiree(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet)
        self.payer(commande, Paiement.ESPECES, 20000)
        self.payer(commande, Paiement.ORANGE_MONEY, 30000, reference='OM1')
        autre = Commande.objects.create(serveur=self.gerant)
        services.ajouter_produit(autre, self.biere, 2, self.gerant)

        reponse = self.client.get(reverse('ventes'))
        self.assertEqual(reponse.context['chiffre_affaires'], 50000)
        self.assertEqual(reponse.context['total_encaisse'], 50000)
        # Le serveur ne voit pas la commande du gérant
        self.assertEqual(len(reponse.context['ouvertes']), 0)

        self.client.force_login(self.gerant)
        reponse = self.client.get(reverse('ventes'))
        self.assertEqual(len(reponse.context['ouvertes']), 1)
        modes = {cle: montant for cle, _, montant in reponse.context['encaissements']}
        self.assertEqual((modes['especes'], modes['orange_money']), (20000, 30000))

    def test_pages_accessibles(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.moet)
        for url in (reverse('tables'), reverse('commande', args=[commande.pk]),
                    reverse('ticket', args=[commande.pk]), reverse('ventes')):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('tables')).status_code, 302)


class ClotureTests(BaseCaisse):
    def setUp(self):
        super().setUp()
        from . import cloture
        self.cloture = cloture
        self.jour = cloture.soiree_courante()
        commande = self.ouvrir()
        self.ajouter(commande, self.moet)                      # 50 000
        self.payer(commande, Paiement.ESPECES, 20000)
        self.payer(commande, Paiement.MTN_MOMO, 30000, reference='MP1')
        self.client.force_login(self.gerant)

    def cloturer(self, **donnees):
        return self.client.post(reverse('cloturer'), dict({'fond_de_caisse': 10000}, **donnees))

    def test_reservee_au_gerant(self):
        self.client.force_login(self.serveur)
        self.assertEqual(self.client.get(reverse('cloturer')).status_code, 403)

    def test_cloture_avec_ecarts_de_caisse_et_de_stock(self):
        # Espèces attendues : 10 000 de fond + 20 000 encaissés ; il manque 1 000
        reponse = self.cloturer(compte_especes=29000, compte_mtn_momo=30000,
                                **{f'stock_{self.moet.pk}': 3, f'stock_{self.biere.pk}': 24})
        resultat = Cloture.objects.get()
        self.assertRedirects(reponse, reverse('cloture_detail', args=[resultat.pk]))
        self.assertEqual((resultat.chiffre_affaires, resultat.total_encaisse, resultat.ecart_caisse), (50000, 50000, -1000))
        # Moet : 4 en théorie, 3 comptés → 1 bouteille manquante valorisée au prix d'achat
        self.assertEqual(resultat.ecart_stock, -30000)
        self.assertEqual(self.moet.stock_actuel, 3)
        self.assertEqual(self.biere.stock_actuel, 24)
        self.assertEqual(resultat.inventaire.count(), 2)
        journal = JournalAudit.objects.get(action='cloture')
        self.assertIn('Caisse Espèces : attendu 30', journal.details)

    def test_montant_compte_obligatoire_pour_les_modes_encaisses(self):
        reponse = self.cloturer(compte_especes=30000)
        self.assertContains(reponse, 'Indiquez le montant compté pour MTN MoMo')
        self.assertFalse(Cloture.objects.exists())
        self.assertEqual(self.moet.stock_actuel, 4)

    def test_refusee_si_une_addition_est_ouverte(self):
        commande = self.ouvrir()
        self.ajouter(commande, self.biere)
        reponse = self.cloturer(compte_especes=30000, compte_mtn_momo=30000)
        self.assertContains(reponse, 'encore ouvertes')
        self.assertFalse(Cloture.objects.exists())

    def test_soiree_cloturee_bloque_les_commandes_jusqu_a_reouverture(self):
        self.cloturer(compte_especes=30000, compte_mtn_momo=30000)
        resultat = Cloture.objects.get()
        self.assertEqual(resultat.ecart_caisse, 0)
        self.client.force_login(self.serveur)
        self.client.post(reverse('ouvrir_table', args=[self.table.pk]))
        self.assertFalse(Commande.objects.filter(statut=Commande.OUVERTE).exists())
        # Une deuxième clôture de la même soirée renvoie vers le rapport existant
        self.client.force_login(self.gerant)
        self.assertRedirects(self.client.get(reverse('cloturer')), reverse('cloture_detail', args=[resultat.pk]))

        self.client.post(reverse('rouvrir', args=[resultat.pk]), {'motif': 'clients arrivés tard'})
        resultat.refresh_from_db()
        self.assertEqual(resultat.statut, Cloture.ROUVERTE)
        self.assertTrue(JournalAudit.objects.filter(action='reouverture').exists())
        self.client.force_login(self.serveur)
        self.ouvrir()  # les commandes sont de nouveau possibles

    def test_rapport_et_historique(self):
        self.cloturer(compte_especes=30000, compte_mtn_momo=30000)
        resultat = Cloture.objects.get()
        self.assertContains(self.client.get(reverse('cloture_detail', args=[resultat.pk])), 'Comptage de la caisse')
        self.assertContains(self.client.get(reverse('clotures')), 'Rapport')
        self.assertContains(self.client.get(reverse('tables')), 'clôturée')
