"""
BookWorld : pipeline de données (collecte, nettoyage, agrégation, stockage).

Quatre sources sont collectées :
  1. sales_raw.csv            : les commandes brutes (fichier plat)
  2. bookworld_reference.db   : les référentiels métier (base SQLite)
  3. https://books.toscrape.com/ : le catalogue, première page (scraping)
  4. API Frankfurter          : le taux de change GBP -> EUR (API publique)

Le résultat est une base SQLite finale, bookworld_final.db, dont la
structure est décrite dans schema_final.sql, et qui contient notamment
l'agrégat sales_by_country exposé ensuite par api.py.

Exécution : python pipeline.py
"""

import sys
import re
import sqlite3
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

# --- Constantes du projet ---
SALES_CSV = "sales_raw.csv"
REFERENCE_DB = "bookworld_reference.db"
FINAL_DB = "bookworld_final.db"
SCHEMA_FILE = "schema_final.sql"

CATALOGUE_URL = "https://books.toscrape.com/"
FX_URL = "https://api.frankfurter.dev/v1/latest"
FX_URL_FALLBACK = "https://api.frankfurter.app/latest"
TIMEOUT = 30

# Colonnes du CSV brut qui ne doivent JAMAIS atteindre la base finale (RGPD)
PERSONAL_DATA_COLUMNS = ["customer_first_name", "customer_last_name"]

# Traduction des notes en étoiles du site en nombre
RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


# ============================================================
# 1. EXTRACT : aller chercher les quatre sources
# ============================================================

def extract_sales():
    """Lit le fichier CSV des commandes brutes."""
    try:
        sales = pd.read_csv(SALES_CSV)
    except FileNotFoundError:
        raise RuntimeError(f"Fichier introuvable : {SALES_CSV}. "
                           "Lancer le pipeline depuis le dossier project.")

    expected = ["order_id", "order_date", "book_id", "country_code",
                "channel_code", "quantity", "discount_rate", "book_name"]
    missing = [c for c in expected if c not in sales.columns]
    if missing:
        raise RuntimeError(f"Colonnes manquantes dans {SALES_CSV} : {missing}")

    print("sales_raw :", sales.shape)
    return sales


def extract_reference():
    """Extrait les référentiels depuis la base SQLite.
    Les deux requêtes sont recopiées dans queries.sql."""
    try:
        conn = sqlite3.connect(f"file:{REFERENCE_DB}?mode=ro", uri=True)
    except sqlite3.Error as e:
        raise RuntimeError(f"Impossible d'ouvrir {REFERENCE_DB} : {e}")

    # Requête 1 : avec filtre, seuls les canaux actifs sont conservés
    channels = pd.read_sql_query(
        """
        SELECT channel_code, channel_name, channel_group
        FROM channels
        WHERE is_active = 1
        ORDER BY channel_code
        """,
        conn,
    )

    # Requête 2 : enrichissement, le référentiel des pays complet
    countries = pd.read_sql_query(
        """
        SELECT country_code, country_name, currency_code, vat_rate, region
        FROM countries
        ORDER BY country_code
        """,
        conn,
    )
    conn.close()

    print("channels (actifs) :", channels.shape, "| countries :", countries.shape)
    return channels, countries


