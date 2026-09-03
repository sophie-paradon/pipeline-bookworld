# BookWorld : pipeline de données et API REST

Projet réalisé pour le bloc de compétences **RNCP 37827BC01** (« réaliser la collecte, le stockage et la mise à disposition des données d'un projet en intelligence artificielle »), formation Data Analyst DataBird.

BookWorld est une librairie en ligne fictive qui vend à l'international. Ses données sont dispersées entre un fichier CSV de commandes, une base SQLite de référentiels, un catalogue à scraper sur le web et une API de taux de change. Ce projet les collecte, les nettoie, les agrège par pays dans une base SQLite finale, puis expose le résultat par une API REST protégée par un token.

```
sales_raw.csv ─────────────┐
bookworld_reference.db ────┤
books.toscrape.com (page 1)┼──►  pipeline.py  ──►  bookworld_final.db  ──►  api.py  ──►  ngrok
API Frankfurter (GBP→EUR) ─┘
```

## 1. Installer les dépendances

Python 3.10 ou plus récent. Depuis le dossier `project` :

```
pip install -r requirements.txt
```

Bibliothèques utilisées : `pandas` (manipulation des tableaux), `requests` (appels web), `beautifulsoup4` (lecture du HTML scrapé), `flask` (API). Le module `sqlite3` est livré avec Python.

## 2. Exécuter le pipeline

```
python pipeline.py
```

Le script enchaîne quatre étapes : extraction des quatre sources, nettoyage et enrichissement, agrégation des ventes par pays, puis création de la base `bookworld_final.db` à partir de `schema_final.sql`. Une connexion Internet est nécessaire pour le scraping et le taux de change. En cas d'échec d'une source, le pipeline s'arrête avec un message explicite (`ERREUR : ...`) plutôt que de produire une base incomplète.

Pour contrôler le résultat :

```
python verifier_base.py
```

## 3. Lancer l'API

```
python api.py
```

L'API écoute sur `http://127.0.0.1:5000`. Pour l'exposer publiquement pendant une démonstration, dans un second terminal : `ngrok http 5000`.

| Endpoint | Authentification | Réponse |
|---|---|---|
| `GET /health` | non | état de l'API et accès à la base |
| `GET /sales-by-country` | oui | ventes agrégées par pays, classées par chiffre d'affaires en euros |
| `GET /sales-by-country/<code>` | oui | les ventes d'un seul pays, par exemple `/sales-by-country/FR` (404 si inconnu) |
| `GET /books` | oui | le catalogue scrapé : titre, prix en GBP, note, disponibilité |

## 4. Utiliser l'authentification par token

Toutes les routes sauf `/health` exigent un token dans l'en-tête `Authorization`. Le token est lu dans la variable d'environnement `BOOKWORLD_API_TOKEN` ; si elle n'est pas définie, la valeur par défaut `bookworld-2026-token` est utilisée.

Définir son propre token avant de lancer l'API (PowerShell) :

```
$env:BOOKWORLD_API_TOKEN = "mon-token-secret"
python api.py
```

Appeler l'API avec le token (PowerShell) :

```
Invoke-RestMethod http://127.0.0.1:5000/sales-by-country -Headers @{ Authorization = "Bearer bookworld-2026-token" }
```

Avec curl :

```
curl.exe -H "Authorization: Bearer bookworld-2026-token" http://127.0.0.1:5000/sales-by-country
```

Sans token, ou avec un token faux, l'API répond `401 Unauthorized` avec un message en JSON. L'en-tête `X-API-Key: <token>` est accepté en alternative.

Le dépôt GitHub est relié en HTTPS ; une clé SSH n'est pas nécessaire pour cloner ou consulter le projet. Pour contribuer par SSH, ajouter sa clé publique dans les réglages GitHub (Settings, SSH and GPG keys), puis utiliser l'adresse `git@github.com:sophie-paradon/pipeline-bookworld.git`.

## 5. Les fichiers du projet

| Fichier | Rôle |
|---|---|
| `pipeline.py` | Le pipeline complet : `extract()`, `transform()`, `load()`, `main()` |
| `api.py` | L'API Flask, ses quatre endpoints et l'authentification par token |
| `queries.sql` | Les requêtes SQL d'extraction depuis le référentiel, version finale lisible |
| `schema_final.sql` | La structure de la base finale (tables, clés primaires et étrangères) |
| `verifier_base.py` | Script de contrôle de la base finale après exécution |
| `requirements.txt` | Les dépendances Python à installer |
| `sales_raw.csv` | Source : 240 commandes brutes (contient des noms de clients, jamais chargés) |
| `bookworld_reference.db` | Source : référentiels pays, canaux et catégories |
| `bookworld_final.db` | Résultat du pipeline (non versionné, régénéré à chaque exécution) |

## 6. Point RGPD

Le fichier brut contient le prénom et le nom des clients. Ces colonnes ne sont pas nécessaires pour produire des ventes par pays : elles sont supprimées dès le début de la transformation et n'apparaissent dans aucune table de `bookworld_final.db`. Le pipeline le vérifie lui-même à la fin du chargement.
