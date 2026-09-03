"""
Contrôle de la base finale bookworld_final.db après exécution du pipeline.
Lancer :  python verifier_base.py
"""

import sqlite3
import pandas as pd

conn = sqlite3.connect("bookworld_final.db")

tables = pd.read_sql_query(
    "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name", conn
)
print("Tables de la base finale :")
print(tables.to_string(index=False))

print("\nNombre de lignes par table :")
for name in tables["name"]:
    n = pd.read_sql_query(f"SELECT COUNT(*) AS n FROM {name}", conn)["n"][0]
    print(f"  {name:<18} {n:>5}")

print("\nColonnes de la table orders (aucune colonne nominative attendue) :")
print(pd.read_sql_query("PRAGMA table_info(orders)", conn)[["name", "type"]].to_string(index=False))

print("\nVentes par pays :")
print(pd.read_sql_query(
    "SELECT * FROM sales_by_country ORDER BY total_revenue_eur DESC", conn
).to_string(index=False))

print("\nTaux de change utilisé :")
print(pd.read_sql_query("SELECT * FROM exchange_rates", conn).to_string(index=False))

conn.close()
