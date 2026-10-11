from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class ConnexionTests(TestCase):
    def setUp(self):
        User.objects.create_user('serveur', password='motdepasse-test')

    def test_page_protegee_redirige_vers_la_connexion(self):
        reponse = self.client.get(reverse('stock'))
        self.assertRedirects(reponse, reverse('connexion') + '?next=' + reverse('stock'))

    def test_connexion_puis_deconnexion(self):
        reponse = self.client.post(reverse('connexion'), {'username': 'serveur', 'password': 'motdepasse-test'})
        self.assertRedirects(reponse, reverse('accueil'), fetch_redirect_response=False)
        self.assertRedirects(self.client.post(reverse('deconnexion')), reverse('connexion'))
        self.assertEqual(self.client.get(reverse('stock')).status_code, 302)

    def test_mauvais_mot_de_passe(self):
        reponse = self.client.post(reverse('connexion'), {'username': 'serveur', 'password': 'faux'})
        self.assertContains(reponse, 'incorrect')


class VuesSelonLeRoleTests(TestCase):
    """La caisse et l'admin n'ont pas la même vue."""
    PAGES_ADMIN = ['tableau_de_bord', 'journal', 'stock', 'mouvements', 'achat_nouveau', 'achats',
                   'produit_nouveau', 'importer', 'cloturer', 'clotures', 'personnel', 'compte_nouveau']

    def setUp(self):
        self.caisse = User.objects.create_user('awa', password='motdepasse-test')
        self.admin = User.objects.create_superuser('patron', password='motdepasse-test')

    def test_la_caisse_n_accede_qu_a_la_caisse(self):
        self.client.force_login(self.caisse)
        self.assertRedirects(self.client.get(reverse('accueil')), reverse('tables'))
        for nom in ('tables', 'ventes'):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 200, nom)
        for nom in self.PAGES_ADMIN:
            self.assertEqual(self.client.get(reverse(nom)).status_code, 403, nom)

    def test_menu_de_la_caisse(self):
        self.client.force_login(self.caisse)
        page = self.client.get(reverse('tables')).content.decode()
        self.assertIn('Espace caisse', page)
        self.assertIn('Mes ventes de la soirée', page)
        for absent in ('Tableau de bord', 'Journal d&#x27;audit', 'État du stock', 'Nouvel achat', 'Comptes du personnel'):
            self.assertNotIn(absent, page)

    def test_l_admin_voit_tout(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse('accueil')), reverse('tableau_de_bord'))
        page = self.client.get(reverse('tables')).content.decode()
        self.assertIn('Espace admin', page)
        for nom in self.PAGES_ADMIN:
            self.assertEqual(self.client.get(reverse(nom)).status_code, 200, nom)

    def test_page_de_refus_explicite(self):
        self.client.force_login(self.caisse)
        reponse = self.client.get(reverse('tableau_de_bord'))
        self.assertContains(reponse, "Accès réservé à l'admin", status_code=403)


class ComptesDuPersonnelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('patron', password='motdepasse-test')
        self.client.force_login(self.admin)

    def test_creer_un_compte_caisse(self):
        reponse = self.client.post(reverse('compte_nouveau'), {
            'username': 'awa', 'first_name': 'Awa', 'last_name': 'Koné', 'role': 'caisse',
            'password1': 'Un-mot-de-passe-solide-42', 'password2': 'Un-mot-de-passe-solide-42'})
        self.assertRedirects(reponse, reverse('personnel'))
        awa = User.objects.get(username='awa')
        self.assertFalse(awa.is_superuser)
        self.assertTrue(awa.check_password('Un-mot-de-passe-solide-42'))

    def test_promouvoir_desactiver_et_changer_le_mot_de_passe(self):
        awa = User.objects.create_user('awa', password='ancien-mot-de-passe-1')
        url = reverse('compte_modifier', args=[awa.pk])
        self.client.post(url, {'enregistrer': '1', 'first_name': 'Awa', 'last_name': '', 'role': 'admin', 'is_active': 'on'})
        awa.refresh_from_db()
        self.assertTrue(awa.is_superuser)
        self.client.post(url, {'enregistrer': '1', 'first_name': 'Awa', 'last_name': '', 'role': 'caisse'})
        awa.refresh_from_db()
        self.assertFalse(awa.is_superuser)
        self.assertFalse(awa.is_active)
        self.client.post(url, {'mot_de_passe': '1', 'new_password1': 'Nouveau-mot-de-passe-77',
                               'new_password2': 'Nouveau-mot-de-passe-77'})
        awa.refresh_from_db()
        self.assertTrue(awa.check_password('Nouveau-mot-de-passe-77'))

    def test_l_admin_ne_peut_pas_se_retirer_ses_droits(self):
        url = reverse('compte_modifier', args=[self.admin.pk])
        reponse = self.client.post(url, {'enregistrer': '1', 'first_name': '', 'last_name': '', 'role': 'caisse'})
        self.assertContains(reponse, 'propres droits')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser and self.admin.is_active)
