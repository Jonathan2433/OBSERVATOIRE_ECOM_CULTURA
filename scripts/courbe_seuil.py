#!/usr/bin/env python3
"""Courbe de seuil multi-label — livrable du lot L5'.

Établit, sur la **validation**, la relation entre le seuil d'activation du
niveau 1 et les trois grandeurs qui arbitrent son réglage :

* **précision du second thème** — cible ≥ 0,70 *(à valider, Q-9)* ;
* **taux de faux second thème** sur les verbatims réellement mono-thème —
  cible ≤ 0,15 ;
* **rappel du second thème** sur les verbatims réellement bi-thèmes.

Plus le F1 macro et micro **après plafonnement à `max_themes`**, c'est-à-dire sur
la décision que le produit prend réellement (correction L2).

Le seuil retenu est un **arbitrage métier**, pas un optimum mathématique : un
second thème parasite crée du volume fictif dans les tableaux de priorisation de
Cultura, un second thème manquant en retire. Les deux faussent une décision
d'investissement, et pas symétriquement.

⚠️ **Jamais sur le jeu de test.** Le seuil est un paramètre réglé ; le régler sur
le test reviendrait à s'y sur-ajuster et à publier une mesure optimiste.

Usage :
    python scripts/courbe_seuil.py [--version-niv1 20260910_115611]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.evaluation.decision_niv1 import (  # noqa: E402
    courbe_seuil,
    matrice_decidee,
    seuils_par_defaut,
)
from src.modeling.architecture import load_classifier  # noqa: E402
from src.utils.config import load_config, resolve_path  # noqa: E402
from src.utils.taxonomy import Taxonomy  # noqa: E402

#: Valeurs de repli si `decision.cibles` est absent de la configuration —
#: identiques à celles du cadrage (§7.2, famille B, marquées « à valider », Q-9).
CIBLE_PRECISION_2E_DEFAUT = 0.70
CIBLE_FAUX_2E_DEFAUT = 0.15


def _cibles(cfg) -> tuple:
    """Cibles métier, lues en configuration (`decision.cibles`).

    Elles y vivent parce que ce sont des critères d'acceptation, susceptibles
    d'être révisés par le PO — pas des constantes techniques. La précision du
    second thème reste une proposition eXalt non validée (Q-9).
    """
    c = ((cfg.get("decision") or {}).get("cibles") or {})
    return (float(c.get("precision_second_theme", CIBLE_PRECISION_2E_DEFAUT)),
            float(c.get("taux_faux_second_theme", CIBLE_FAUX_2E_DEFAUT)),
            str(c.get("precision_second_theme_statut", "")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", default="data/processed/cultura_2026_lc_false")
    ap.add_argument("--version-niv1", default=None, help="horodatage ; défaut = CURRENT")
    ap.add_argument("--sortie", default="data/processed/courbe_seuil_L5.json")
    ap.add_argument("--split", default="val", choices=["val", "train"],
                    help="jamais `test` : le seuil est un paramètre réglé")
    args = ap.parse_args()

    cfg = load_config()
    cible_precision, cible_faux, statut_precision = _cibles(cfg)
    cfg["paths"]["model_classifier_niv1"] = \
        cfg["paths"]["model_classifier_niv1"].replace("data/models/",
                                                      "data/models/cultura_2026/")
    cfg["paths"]["taxonomy"] = cfg["cultura_sources"]["taxonomy"]
    tx = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))

    base = resolve_path(cfg, cfg["paths"]["model_classifier_niv1"])
    if args.version_niv1:
        if not (base / args.version_niv1).is_dir():
            raise SystemExit(f"Version introuvable : {base / args.version_niv1}")
        (base / "CURRENT").write_text(args.version_niv1, encoding="utf-8")
    version = (base / "CURRENT").read_text(encoding="utf-8").strip()

    d = pd.read_csv(ROOT / args.donnees / "dataset.csv", encoding="utf-8")
    jeu = d[d["split"] == args.split].reset_index(drop=True)
    y = np.zeros((len(jeu), tx.n_niv1), dtype=int)
    for i, (t1, t2) in enumerate(zip(jeu["theme1_niv1"], jeu["theme2_niv1"])):
        for t in (t1, t2):
            if isinstance(t, str) and t in tx.niv1_to_idx:
                y[i, tx.niv1_to_idx[t]] = 1
    m = y.sum(axis=1) > 0
    n_bi = int((y[m].sum(axis=1) >= 2).sum())
    print(f"Modèle niv1 : {version} · jeu « {args.split} » : {int(m.sum())} annotés, "
          f"{n_bi} bi-thèmes ({100*n_bi/max(int(m.sum()),1):.1f} %)")

    clf = load_classifier(base, multilabel=True, cfg=cfg)
    probs = clf.predict_proba(jeu["text_clean"].fillna("").astype(str).tolist(), 32)

    from sklearn.metrics import f1_score

    cap = int(cfg["thresholds"]["max_themes"])
    lignes: List[Dict[str, Any]] = []
    print(f"\n{'seuil':>6s} {'bi-thèmes':>10s} {'préc. 2e':>9s} {'faux 2e':>9s} "
          f"{'rappel 2e':>10s} {'F1-macro':>9s} {'F1-micro':>9s}")
    for r in courbe_seuil(y[m], probs[m], seuils_par_defaut(0.20, 0.90, 0.05), cap):
        yd = matrice_decidee(probs[m], r["seuil"], cap)
        r["f1_macro_apres_plafond"] = round(
            float(f1_score(y[m], yd, average="macro", zero_division=0)), 4)
        r["f1_micro_apres_plafond"] = round(
            float(f1_score(y[m], yd, average="micro", zero_division=0)), 4)
        lignes.append(r)
        p2, f2, r2 = (r["precision_second_theme"], r["taux_faux_second_theme"],
                      r["rappel_second_theme"])
        marque = "  ← cibles B atteintes" if (
            p2 is not None and f2 is not None
            and p2 >= cible_precision and f2 <= cible_faux) else ""
        def _f(v):
            return f"{v:.4f}" if v is not None else "     -"
        print(f"{r['seuil']:6.2f} {r['part_bi_theme']*100:9.1f}% {_f(p2):>9s} "
              f"{_f(f2):>9s} {_f(r2):>10s} {r['f1_macro_apres_plafond']:9.4f} "
              f"{r['f1_micro_apres_plafond']:9.4f}{marque}")

    # Recommandation : parmi les seuils tenant la cible de faux second thème,
    # celui qui maximise le F1-macro de la décision réelle.
    eligibles = [l for l in lignes
                 if l["taux_faux_second_theme"] is not None
                 and l["taux_faux_second_theme"] <= cible_faux]
    recommande: Optional[Dict[str, Any]] = (
        max(eligibles, key=lambda l: l["f1_macro_apres_plafond"]) if eligibles else None)
    precision_atteignable = max(
        (l["precision_second_theme"] for l in lignes
         if l["precision_second_theme"] is not None), default=None)

    rapport = {
        "version_niv1": version,
        "jeu": args.split,
        "n_annotes": int(m.sum()),
        "n_bi_themes": n_bi,
        "max_themes": cap,
        "cibles": {"precision_second_theme": cible_precision,
                   "precision_second_theme_statut": statut_precision,
                   "taux_faux_second_theme": cible_faux},
        "courbe": lignes,
        "seuil_recommande": recommande,
        "precision_second_theme_maximale": precision_atteignable,
        "cible_precision_atteignable": (precision_atteignable is not None
                                        and precision_atteignable >= cible_precision),
    }
    (ROOT / args.sortie).write_text(json.dumps(rapport, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    print(f"\nSeuil recommandé : "
          f"{recommande['seuil'] if recommande else 'AUCUN ne tient la cible de faux 2e'}")
    print(f"Précision maximale du 2e thème, tous seuils : {precision_atteignable} "
          f"(cible {cible_precision}"
          f"{' — ' + statut_precision if statut_precision else ''})")
    print(f"=> {args.sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
