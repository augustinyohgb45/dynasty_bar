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
| Caisse | Ouvrir des tables, prendre les commandes, encaisser, imprimer les tickets, voir ses propres ventes de la soirée (aucun accès au stock ni à la gestion) |
| Admin | Tout, plus : stock, réceptions, tableau de bord, achats, journal d'audit, retirer un article d'une commande, annuler une commande non encaissée, voir le bilan de tout le personnel ; casses, offerts, ajustements d'inventaire (motif obligatoire), catalogue, import Excel, tables et comptes |

Chaque rôle a sa propre vue : l'« Espace caisse » ne montre que les tables, les commandes et ses
ventes ; l'« Espace admin » donne accès à tout. Après connexion, l'admin arrive sur le tableau de bord
et la caisse sur le plan des tables. Les comptes se créent dans Administration > « Comptes du personnel »
(rôle Caisse ou Admin, activation, nouveau mot de passe).

## Suivi en direct (admin)

Menu Pilotage > « Suivi en direct » : la page s'actualise toute seule toutes les 10 secondes.
- une fiche par membre du personnel ayant travaillé ce soir : encaissé, commandes soldées et en
  cours, actions sensibles, dernière action et pastille verte si active dans les 15 dernières minutes ;
- les commandes en cours avec leur contenu, les derniers encaissements (mode, référence) ;
- le fil des actions de la soirée, filtrable sur une personne (cliquer sur sa fiche).

« Ventes de la soirée » permet aussi à l'admin de filtrer sur un caissier ou une caissière.

## Espace gérance

- **Tableau de bord** (soirée en cours, 7 jours, mois, 30 jours) : chiffre d'affaires, marge estimée,
  boissons vendues, encaissements par mode, ventes par catégorie et par jour, boissons restantes,
  boissons à commander, additions en cours, casses et offerts, derniers achats et dernières activités.
- **Achats** : à chaque approvisionnement, saisir le fournisseur et les boissons achetées (quantité,
  prix unitaire). Le stock et le prix d'achat de chaque boisson sont mis à jour. Une boisson qui
  n'existe pas encore se crée directement depuis l'achat (nom, catégorie, prix de vente).

## Clôture de soirée

Menu Caisse > « Clôture de soirée » (gérant), en fin de service :

1. **Vérifications** : toutes les additions doivent être encaissées ou annulées.
2. **Comptage de la caisse** : saisir le fond de caisse du début de soirée, puis le montant compté
   pour chaque mode (tiroir-caisse, relevés MoMo, Orange Money, Moov Money, Wave, terminal de carte).
   L'écart avec le montant attendu s'affiche en direct.
3. **Inventaire** : compter les bouteilles restantes (une boisson laissée vide n'est pas modifiée).
   Les écarts sont corrigés dans le stock et valorisés au prix d'achat.
4. **Validation** : le bilan est figé (rapport imprimable) et la caisse refuse les nouvelles
   commandes de cette soirée. Le gérant peut rouvrir la soirée avec un motif ; la clôture et la
   réouverture sont inscrites au journal d'audit.

L'historique des clôtures montre, soirée par soirée, les écarts de caisse et de stock.

## Journal d'audit

Chaque action est enregistrée avec son auteur, l'heure et l'appareil (adresse IP) :
ouverture de commande, ajout et retrait d'article, encaissement (mode, référence, monnaie rendue),
annulation (motif), réception, achat, casse, offert, inventaire, import, création, modification et
suppression de boissons, de catégories, de tables ou de comptes, connexions et échecs de connexion.
Les actions sensibles (retraits, annulations, pertes, inventaires, suppressions) sont signalées en
rouge et filtrables. Le journal s'exporte pour Excel et ne peut être ni modifié ni supprimé.

## Caisse

- **Tables** : 8 tables en salle et 4 au carré VIP sont créées au départ ; le gérant les renomme,
  ajoute ou désactive dans « Comptes et réglages » > Tables.
- **Commande** : chaque article ajouté sort aussitôt du stock, au prix du moment (un changement de
  prix ultérieur ne modifie pas les commandes déjà passées). Les ventes ne se saisissent plus dans
  « Mouvements » : elles passent toutes par la caisse.
- **Commande client (sans table)** : bouton « Commande client » en haut de la caisse. Nom du client
  obligatoire, téléphone facultatif ; utile quand toutes les tables sont occupées (un message le
  signale), pour un client debout, en terrasse ou à emporter. Le reçu porte le nom du client.
  « Vente rapide au comptoir » reste disponible pour une consommation sans nom.
- **Paiement** : espèces (monnaie à rendre calculée), MTN MoMo, Orange Money, Moov Money, Wave ou
  carte (référence de transaction obligatoire). Une addition peut être réglée en plusieurs fois et
  avec plusieurs modes ; la table se libère quand tout est payé.
- **Soirée** : de 12 h à 12 h le lendemain (réglable avec `HEURE_DEBUT_SOIREE` dans `.env`), pour que
  les ventes d'après minuit comptent dans la bonne soirée.

## Offres par lot

Une boisson peut être vendue par lot (ex. : « 3 Portes de Bordeaux » à 75 000 F, « 2 Chenet Ice » à
25 000 F) : dans « Nouvelle boisson » ou « Modifier », choisir la boisson de base dans « Lot de » et le
nombre de bouteilles. Un lot n'a pas de stock propre : son stock est le nombre de lots complets
possibles, et chaque lot vendu fait sortir les bouteilles de la boisson de base. Les lots ne
s'achètent pas, ne s'inventorient pas et ne comptent pas dans la valeur du stock.

## Import du catalogue Excel

Depuis la page « Importer le catalogue », ou en ligne de commande :

```bash
venv\Scripts\python.exe manage.py importer_catalogue "chemin\gestion_Stock Dynasty.xlsm" --simulation
```

L'import harmonise les catégories, répartit les alcools forts (Whisky, Cognac, Gin…),
écarte les prix d'achat incohérents et ne reprend le stock initial qu'une seule fois.

## Déploiement en ligne (Vercel + Neon)

L'application tourne aussi sur Vercel, avec une base PostgreSQL Neon (le fichier SQLite ne peut pas
être utilisé en ligne : il serait effacé). En local, sans variable DATABASE_URL, rien ne change.

1. Sur vercel.com : « Add New… > Project », importer le dépôt GitHub dynasty_bar
   (Framework Preset : Other), coller dans « Environment Variables » le contenu du fichier local
   `.env.vercel` (SECRET_KEY, DEBUG=False…), puis « Deploy ».
2. Onglet « Storage » du projet : « Create Database » > Neon, le relier au projet ; Vercel ajoute
   DATABASE_URL. Relancer ensuite un déploiement (« Redeploy »).
3. Créer les tables et copier les données de ce PC vers Neon. Ajouter dans le fichier `.env` local
   la ligne `NEON_DATABASE_URL=postgresql://…` (adresse fournie par Neon), puis :

```bash
venv\Scripts\python.exe -X utf8 manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions -e admin.logentry -o sauvegardes\donnees.json
venv\Scripts\python.exe manage.py migrate --database neon
venv\Scripts\python.exe -X utf8 manage.py loaddata --database neon sauvegardes\donnees.json
```

En ligne, la caisse dépend de la connexion Internet du club ; `lancer_reseau.py` reste la solution
sans Internet (mais les deux bases sont alors séparées).

## Tests

```bash
venv\Scripts\python.exe manage.py test
```