def extract_catalogue():
    """Scrape la première page du catalogue books.toscrape.com.
    Retourne un DataFrame : book_name, unit_price_gbp, rating, availability."""
    try:
        response = requests.get(CATALOGUE_URL, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Scraping impossible ({CATALOGUE_URL}) : {e}")

    soup = BeautifulSoup(response.content, "html.parser")
    articles = soup.select("article.product_pod")

    rows = []
    for article in articles:
        title = article.h3.a["title"]
        price_text = article.select_one("p.price_color").get_text()
        price = float(re.sub(r"[^\d.]", "", price_text))   # "£51.77" -> 51.77
        rating_word = article.select_one("p.star-rating")["class"][1]
        availability = article.select_one("p.availability").get_text(strip=True)
        rows.append({
            "book_name": title,
            "unit_price_gbp": price,
            "rating": RATING_WORDS.get(rating_word),
            "availability": availability,
        })

    catalogue = pd.DataFrame(rows)
    if catalogue.empty:
        raise RuntimeError("Aucun livre trouvé sur la page : la structure du site a changé ?")

    print("catalogue scrapé :", catalogue.shape)
    return catalogue


def extract_exchange_rate():
    """Récupère le taux GBP -> EUR du jour via l'API Frankfurter.
    Retourne un dictionnaire : rate, rate_date, retrieved_at."""
    params = {"base": "GBP", "symbols": "EUR"}
    last_error = None
    for url in (FX_URL, FX_URL_FALLBACK):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            rate = float(payload["rates"]["EUR"])
            print(f"taux de change : 1 GBP = {rate} EUR (au {payload['date']}, source {url})")
            return {
                "base_currency": "GBP",
                "target_currency": "EUR",
                "rate": rate,
                "rate_date": payload["date"],
                "retrieved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except (requests.RequestException, KeyError, ValueError) as e:
            last_error = e
            print(f"  avertissement : {url} indisponible ({e}), essai suivant")
    raise RuntimeError(f"Taux de change indisponible : {last_error}")


def extract():
    """Rassemble les quatre sources dans un dictionnaire data."""
    sales = extract_sales()
    channels, countries = extract_reference()
    catalogue = extract_catalogue()
    fx = extract_exchange_rate()

    data = {
        "sales": sales,
        "channels": channels,
        "countries": countries,
        "catalogue": catalogue,
        "fx": fx,
    }
    return data


# ============================================================
# 2. TRANSFORM : nettoyer, enrichir, agréger
# ============================================================

def transform(data):
    sales = data["sales"].copy()
    channels = data["channels"]
    countries = data["countries"].copy()
    catalogue = data["catalogue"]
    fx = data["fx"]

    # --- 2.1 Nettoyage des commandes brutes ---
    n_start = len(sales)

    # Point RGPD : les noms et prénoms sont retirés dès cette étape.
    # Ils ne servent pas à l'agrégation par pays et ne doivent pas être stockés.
    sales = sales.drop(columns=[c for c in PERSONAL_DATA_COLUMNS if c in sales.columns])

    # Harmonisation des textes et des codes
    for col in ["order_id", "book_id", "book_name"]:
        sales[col] = sales[col].astype(str).str.strip()
    for col in ["country_code", "channel_code"]:
        sales[col] = sales[col].astype(str).str.strip().str.upper()

    # Dates au format datetime ; une date illisible devient vide puis est écartée
    sales["order_date"] = pd.to_datetime(sales["order_date"], errors="coerce")

    # Doublons de commande et lignes inexploitables
    sales = sales.drop_duplicates(subset="order_id")
    sales = sales.dropna(subset=["order_id", "order_date", "book_name", "country_code"])
    sales = sales[(sales["quantity"] > 0)]
    sales = sales[(sales["discount_rate"] >= 0) & (sales["discount_rate"] < 1)]

    print(f"nettoyage : {n_start} lignes lues, {len(sales)} conservées, "
          f"{n_start - len(sales)} écartées")

    # --- 2.2 Enrichissement par le catalogue (prix en GBP) ---
    sales = sales.merge(catalogue, on="book_name", how="left")
    sans_prix = sales["unit_price_gbp"].isna().sum()
    if sans_prix > 0:
        titres = sales.loc[sales["unit_price_gbp"].isna(), "book_name"].unique()
        print(f"  avertissement : {sans_prix} commandes sans prix (titres absents du "
              f"catalogue scrapé) sont écartées : {list(titres)}")
        sales = sales.dropna(subset=["unit_price_gbp"])

    # --- 2.3 Enrichissement par le référentiel des pays ---
    countries["in_reference"] = 1
    codes_inconnus = sorted(set(sales["country_code"]) - set(countries["country_code"]))
    if codes_inconnus:
        print(f"  avertissement : codes pays présents dans les ventes mais absents du "
              f"référentiel : {codes_inconnus}. Les commandes sont conservées et le pays "
              f"est marqué comme hors référentiel.")
        complement = pd.DataFrame({
            "country_code": codes_inconnus,
            "country_name": ["Inconnu (hors référentiel)"] * len(codes_inconnus),
            "currency_code": None, "vat_rate": None, "region": None,
            "in_reference": 0,
        })
        countries = pd.concat([countries, complement], ignore_index=True)

    sales = sales.merge(countries[["country_code", "country_name"]], on="country_code", how="left")

    # --- 2.4 Valorisation : montant en GBP puis en EUR ---
    sales["revenue_gbp"] = (sales["quantity"] * sales["unit_price_gbp"]
                            * (1 - sales["discount_rate"])).round(2)
    sales["revenue_eur"] = (sales["revenue_gbp"] * fx["rate"]).round(2)

    # --- 2.5 Table de faits finale (sans donnée personnelle) ---
    orders = sales[[
        "order_id", "order_date", "book_id", "country_code", "channel_code",
        "quantity", "discount_rate", "unit_price_gbp", "revenue_gbp", "revenue_eur",
    ]].copy()
    orders["order_date"] = orders["order_date"].dt.strftime("%Y-%m-%d")
    orders = orders.sort_values("order_id")

    # --- 2.6 Dimension livres : identifiant des ventes + prix du catalogue ---
    books = (
        sales[["book_id", "book_name", "unit_price_gbp", "rating", "availability"]]
        .drop_duplicates(subset="book_id")
        .sort_values("book_id")
    )

    # --- 2.7 Agrégation demandée : les ventes par pays ---
    sales_by_country = (
        sales
        .groupby(["country_code", "country_name"], as_index=False)
        .agg(
            total_orders=("order_id", "nunique"),
            total_quantity=("quantity", "sum"),
            total_revenue_gbp=("revenue_gbp", "sum"),
            total_revenue_eur=("revenue_eur", "sum"),
        )
        .round({"total_revenue_gbp": 2, "total_revenue_eur": 2})
        .sort_values("total_revenue_eur", ascending=False)
    )

    # Contrôle de cohérence : l'agrégat doit conserver le total des commandes
    assert sales_by_country["total_orders"].sum() == orders["order_id"].nunique(), \
        "L'agrégation par pays ne conserve pas le nombre de commandes"

    print("orders :", orders.shape, "| books :", books.shape,
          "| sales_by_country :", sales_by_country.shape)
    print(sales_by_country.to_string(index=False))

    exchange_rates = pd.DataFrame([fx])

    return {
        "countries": countries,
        "channels": channels,
        "books": books,
        "exchange_rates": exchange_rates,
        "orders": orders,
        "sales_by_country": sales_by_country,
    }


# ============================================================
# 3. LOAD : créer la base finale et la remplir
# ============================================================

def load(tables):
    """Crée la base finale à partir de schema_final.sql, puis insère les tables."""
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = sqlite3.connect(FINAL_DB)
    conn.executescript(schema_sql)          # DROP + CREATE de toutes les tables

    # L'ordre respecte les clés étrangères : dimensions d'abord, faits ensuite
    for name in ["countries", "channels", "books", "exchange_rates", "orders", "sales_by_country"]:
        tables[name].to_sql(name, conn, if_exists="append", index=False)

    conn.commit()

    # Contrôle : la base contient bien les tables et les volumes attendus
    print(f"\nBase finale créée : {FINAL_DB}")
    for name in ["countries", "channels", "books", "exchange_rates", "orders", "sales_by_country"]:
        n = pd.read_sql_query(f"SELECT COUNT(*) AS n FROM {name}", conn)["n"][0]
        print(f"  {name:<18} {n:>5} lignes")

    colonnes = pd.read_sql_query("PRAGMA table_info(orders)", conn)["name"].tolist()
    for col in PERSONAL_DATA_COLUMNS:
        assert col not in colonnes, f"Donnée personnelle présente dans la base finale : {col}"
    print("  contrôle RGPD : aucune colonne nominative dans la base finale")

    conn.close()


# ============================================================
# 4. Point d'entrée
# ============================================================

def main():
    print("=== BookWorld : pipeline de données ===")
    try:
        data = extract()
        tables = transform(data)
        load(tables)
    except RuntimeError as e:
        print(f"\nERREUR : {e}")
        sys.exit(1)
    print("\nPipeline terminé avec succès.")


if __name__ == "__main__":
    main()
