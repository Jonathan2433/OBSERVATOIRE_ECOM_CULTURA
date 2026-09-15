#!/usr/bin/env python3
"""Liste de candidats à l'annotation du second thème — mitigation de R-1.

Le constat qui motive ce script
-------------------------------
La précision du second thème plafonne entre 0,18 et 0,29, mesurée sur trois
modèles de qualité croissante. Le facteur limitant n'est pas le modèle mais
l'annotation : **314 bi-thèmes sur 7 501 verbatims (4,4 %)**, dont 35 au test.

Chercher des bi-thèmes au hasard coûte cher : 4 % de rendement. Deux stratégies
plus efficaces sont proposées ici.

**(a) Vérifier les propositions du modèle.** Les verbatims où le modèle propose
un second thème sont exactement ceux où se joue la décision qui échoue. Les faire
trancher par un humain donne de la supervision là où elle manque, pour un volume
réduit — et corrige directement les faux positifs qui polluent les volumes.

**(b) Explorer les candidats les mieux classés.** En triant par probabilité du
second thème, le rendement passe de 4 % à ~14 % sur les 100 premiers : trois fois
et demie moins de lecture pour le même nombre de bi-thèmes trouvés.

Le fichier produit est destiné à une relecture humaine : le second thème proposé
est affiché, le relecteur confirme, corrige, ou supprime.

Usage :
    python scripts/preparer_annotation_2e_theme.py [--verifier 400] [--explorer 400]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for c in (str(ROOT), str(ROOT / "scripts")):
    if c not in sys.path:
        sys.path.insert(0, c)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.evaluation.decision_niv1 import themes_decides  # noqa: E402
from src.modeling.architecture import load_classifier  # noqa: E402
from src.utils.config import load_config, resolve_path  # noqa: E402
from src.utils.taxonomy import Taxonomy  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", default="data/processed/cultura_2026_lc_false")
    ap.add_argument("--verifier", type=int, default=400,
                    help="verbatims où le modèle PROPOSE un second thème")
    ap.add_argument("--explorer", type=int, default=400,
                    help="verbatims les mieux classés sans proposition retenue")
    ap.add_argument("--seuil", type=float, default=0.85)
    ap.add_argument("--sortie", default="data/output/annotation_2e_theme.xlsx")
    args = ap.parse_args()

    cfg = load_config()
    cfg["paths"]["model_classifier_niv1"] = cfg["paths"]["model_classifier_niv1"].replace(
        "data/models/", "data/models/cultura_2026/")
    cfg["paths"]["taxonomy"] = cfg["cultura_sources"]["taxonomy"]
    tx = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))

    d = pd.read_csv(ROOT / args.donnees / "dataset.csv", encoding="utf-8")
    # On n'annote QUE le train et la validation : toucher au test détruirait le
    # jeu de recette gelé, et avec lui toute comparaison future.
    jeu = d[d["split"].isin(["train", "val"])].reset_index(drop=True)
    print(f"Corpus annotable (train + validation) : {len(jeu)} verbatims "
          f"— le test est exclu, il doit rester gelé")

    clf = load_classifier(resolve_path(cfg, cfg["paths"]["model_classifier_niv1"]),
                          multilabel=True, cfg=cfg)
    probs = clf.predict_proba(jeu["text_clean"].fillna("").astype(str).tolist(), 32)

    cap = int(cfg["thresholds"]["max_themes"])
    propose, second, score = [], [], []
    for i in range(len(jeu)):
        idx = themes_decides(probs[i], args.seuil, cap)
        propose.append(len(idx) >= 2)
        second.append(tx.idx_to_niv1[idx[1]] if len(idx) >= 2 else "")
        score.append(float(np.sort(probs[i])[-2]))
    jeu["_propose"] = propose
    jeu["_second_propose"] = second
    jeu["_score_second"] = score
    jeu["_deja_bi"] = jeu["theme2_niv1"].notna() & (jeu["theme2_niv1"] != "")

    # (a) vérifier les propositions, en priorité celles qui contredisent l'annotation
    a = jeu[jeu["_propose"] & ~jeu["_deja_bi"]].sort_values("_score_second", ascending=False)
    a = a.head(args.verifier).copy()
    a["motif"] = "le modèle propose un 2e thème — l'annotation n'en a pas"

    # (b) explorer les mieux classés parmi les non proposés
    reste = jeu[~jeu.index.isin(a.index) & ~jeu["_deja_bi"] & ~jeu["_propose"]]
    b = reste.sort_values("_score_second", ascending=False).head(args.explorer).copy()
    b["motif"] = "candidat probable, sous le seuil"

    ech = pd.concat([a, b], ignore_index=True)
    colonnes = {
        "motif": "Motif de sélection",
        "__source__": "Source",
        "text_clean": "Verbatim (anonymisé)",
        "theme1_niv1": "Thème 1 — annoté",
        "theme1_niv2": "Sous-thème 1 — annoté",
        "_second_propose": "2e thème PROPOSÉ par le modèle",
        "_score_second": "Confiance du 2e thème",
        "sentiment": "Sentiment — annoté",
    }
    out = ech[list(colonnes)].rename(columns=colonnes)
    out["Confiance du 2e thème"] = out["Confiance du 2e thème"].round(4)
    for col in ("Y a-t-il un 2e sujet ? (OUI / NON)", "2e thème retenu",
                "2e sous-thème retenu", "Commentaire"):
        out[col] = ""

    chemin = ROOT / args.sortie
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(chemin, engine="openpyxl") as w:
        out.to_excel(w, index=False, sheet_name="Annotation 2e thème")
        pd.DataFrame([
            {"Stratégie": "Vérifier les propositions du modèle", "Verbatims": len(a)},
            {"Stratégie": "Explorer les candidats probables", "Verbatims": len(b)},
        ]).to_excel(w, index=False, sheet_name="Composition")

    (chemin.with_suffix(".json")).write_text(json.dumps({
        "corpus": "train + validation uniquement — le jeu de test reste gelé",
        "modele_niv1": (resolve_path(cfg, cfg["paths"]["model_classifier_niv1"])
                        / "CURRENT").read_text(encoding="utf-8").strip(),
        "seuil": args.seuil,
        "verifier": int(len(a)),
        "explorer": int(len(b)),
        "bi_themes_deja_annotes": int(jeu["_deja_bi"].sum()),
        "rendement_attendu": ("~14 % sur les 100 premiers contre 4 % au hasard "
                              "(mesuré sur la validation)"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  à vérifier (le modèle propose un 2e thème) : {len(a)}")
    print(f"  à explorer (candidats probables)           : {len(b)}")
    print(f"  bi-thèmes déjà annotés dans ce périmètre   : {int(jeu['_deja_bi'].sum())}")
    print(f"\n  => {chemin.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
