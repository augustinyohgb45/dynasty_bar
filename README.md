# Dynasty Night Club — gestion du bar

Application web (Django) de gestion du bar : caisse par table ou au comptoir, paiements
(espèces, mobile money, carte), bilan de soirée, et stock (catalogue, réceptions, casses,
offerts, inventaires, alertes). Utilisable depuis un ordinateur, une tablette ou un téléphone
connecté au réseau du club.

## Installation

```bash
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env        # puis renseigner SECRET_KEY
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py createsuperuser   # compte du gérant
```

## Utilisation

- Sur ce PC : `venv\Scripts\python.exe manage.py runserver`, puis http://localhost:8000
- Sur le réseau du club : `venv\Scripts\python.exe lancer_reseau.py` affiche le lien à partager.

## Rôles

| Rôle | Peut faire |
|---|---|
| Personnel | Ouvrir des tables, prendre les commandes, encaisser, imprimer les tickets, voir ses propres ventes de la soirée ; consulter le stock et saisir les réceptions |
| Gérant (administrateur) | Tout, plus : retirer un article d'une commande, annuler une commande non encaissée, voir le bilan de tout le personnel ; casses, offerts, ajustements d'inventaire (motif obligatoire), catalogue, import Excel, tables et comptes |

Les comptes du personnel se créent dans « Comptes et réglages » (administration Django).
## Caisse

- **Tables** : 8 tables en salle et 4 au carré VIP sont créées au départ ; le gérant les renomme,
  ajoute ou désactive dans « Comptes et réglages » > Tables.
- **Commande** : chaque article ajouté sort aussitôt du stock, au prix du moment (un changement de
  prix ultérieur ne modifie pas les commandes déjà passées). Les ventes ne se saisissent plus dans
  « Mouvements » : elles passent toutes par la caisse.
- **Paiement** : espèces (monnaie à rendre calculée), MTN MoMo, Orange Money, Moov Money, Wave ou
  carte (référence de transaction obligatoire). Une addition peut être réglée en plusieurs fois et
  avec plusieurs modes ; la table se libère quand tout est payé.
- **Soirée** : de 12 h à 12 h le lendemain (réglable avec `HEURE_DEBUT_SOIREE` dans `.env`), pour que
  les ventes d'après minuit comptent dans la bonne soirée.

## Import du catalogue Excel

Depuis la page « Importer le catalogue », ou en ligne de commande :

```bash
venv\Scripts\python.exe manage.py importer_catalogue "chemin\gestion_Stock Dynasty.xlsm" --simulation
```

L'import harmonise les catégories, répartit les alcools forts (Whisky, Cognac, Gin…),
écarte les prix d'achat incohérents et ne reprend le stock initial qu'une seule fois.

## Tests

```bash
venv\Scripts\python.exe manage.py test
```
