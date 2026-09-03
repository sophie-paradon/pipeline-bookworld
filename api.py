"""
BookWorld : API REST d'exposition de la base finale (bookworld_final.db).

Endpoints :
  GET /health                          -> état de l'API (sans authentification)
  GET /sales-by-country                -> les ventes agrégées par pays
  GET /sales-by-country/<country_code> -> les ventes d'un seul pays
  GET /books                           -> le catalogue et ses prix

Authentification simple par token : toute route sauf /health exige
l'en-tête  Authorization: Bearer <token>  (ou X-API-Key: <token>).
Le token est lu dans la variable d'environnement BOOKWORLD_API_TOKEN ;
à défaut, la valeur par défaut ci-dessous est utilisée.

Lancement : python api.py   (l'API écoute sur http://127.0.0.1:5000)
"""

import os
import sqlite3
from functools import wraps

import pandas as pd
from flask import Flask, jsonify, request

DB_PATH = "bookworld_final.db"
API_TOKEN = os.environ.get("BOOKWORLD_API_TOKEN", "bookworld-2026-token")

app = Flask(__name__)


# ------------------------------------------------------------
# Outils
# ------------------------------------------------------------

def run_query(query, params=()):
    """Ouvre la base, exécute la requête, referme, renvoie un DataFrame."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def token_required(view):
    """Décorateur : refuse la requête (401) si le token est absent ou faux."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        token = header.replace("Bearer ", "", 1).strip() if header.startswith("Bearer ") else None
        if token is None:
            token = request.headers.get("X-API-Key")
        if token != API_TOKEN:
            return jsonify({"error": "unauthorized",
                            "message": "Token manquant ou invalide. "
                                       "Envoyer l'en-tête Authorization: Bearer <token>."}), 401
        return view(*args, **kwargs)
    return wrapper


# ------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Dit si l'API fonctionne et si la base finale est accessible."""
    try:
        n = run_query("SELECT COUNT(*) AS n FROM sales_by_country")["n"][0]
        return jsonify({"status": "ok", "database": DB_PATH, "countries": int(n)})
    except Exception as e:
        return jsonify({"status": "error", "database": DB_PATH, "detail": str(e)}), 500


@app.route("/sales-by-country", methods=["GET"])
@token_required
def sales_by_country():
    """Les ventes agrégées par pays, classées par chiffre d'affaires en euros."""
    df = run_query(
        """
        SELECT country_code, country_name, total_orders, total_quantity,
               total_revenue_gbp, total_revenue_eur
        FROM sales_by_country
        ORDER BY total_revenue_eur DESC
        """
    )
    return jsonify({"count": len(df), "data": df.to_dict(orient="records")})


@app.route("/sales-by-country/<country_code>", methods=["GET"])
@token_required
def sales_for_one_country(country_code):
    """Les ventes d'un seul pays, par exemple /sales-by-country/FR."""
    df = run_query(
        """
        SELECT country_code, country_name, total_orders, total_quantity,
               total_revenue_gbp, total_revenue_eur
        FROM sales_by_country
        WHERE country_code = ?
        """,
        (country_code.upper(),),
    )
    if df.empty:
        return jsonify({"error": "not_found",
                        "message": f"Aucune vente pour le pays {country_code.upper()}"}), 404
    return jsonify(df.to_dict(orient="records")[0])


@app.route("/books", methods=["GET"])
@token_required
def books():
    """Le catalogue : identifiant, titre, prix en GBP, note et disponibilité."""
    df = run_query("SELECT * FROM books ORDER BY book_id")
    return jsonify({"count": len(df), "data": df.to_dict(orient="records")})


if __name__ == "__main__":
    app.run(debug=False, port=5000)
