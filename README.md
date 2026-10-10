# Dynasty Night Club — gestion du bar

Application web (Django) de gestion du stock du bar : catalogue, réceptions, ventes,
casses, offerts, inventaires, alertes de stock bas et de rupture. Utilisable depuis un
ordinateur, une tablette ou un téléphone connecté au réseau du club.

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
| Personnel | Consulter le stock, saisir réceptions et ventes |
| Gérant (administrateur) | Tout, plus : casses, offerts, ajustements d'inventaire (motif obligatoire), catalogue, import Excel, comptes |

Les comptes du personnel se créent dans « Comptes et réglages » (administration Django).

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
