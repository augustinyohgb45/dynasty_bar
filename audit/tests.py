from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from caisse.models import Commande, Table
from stock.models import Categorie, MouvementStock, Produit

from .models import JournalAudit


class JournalCaisseTests(TestCase):
    def setUp(self):
        categorie = Categorie.objects.create(nom='Champagne')
        self.moet = Produit.objects.create(code='Champ5', nom='Moet', categorie=categorie, prix_vente=50000)
        MouvementStock.objects.create(produit=self.moet, type=MouvementStock.ENTREE, quantite=5)
        self.caissiere = User.objects.create_user('awa', password='motdepasse-test')
        self.gerant = User.objects.create_superuser('gerant', password='motdepasse-test')
        self.client.force_login(self.caissiere)
        self.client.post(reverse('ouvrir_table', args=[Table.objects.get(nom='Table 1').pk]))
        self.commande = Commande.objects.get()

    def test_toutes_les_actions_de_caisse_sont_tracees(self):
        self.client.post(reverse('ajouter', args=[self.commande.pk]), {'produit': self.moet.pk, 'quantite': 2})
        self.client.force_login(self.gerant)
        self.client.post(reverse('retirer', args=[self.commande.lignes.get().pk]))
        self.client.force_login(self.caissiere)
        self.client.post(reverse('payer', args=[self.commande.pk]), {'mode': 'especes', 'montant': 60000})

        actions = list(JournalAudit.objects.filter(type_objet='Commande').order_by('id')
                       .values_list('action', 'nom_utilisateur'))
        self.assertEqual(actions, [('ouverture', 'awa'), ('ajout', 'awa'), ('retrait', 'gerant'), ('paiement', 'awa')])
        paiement = JournalAudit.objects.get(action='paiement')
        self.assertEqual(paiement.montant, 50000)
        self.assertIn('monnaie rendue 10', paiement.details)
        self.assertEqual(paiement.adresse_ip, '127.0.0.1')

    def test_annulation_tracee_avec_motif(self):
        self.client.post(reverse('ajouter', args=[self.commande.pk]), {'produit': self.moet.pk})
        self.client.force_login(self.gerant)
        self.client.post(reverse('annuler', args=[self.commande.pk]), {'motif': 'client parti'})
        annulation = JournalAudit.objects.get(action='annulation')
        self.assertIn('client parti', annulation.details)
        self.assertIn('1 × Moet', annulation.details)
        self.assertTrue(annulation.est_sensible)

    def test_modification_du_catalogue_tracee(self):
        self.moet.prix_vente = 55000
        self.moet.save()
        modification = JournalAudit.objects.get(action='modification', type_objet='Produit')
        self.assertIn('Prix de vente : 50000 → 55000', modification.details)

    def test_connexions_et_echecs(self):
        self.client.logout()
        self.client.post(reverse('connexion'), {'username': 'awa', 'password': 'faux'})
        self.client.post(reverse('connexion'), {'username': 'awa', 'password': 'motdepasse-test'})
        self.assertTrue(JournalAudit.objects.filter(action='echec_connexion', objet='awa').exists())
        self.assertTrue(JournalAudit.objects.filter(action='connexion', nom_utilisateur='awa').exists())


class PageJournalTests(TestCase):
    def setUp(self):
        self.gerant = User.objects.create_superuser('gerant', password='motdepasse-test')
        self.caissiere = User.objects.create_user('awa', password='motdepasse-test')
        JournalAudit.objects.create(action='retrait', nom_utilisateur='awa', objet='VIP 1 #00001', details='1 × Moet')
        JournalAudit.objects.create(action='paiement', nom_utilisateur='awa', objet='VIP 1 #00001', montant=50000)

    def test_reserve_au_gerant(self):
        self.client.force_login(self.caissiere)
        self.assertEqual(self.client.get(reverse('journal')).status_code, 403)

    def test_filtres_et_export(self):
        self.client.force_login(self.gerant)
        reponse = self.client.get(reverse('journal'), {'sensibles': '1'})
        self.assertEqual(reponse.context['page_journal'].paginator.count, 1)
        export = self.client.get(reverse('journal'), {'export': 'csv'})
        self.assertEqual(export['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('Retrait', export.content.decode('utf-8'))

    def test_journal_non_modifiable_dans_l_administration(self):
        self.client.force_login(self.gerant)
        entree = JournalAudit.objects.first()
        self.assertEqual(self.client.get(reverse('admin:audit_journalaudit_delete', args=[entree.pk])).status_code, 403)


class ChargementDeDonneesTests(TestCase):
    def test_loaddata_n_ecrit_rien_au_journal(self):
        """La copie des données vers la base en ligne ne doit pas créer de fausses actions."""
        import json
        import os
        import tempfile

        from django.core.management import call_command

        donnees = [{'model': 'stock.categorie', 'pk': 50, 'fields': {'nom': 'Soft', 'ordre': 13}}]
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(donnees, f)
        try:
            call_command('loaddata', f.name, verbosity=0)
        finally:
            os.unlink(f.name)
        self.assertFalse(JournalAudit.objects.exists())
