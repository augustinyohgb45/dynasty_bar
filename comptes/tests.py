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
        self.assertRedirects(reponse, reverse('stock'))
        self.assertRedirects(self.client.post(reverse('deconnexion')), reverse('connexion'))
        self.assertEqual(self.client.get(reverse('stock')).status_code, 302)

    def test_mauvais_mot_de_passe(self):
        reponse = self.client.post(reverse('connexion'), {'username': 'serveur', 'password': 'faux'})
        self.assertContains(reponse, 'incorrect')
