#!/usr/bin/env python3
"""Ablation des leviers de la couche de décision — un par un, puis en cumulatif.

Pourquoi séparément
-------------------
La mesure cumulative répond à « que gagne-t-on au total ? ». Elle ne répond pas
à « chaque levier mérite-t-il d'être là ? ». Un levier peut être neutre en
cumulatif parce qu'un autre le masque, ou **coûter** sur un thème et gagner sur
un autre. Les deux paires confusables sont d'ailleurs évaluées séparément :
rien ne dit qu'elles se valent.

Un levier qui ne rapporte rien doit sortir de la configuration. Une règle
inactive dans le code de production est une dette, pas une sécurité.

Les probabilités sont calculées UNE FOIS puis rejouées sur chaque configuration :
toutes les lignes portent donc exactement sur la même population.

Usage :
    python scripts/ablation_leviers.py [--split test]
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for chemin in (str(ROOT), str(ROOT / "scripts")):
    if chemin not in sys.path:
        sys.path.insert(0, chemin)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from evaluer_cultura import _configurer_nouveau_modele  # noqa: E402
from src.evaluation.decision_niv1 import (  # noqa: E402
    distribution_nb_themes,
    matrice_depuis_decisions,
    mesures_second_theme,
)
from src.inference.decision import PolitiqueDecision, themes_par_verbatim  # noqa: E402
from src.utils.config import load_config, resolve_path  # noqa: E402
from src.utils.taxonomy import Taxonomy  # noqa: E402


def _sans(dec: Dict[str, Any], *cles: str) -> Dict[str, Any]:
    """Copie du bloc `decision` privée des leviers nommés."""
    return {k: v for k, v in dec.items() if k not in cles}


def _paires(dec: Dict[str, Any], gardees: List[List[str]]) -> Dict[str, Any]:
    """Copie du bloc `decision` où seules certaines paires restent actives."""
    out = deepcopy(dec)
    out["paires_confusables"] = {"actif": bool(gardees), "paires": gardees}
    return out


def configurations(dec: Dict[str, Any]) -> List[tuple]:
    """(libellé, bloc `decision`) — nu, chaque levier seul, puis retraits."""
    toutes = (dec.get("paires_confusables") or {}).get("paires") or []
    contexte = {k: v for k, v in dec.items()
                if k in ("referentiel_attendu", "cibles")}
    cfgs: List[tuple] = [
        ("nu (seuil unique)", dict(contexte)),
        ("seuils par thème seuls", _sans(dec, "regles_source", "paires_confusables")),
        ("arbitrage source seul", _sans(dec, "seuils_par_theme", "paires_confusables")),
        ("paires seules", _sans(dec, "seuils_par_theme", "regles_source")),
    ]
    for paire in toutes:
        cfgs.append((f"paire seule : {paire[0]} / {paire[1]}",
                     _paires(_sans(dec, "seuils_par_theme", "regles_source"), [paire])))
    cfgs.append(("TOUT", dec))
    cfgs.append(("TOUT − arbitrage source", _sans(dec, "regles_source")))
    for paire in toutes:
        restantes = [p for p in toutes if p != paire]
        cfgs.append((f"TOUT − paire {paire[0]} / {paire[1]}", _paires(dec, restantes)))
    return cfgs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["train", "val", "test"])
    ap.add_argument("--donnees", default="data/processed/cultura_2026")
    ap.add_argument("--sortie", default="data/processed/ablation_leviers.json")
    args = ap.parse_args()

    cfg = load_config()
    carte = _configurer_nouveau_modele(cfg)
    taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))

    suffixe = "" if carte.get("lowercase", True) else "_lc_false"
    df = pd.read_csv(ROOT / (args.donnees + suffixe) / "dataset.csv", encoding="utf-8")
    df["text_clean"] = df["text_clean"].fillna("").astype(str)
    jeu = df[df["split"] == args.split].reset_index(drop=True)

    from src.inference.predictor import VerbatimPredictor
    from sklearn.metrics import f1_score

    predictor = VerbatimPredictor(cfg)
    probs = predictor.clf_niv1.predict_proba(jeu["text_clean"].tolist(),
                                             predictor.batch_size)

    y = np.zeros((len(jeu), taxonomy.n_niv1), dtype=int)
    for i, (t1, t2) in enumerate(zip(jeu["theme1_niv1"], jeu["theme2_niv1"])):
        for t in (t1, t2):
            if isinstance(t, str) and t in taxonomy.niv1_to_idx:
                y[i, taxonomy.niv1_to_idx[t]] = 1
    garde = y.sum(axis=1) > 0
    yv, pv = y[garde], probs[garde]
    sources = [None if pd.isna(v) else str(v)
               for v, g in zip(jeu["__source__"], garde) if g]

    dec = cfg.get("decision") or {}
    lignes: List[Dict[str, Any]] = []
    f1_ref: Optional[Dict[str, float]] = None
    for libelle, bloc in configurations(dec):
        variante = dict(cfg)
        variante["decision"] = bloc
        politique = PolitiqueDecision.depuis_config(variante, taxonomy)
        decisions = themes_par_verbatim(pv, politique, sources)
        y_dec = matrice_depuis_decisions(decisions, taxonomy.n_niv1)
        par_theme = {taxonomy.niv1_labels[i]: round(float(v), 4) for i, v in
                     enumerate(f1_score(yv, y_dec, average=None, zero_division=0))}
        if f1_ref is None:
            f1_ref = par_theme
        m = mesures_second_theme(yv, decisions)
        lignes.append({
            "configuration": libelle,
            "f1_macro": round(float(f1_score(yv, y_dec, average="macro",
                                             zero_division=0)), 4),
            "f1_micro": round(float(f1_score(yv, y_dec, average="micro",
                                             zero_division=0)), 4),
            "part_bi_theme": distribution_nb_themes(y_dec)["part_bi_theme"],
            "precision_second_theme": m["precision_second_theme"],
            "taux_faux_second_theme": m["taux_faux_second_theme"],
            "rappel_second_theme": m["rappel_second_theme"],
            "f1_par_theme": par_theme,
            "themes_degrades": sorted(
                (t for t, v in par_theme.items() if v < f1_ref[t] - 1e-9),
                key=lambda t: par_theme[t] - f1_ref[t]),
            "compteurs": {k: v for k, v in politique.compteurs.items() if v},
        })

    part_annotee = round(float((yv.sum(axis=1) >= 2).mean()), 4)
    rapport = {
        "protocole": {
            "jeu": args.split, "n": int(garde.sum()),
            "modele": "cultura_2026 (réentraîné)",
            "seuil_niv1": float(cfg["thresholds"]["classification_niv1"]),
            "part_bi_theme_annotee": part_annotee,
            "note": "Probabilités calculées une seule fois puis rejouées : "
                    "toutes les lignes portent sur la même population.",
        },
        "ablation": lignes,
    }
    (ROOT / args.sortie).write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 100)
    print(f"  ABLATION DES LEVIERS — jeu « {args.split} », n={garde.sum()}, "
          f"seuil {cfg['thresholds']['classification_niv1']}")
    print(f"  Part bi-thèmes ANNOTÉE : {part_annotee*100:.2f} %")
    print("=" * 100)
    base = lignes[0]["f1_macro"]
    print(f"\n  {'configuration':<42} {'F1-mac':>7} {'Δ':>8} {'bi-th':>7} "
          f"{'prec2':>7} {'faux2':>7}  thèmes dégradés")
    for l in lignes:
        d = l["f1_macro"] - base
        deg = ", ".join(l["themes_degrades"][:2]) or "—"
        print(f"  {l['configuration']:<42} {l['f1_macro']:>7.4f} {d:>+8.4f} "
              f"{l['part_bi_theme']:>7.4f} "
              f"{(l['precision_second_theme'] or 0):>7.4f} "
              f"{(l['taux_faux_second_theme'] or 0):>7.4f}  {deg}")
    print(f"\n  => {args.sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
