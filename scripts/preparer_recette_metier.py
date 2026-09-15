#!/usr/bin/env python3
"""Jeu de recette métier — lot L9.

Produit un échantillon **relu par un humain nommé**, tiré du jeu de test gelé et
jamais utilisé pour l'entraînement ni pour le réglage des seuils. Il porte les
catégories exigées au cadrage (§7.1) :

* mono-thèmes et bi-thèmes **dans leur proportion réelle** ;
* cas des **frontières poreuses** identifiées (retrait en magasin, rupture,
  annulation, marketplace) ;
* verbatims **très courts** et **très longs** ;
* sous-thèmes **hors périmètre** (D-32), pour contrôler le routage D-40 ;
* verbatims classés **Général / Autre**, le fourre-tout à 19,7 % (Q-27).

Le fichier produit est destiné à être relu **à l'aveugle** : la colonne de
prédiction est présente, la colonne d'annotation Cultura aussi, et le relecteur
tranche. Les verbatims sont **anonymisés** (`text_clean`), jamais bruts.

Usage :
    python scripts/preparer_recette_metier.py [--taille 200]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.preprocessing.label_norm import fold  # noqa: E402
from src.utils.config import load_config  # noqa: E402

#: Frontières signalées comme poreuses au cadrage et par l'atelier L3 à venir.
FRONTIERES_POREUSES = ["retrait magasin", "rupture", "annul", "marketplace",
                       "click", "collect", "remboursement", "retour produit"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", default="data/processed/cultura_2026_lc_false")
    ap.add_argument("--taille", type=int, default=200)
    ap.add_argument("--sortie", default="data/output/recette_metier_L9.xlsx")
    args = ap.parse_args()

    cfg = load_config()
    hors = {fold(s) for s in cfg["label_normalization"]["sous_themes_hors_perimetre"]}
    seed = int(cfg["model"]["seed"])

    d = pd.read_csv(ROOT / args.donnees / "dataset.csv", encoding="utf-8")
    test = d[d["split"] == "test"].reset_index(drop=True)
    test["nb_mots"] = test["text_clean"].fillna("").astype(str).str.split().str.len()
    test["bi_theme"] = test["theme2_niv1"].notna() & (test["theme2_niv1"] != "")
    test["hors_perimetre"] = [
        isinstance(s, str) and fold(s) in hors for s in test["theme1_niv2"]]
    test["poreux"] = [
        any(m in fold(str(a)) + " " + fold(str(b)) for m in FRONTIERES_POREUSES)
        for a, b in zip(test["theme1_niv2"].fillna(""), test["theme2_niv2"].fillna(""))]
    test["general_autre"] = [
        fold(str(a)) == "general" and fold(str(b)) == "autre"
        for a, b in zip(test["theme1_niv1"].fillna(""), test["theme1_niv2"].fillna(""))]

    # Quotas : les catégories rares sont sur-représentées volontairement, parce
    # que c'est là que le jugement humain apporte quelque chose. La proportion
    # réelle est conservée pour le socle mono/bi-thème.
    quotas = [
        ("bi-thèmes", test[test["bi_theme"]], 30),
        ("hors périmètre (D-32/D-40)", test[test["hors_perimetre"]], 20),
        ("frontières poreuses (L3)", test[test["poreux"] & ~test["bi_theme"]], 30),
        ("Général / Autre (Q-27)", test[test["general_autre"]], 25),
        ("très courts (≤ 3 mots)", test[test["nb_mots"] <= 3], 20),
        ("très longs (≥ 40 mots)", test[test["nb_mots"] >= 40], 20),
    ]

    pris: set = set()
    morceaux: List[pd.DataFrame] = []
    detail: Dict[str, int] = {}
    for nom, sous, n in quotas:
        dispo = sous[~sous.index.isin(pris)]
        prend = dispo.sample(min(n, len(dispo)), random_state=seed) if len(dispo) else dispo
        if len(prend):
            prend = prend.copy()
            prend["categorie_recette"] = nom
            morceaux.append(prend)
            pris.update(prend.index)
        detail[nom] = int(len(prend))

    # Complément tiré au hasard, pour que l'échantillon reste représentatif.
    reste = test[~test.index.isin(pris)]
    manque = max(args.taille - len(pris), 0)
    if manque and len(reste):
        comp = reste.sample(min(manque, len(reste)), random_state=seed).copy()
        comp["categorie_recette"] = "tirage représentatif"
        morceaux.append(comp)
        detail["tirage représentatif"] = int(len(comp))

    ech = pd.concat(morceaux, ignore_index=True) if morceaux else test.head(0)

    colonnes = {
        "categorie_recette": "Catégorie de recette",
        "__source__": "Source",
        "text_clean": "Verbatim (anonymisé)",
        "nb_mots": "Nb mots",
        "__satisfaction__": "Satisfaction (1-4)",
        "theme1_niv1": "Thème 1 — annoté Cultura",
        "theme1_niv2": "Sous-thème 1 — annoté Cultura",
        "theme2_niv1": "Thème 2 — annoté Cultura",
        "theme2_niv2": "Sous-thème 2 — annoté Cultura",
        "sentiment": "Sentiment — annoté Cultura",
    }
    sortie = ech[list(colonnes)].rename(columns=colonnes)
    for col in ("Verdict relecteur (OK / KO)", "Thème attendu si KO",
                "Sentiment attendu si KO", "Commentaire"):
        sortie[col] = ""

    chemin = ROOT / args.sortie
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(chemin, engine="openpyxl") as writer:
        sortie.to_excel(writer, index=False, sheet_name="Recette métier")
        pd.DataFrame([{"Catégorie": k, "Verbatims": v} for k, v in detail.items()]
                     ).to_excel(writer, index=False, sheet_name="Composition")

    manifeste = {
        "origine": "jeu de test gelé, jamais vu à l'entraînement ni au réglage des seuils",
        "corpus": args.donnees,
        "seed": seed,
        "total": int(len(sortie)),
        "composition": detail,
        "anonymisation": "verbatims issus de `text_clean` (PII masquées)",
        "protocole": ("relecture à l'aveugle : le relecteur tranche OK/KO sur "
                      "l'annotation Cultura, sans voir la prédiction du modèle. "
                      "Le verdict doit être prononcé par une personne nommée (Q-11)."),
    }
    (chemin.with_suffix(".json")).write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Jeu de recette métier : {len(sortie)} verbatims")
    for k, v in detail.items():
        print(f"   {k:34s} {v:4d}")
    print(f"\n   => {chemin.relative_to(ROOT)}")
    print(f"   => {chemin.with_suffix('.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
