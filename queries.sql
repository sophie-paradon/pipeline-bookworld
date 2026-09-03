-- ============================================================
-- BookWorld : requêtes SQL d'extraction depuis bookworld_reference.db
-- Version finale et lisible des requêtes utilisées dans pipeline.py
-- (fonction extract_reference). Les requêtes sont recopiées telles
-- quelles dans le script Python.
-- ============================================================

-- 1. Requête avec filtre : les canaux de vente actifs
--    Le canal AFF (Affiliate Network) est inactif dans le référentiel,
--    il est exclu de la base finale.
SELECT
    channel_code,
    channel_name,
    channel_group
FROM channels
WHERE is_active = 1
ORDER BY channel_code;

-- 2. Requête utile à l'enrichissement : le référentiel des pays
--    Elle apporte le nom du pays, la devise, la TVA et la région,
--    qui sont joints aux ventes brutes sur country_code.
--    Aucun filtre sur is_active : le Portugal (PT) est inactif mais
--    a réalisé des ventes sur la période, ses commandes doivent être comptées.
SELECT
    country_code,
    country_name,
    currency_code,
    vat_rate,
    region
FROM countries
ORDER BY country_code;

-- 3. Requête de contrôle (exécutée dans verifier_base.py) :
--    combien de lignes contient chaque table du référentiel ?
SELECT 'countries' AS table_name, COUNT(*) AS nb_rows FROM countries
UNION ALL
SELECT 'channels', COUNT(*) FROM channels
UNION ALL
SELECT 'category_rules', COUNT(*) FROM category_rules;

-- 4. Requête d'analyse sur la base FINALE (bookworld_final.db) :
--    le classement des pays par chiffre d'affaires en euros,
--    telle qu'elle est servie par l'endpoint GET /sales-by-country
SELECT
    country_code,
    country_name,
    total_orders,
    total_quantity,
    total_revenue_gbp,
    total_revenue_eur
FROM sales_by_country
ORDER BY total_revenue_eur DESC;
