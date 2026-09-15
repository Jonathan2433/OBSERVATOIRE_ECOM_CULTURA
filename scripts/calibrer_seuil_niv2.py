#!/usr/bin/env python3
"""Calibrage du seuil de niveau 2 — rendre le routage D-32/D-40 opérant.

Le problème
-----------
D-32 veut que les 16 sous-thèmes sous le seuil de 10 exemples soient **routés en
validation humaine**. D-40 en fixe la forme : `theme*_niv2` vide et revue forcée.

Mesuré à l'itération 1 : **le mécanisme ne se déclenche jamais** (0 verbatim sur
1 128). C'est logique — ces sous-thèmes sont exclus de l'entraînement du niveau 2,
donc leurs neurones ne remportent jamais l'argmax. Un verbatim dont le vrai
sous-thème est hors périmètre reçoit alors un **frère plausible**, sans passer en
revue : exactement ce que D-32 voulait éviter.

Le signal exploitable
---------------------
Quand le vrai sous-thème n'existe pas dans l'espace appris, le modèle **répartit**
sa probabilité entre les frères au lieu de trancher. La confiance du niveau 2,
restreinte aux enfants du thème retenu, est alors basse. C'est ce que mesure
`thresholds.classification_niv2` — déclaré dans la configuration depuis l'origine
et **jamais lu** par l'inférence (dette signalée à l'état des lieux).

Ce script établit la courbe seuil → (détection des hors-périmètre, routage à tort
des dans-périmètre) sur la **validation**, jamais sur le test.

Usage :
    python scripts/calibrer_seuil_niv2.py [--version-niv1 X --version-niv2 Y]
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

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.modeling.architecture import load_classifier  # noqa: E402
from src.preprocessing.label_norm import fold  # noqa: E402
from src.utils.config import load_config, resolve_path  # noqa: E402
from src.utils.taxonomy import Taxonomy  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", default="data/processed/cultura_2026_lc_false")
    ap.add_argument("--version-niv1", default=None,
                    help="horodatage à épingler ; défaut = CURRENT")
    ap.add_argument("--version-niv2", default=None)
    ap.add_argument("--sortie", default="data/processed/calibrage_seuil_niv2.json")
    args = ap.parse_args()

    cfg = load_config()
    for cle in ("model_classifier_niv1", "model_classifier_niv2"):
        cfg["paths"][cle] = cfg["paths"][cle].replace("data/models/",
                                                      "data/models/cultura_2026/")
    cfg["paths"]["taxonomy"] = cfg["cultura_sources"]["taxonomy"]
    tx = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))

    # Épinglage explicite des versions : pendant un entraînement, `CURRENT` peut
    # changer entre deux modèles et l'on mélangerait deux itérations.
    def _dir(cle: str, version: str | None) -> Path:
        base = resolve_path(cfg, cfg["paths"][cle])
        if version:
            chemin = base / version
            if not chemin.is_dir():
                raise SystemExit(f"Version introuvable : {chemin}")
            (base / "CURRENT").write_text(version, encoding="utf-8")
        return base

    d1 = _dir("model_classifier_niv1", args.version_niv1)
    d2 = _dir("model_classifier_niv2", args.version_niv2)
    v1 = (d1 / "CURRENT").read_text(encoding="utf-8").strip()
    v2 = (d2 / "CURRENT").read_text(encoding="utf-8").strip()
    print(f"Versions épinglées : niv1={v1} · niv2={v2}")

    hors = {fold(s) for s in cfg["label_normalization"]["sous_themes_hors_perimetre"]}
    d = pd.read_csv(ROOT / args.donnees / "dataset.csv", encoding="utf-8")
    val = d[(d["split"] == "val") & d["theme1_niv2"].notna()].reset_index(drop=True)
    val["hors_perimetre"] = [fold(s) in hors for s in val["theme1_niv2"]]
    n_hors = int(val["hors_perimetre"].sum())
    print(f"Validation : {len(val)} verbatims annotés en sous-thème, "
          f"dont {n_hors} hors périmètre ({100*n_hors/max(len(val),1):.1f} %)")
    if n_hors == 0:
        print("Aucun cas hors périmètre en validation : calibrage impossible.")
        return 1

    textes = val["text_clean"].fillna("").astype(str).tolist()
    clf1 = load_classifier(resolve_path(cfg, cfg["paths"]["model_classifier_niv1"]),
                           multilabel=True, cfg=cfg)
    clf2 = load_classifier(resolve_path(cfg, cfg["paths"]["model_classifier_niv2"]),
                           multilabel=False, cfg=cfg)
    p1 = clf1.predict_proba(textes, 32)
    p2 = clf2.predict_proba(textes, 32)

    # Confiance du niveau 2 telle que l'inférence la calcule : argmax masqué par
    # les enfants du thème de niveau 1 retenu.
    confiances: List[float] = []
    for i in range(len(val)):
        niv1 = tx.idx_to_niv1[int(np.argmax(p1[i]))]
        _, c = tx.best_niv2_for_niv1(niv1, p2[i])
        confiances.append(float(c))
    val["conf_niv2"] = confiances

    ch = val.loc[val["hors_perimetre"], "conf_niv2"]
    dp = val.loc[~val["hors_perimetre"], "conf_niv2"]
    print(f"\nConfiance niv2 médiane — hors périmètre {ch.median():.4f} · "
          f"dans périmètre {dp.median():.4f}")
    if ch.median() >= dp.median():
        print("  ⚠️ Les hors-périmètre ne sont PAS moins confiants : le seuil de "
              "niveau 2 ne peut pas les distinguer. Voir la conclusion.")

    lignes: List[Dict[str, Any]] = []
    print(f"\n{'seuil':>6s} {'detect. hors-per.':>18s} {'routes a tort':>14s} "
          f"{'total route':>12s}")
    for seuil in [round(0.05 * k, 2) for k in range(1, 20)]:
        detecte = float((ch < seuil).mean())
        a_tort = float((dp < seuil).mean())
        total = float((val["conf_niv2"] < seuil).mean())
        lignes.append({"seuil": seuil, "detection_hors_perimetre": round(detecte, 4),
                       "routage_a_tort": round(a_tort, 4),
                       "part_totale_routee": round(total, 4)})
        print(f"{seuil:6.2f} {detecte*100:17.1f}% {a_tort*100:13.1f}% {total*100:11.1f}%")

    # Un seuil n'est utile que s'il détecte nettement mieux qu'il ne se trompe.
    utiles = [l for l in lignes
              if l["detection_hors_perimetre"] >= 0.50 and l["routage_a_tort"] <= 0.20]
    recommande = min(utiles, key=lambda l: l["routage_a_tort"]) if utiles else None

    rapport = {
        "versions": {"niv1": v1, "niv2": v2},
        "validation": {"n": int(len(val)), "n_hors_perimetre": n_hors},
        "confiance_mediane": {"hors_perimetre": round(float(ch.median()), 4),
                              "dans_perimetre": round(float(dp.median()), 4)},
        "courbe": lignes,
        "seuil_recommande": recommande,
        "critere": ("détection ≥ 50 % des hors-périmètre pour ≤ 20 % de routage à "
                    "tort ; à défaut, le seuil de niveau 2 n'est pas un "
                    "discriminant exploitable et D-32 doit passer par une autre "
                    "voie (calibration de confiance en L7, ou apport d'exemples)."),
    }
    (ROOT / args.sortie).write_text(json.dumps(rapport, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    print(f"\nSeuil recommandé : {recommande if recommande else 'AUCUN — voir critère'}")
    print(f"=> {args.sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
