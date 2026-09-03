-- ============================================================
-- BookWorld : schéma de la base finale (bookworld_final.db)
-- Exécuté par pipeline.py (fonction load) avant chaque chargement.
-- Chaque table est supprimée puis recréée : le pipeline peut être
-- relancé autant de fois que nécessaire sans créer de doublons.
--
-- Point RGPD : les colonnes customer_first_name et customer_last_name
-- présentes dans sales_raw.csv ne figurent dans AUCUNE table ci-dessous.
-- Elles ne sont pas nécessaires à l'usage final (ventes par pays) et
-- ne sont donc jamais écrites dans la base finale.
-- ============================================================

DROP TABLE IF EXISTS sales_by_country;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS exchange_rates;
DROP TABLE IF EXISTS books;
DROP TABLE IF EXISTS channels;
DROP TABLE IF EXISTS countries;

-- Référentiel des pays (issu de bookworld_reference.db, complété
-- par les codes rencontrés dans les ventes mais absents du référentiel)
CREATE TABLE countries (
    country_code   TEXT PRIMARY KEY,
    country_name   TEXT NOT NULL,
    currency_code  TEXT,
    vat_rate       REAL,
    region         TEXT,
    in_reference   INTEGER NOT NULL DEFAULT 1   -- 1 = présent dans le référentiel, 0 = ajouté par le pipeline
);

-- Référentiel des canaux de vente actifs
CREATE TABLE channels (
    channel_code   TEXT PRIMARY KEY,
    channel_name   TEXT NOT NULL,
    channel_group  TEXT NOT NULL
);

-- Catalogue : un livre par ligne, prix récupéré par scraping (en livres sterling)
CREATE TABLE books (
    book_id         TEXT PRIMARY KEY,
    book_name       TEXT NOT NULL,
    unit_price_gbp  REAL NOT NULL,
    rating          INTEGER,
    availability    TEXT
);

-- Taux de change utilisé pour convertir les montants (API Frankfurter)
CREATE TABLE exchange_rates (
    base_currency    TEXT NOT NULL,
    target_currency  TEXT NOT NULL,
    rate             REAL NOT NULL,
    rate_date        TEXT NOT NULL,
    retrieved_at     TEXT NOT NULL,
    PRIMARY KEY (base_currency, target_currency, rate_date)
);

-- Table de faits : une ligne par commande, nettoyée et valorisée,
-- sans aucune donnée personnelle
CREATE TABLE orders (
    order_id        TEXT PRIMARY KEY,
    order_date      TEXT NOT NULL,
    book_id         TEXT NOT NULL REFERENCES books(book_id),
    country_code    TEXT NOT NULL REFERENCES countries(country_code),
    channel_code    TEXT NOT NULL REFERENCES channels(channel_code),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    discount_rate   REAL NOT NULL CHECK (discount_rate >= 0 AND discount_rate < 1),
    unit_price_gbp  REAL NOT NULL,
    revenue_gbp     REAL NOT NULL,
    revenue_eur     REAL NOT NULL
);

-- Agrégat métier exposé par l'API : les ventes par pays
CREATE TABLE sales_by_country (
    country_code       TEXT PRIMARY KEY REFERENCES countries(country_code),
    country_name       TEXT NOT NULL,
    total_orders       INTEGER NOT NULL,
    total_quantity     INTEGER NOT NULL,
    total_revenue_gbp  REAL NOT NULL,
    total_revenue_eur  REAL NOT NULL
);
