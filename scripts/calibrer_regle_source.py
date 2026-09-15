#!/usr/bin/env python3
"""Calibration de la marge des règles d'arbitrage contextuel — sur la VALIDATION.

Pourquoi une calibration dédiée
-------------------------------
``avance_max`` avait été calé lors de la campagne d'optimisation, **avant** que
les seuils par thème n'existent. Les deux leviers se recouvrent : les seuils par
thème déplacent déjà l'arbitrage entre `Général` et `Réception commande`, si
bien qu'une marge calée dans l'ancien contexte casse à peu près autant de
décisions qu'elle en corrige.

Ce script mesure, pour chaque marge, ce qui compte réellement :

* combien de décisions de **thème 1** la règle modifie ;
* combien deviennent **justes** et combien deviennent **fausses**.

Un F1 global ne le dit pas : une règle qui corrige 9 cas et en casse 8 affiche
le même F1 qu'une règle qui n'agit pas, alors que ce n'est pas la même chose —
la première ajoute du bruit et une dépendance de production.

Usage :
    python scripts/calibrer_regle_source.py [--split val]

Le résultat est une PROPOSITION : la valeur retenue s'écrit dans
``config.yaml`` (`decision.regles_source`), jamais par ce script.
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for chemin in (str(ROOT), str(ROOT / "scripts")):
    if chemin not in sys.path:
        sys.path.insert(0, chemin)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from evaluer_cultura import _configurer_nouveau_modele  # noqa: E402
from src.evaluation.decision_niv1 import matrice_depuis_decisions  # noqa: E402
from src.inference.decision import PolitiqueDecision, themes_par_verbatim  # noqa: E402
from src.utils.config import load_config, resolve_path  # noqa: E402
from src.utils.taxonomy import Taxonomy  # noqa: E402

MARGES = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.80, 1.00)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="val", choices=["val", "test"],
                    help="val par défaut — calibrer sur le test serait une fuite.")
    ap.add_argument("--donnees", default="data/processed/cultura_2026")
    ap.add_argument("--sortie", default="data/processed/calibrage_regle_source.json")
    args = ap.parse_args()
    if args.split == "test":
        print("⚠️  Calibration demandée sur le TEST : lecture seule, ne pas "
              "reporter la valeur obtenue en configuration.")

    cfg = load_config()
    carte = _configurer_nouveau_modele(cfg)
    taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))
    suffixe = "" if carte.get("lowercase", True) else "_lc_false"
    df = pd.read_csv(ROOT / (args.donnees + suffixe) / "dataset.csv", encoding="utf-8")
    df["text_clean"] = df["text_clean"].fillna("").astype(str)
    jeu = df[df["split"] == args.split].reset_index(drop=True)

    from sklearn.metrics import f1_score

    from src.inference.predictor import VerbatimPredictor

    predictor = VerbatimPredictor(cfg)
    probs = predictor.clf_niv1.predict_proba(jeu["text_clean"].tolist(),
                                             predictor.batch_size)
    y = np.zeros((len(jeu), taxonomy.n_niv1), dtype=int)
    for i, (a, b) in enumerate(zip(jeu["theme1_niv1"], jeu["theme2_niv1"])):
        for t in (a, b):
            if isinstance(t, str) and t in taxonomy.niv1_to_idx:
                y[i, taxonomy.niv1_to_idx[t]] = 1
    garde = y.sum(axis=1) > 0
    yv, pv = y[garde], probs[garde]
    sources = [None if pd.isna(v) else str(v)
               for v, g in zip(jeu["__source__"], garde) if g]
    attendus = [{t for t in (a, b) if isinstance(t, str)}
                for a, b, g in zip(jeu["theme1_niv1"], jeu["theme2_niv1"], garde) if g]

    dec = cfg.get("decision") or {}
    if not (dec.get("regles_source") or {}).get("regles"):
        raise SystemExit("Aucune règle de source déclarée dans `decision.regles_source`.")

    # Référence : la politique complète PRIVÉE de la règle de source.
    sans = dict(cfg)
    sans["decision"] = {k: v for k, v in dec.items() if k != "regles_source"}
    ref = themes_par_verbatim(pv, PolitiqueDecision.depuis_config(sans, taxonomy), sources)
    f1_ref = float(f1_score(yv, matrice_depuis_decisions(ref, taxonomy.n_niv1),
                            average="macro", zero_division=0))

    lignes: List[Dict[str, Any]] = []
    for marge in MARGES:
        variante = deepcopy(dec)
        for regle in variante["regles_source"]["regles"]:
            regle["avance_max"] = marge
        c = dict(cfg)
        c["decision"] = variante
        decisions = themes_par_verbatim(
            pv, PolitiqueDecision.depuis_config(c, taxonomy), sources)
        modif = corrige = casse = 0
        for i, (apres, avant) in enumerate(zip(decisions, ref)):
            if apres == avant:
                continue
            modif += 1
            ok_apres = taxonomy.niv1_labels[apres[0]] in attendus[i]
            ok_avant = taxonomy.niv1_labels[avant[0]] in attendus[i]
            corrige += ok_apres and not ok_avant
            casse += ok_avant and not ok_apres
        f1 = float(f1_score(yv, matrice_depuis_decisions(decisions, taxonomy.n_niv1),
                            average="macro", zero_division=0))
        lignes.append({
            "avance_max": marge, "f1_macro": round(f1, 4),
            "delta_f1_macro": round(f1 - f1_ref, 4),
            "decisions_modifiees": modif, "corrigees": corrige, "cassees": casse,
            "net": corrige - casse,
        })

    # Recommandation : le net le plus élevé, à égalité la marge qui casse le moins.
    meilleur = max(lignes, key=lambda l: (l["net"], -l["cassees"]))
    rapport = {
        "protocole": {
            "jeu": args.split, "n": int(garde.sum()),
            "reference": "politique complète SANS la règle de source",
            "f1_macro_reference": round(f1_ref, 4),
            "seuil_niv1": float(cfg["thresholds"]["classification_niv1"]),
        },
        "balayage": lignes,
        "recommandation": meilleur,
    }
    (ROOT / args.sortie).write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print(f"  CALIBRATION DE LA RÈGLE DE SOURCE — jeu « {args.split} », "
          f"n={garde.sum()}")
    print(f"  Référence sans la règle : F1-macro {f1_ref:.4f}")
    print("=" * 78)
    print(f"\n  {'avance_max':>10} {'F1-macro':>9} {'Δ':>8} {'modifiées':>10} "
          f"{'corrigées':>10} {'cassées':>8} {'net':>5}")
    for l in lignes:
        print(f"  {l['avance_max']:>10} {l['f1_macro']:>9.4f} "
              f"{l['delta_f1_macro']:>+8.4f} {l['decisions_modifiees']:>10} "
              f"{l['corrigees']:>10} {l['cassees']:>8} {l['net']:>+5}")
    print(f"\n  Recommandation : avance_max = {meilleur['avance_max']} "
          f"({meilleur['corrigees']} corrigées, {meilleur['cassees']} cassées)")
    print(f"  => {args.sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
