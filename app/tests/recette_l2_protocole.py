#!/usr/bin/env python3
"""Recette automatisée L2 — protocole d'évaluation sans fuite.

Contrôle les deux invariants du lot :

1. **Aucune fuite entre train, validation et test.** Le split porte sur le texte
   unique, jamais sur la ligne, et le contrôle est bloquant.
2. **Le F1 de niveau 1 est calculé après plafonnement à `max_themes`**, c'est-à-dire
   sur la décision que le produit prend réellement.

Ne charge aucun modèle : torch n'est pas requis.

Usage :
    python app/tests/recette_l2_protocole.py

Code de sortie : 0 si aucun ÉCHEC, 1 sinon.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import List, Tuple

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.evaluation.decision_niv1 import (  # noqa: E402
    distribution_nb_themes,
    matrice_decidee,
    precision_second_theme,
    themes_decides,
)
from src.preprocessing.cultura_loader import charger_cultura  # noqa: E402
from src.training.split_sans_fuite import (  # noqa: E402
    FuiteDetectee,
    cle_texte,
    rapport_split,
    split_par_texte_unique,
    verifier_absence_de_fuite,
)
from src.utils.config import load_config  # noqa: E402

_RESULTS: List[Tuple[str, str, str]] = []


def section(label: str) -> None:
    _RESULTS.append(("--", label, ""))


def check(cond: bool, label: str, detail: str = "") -> bool:
    _RESULTS.append(("OK" if cond else "ÉCHEC", label, detail))
    return cond


def skip(label: str, detail: str = "") -> None:
    _RESULTS.append(("SKIP", label, detail))


def main() -> int:
    cfg = load_config()

    # ---------------------------------------------------------------- #
    section("Décision de niveau 1 — plafonnement à max_themes (§7.1 point 6)")
    # ---------------------------------------------------------------- #
    p = np.array([0.90, 0.60, 0.40, 0.10])
    check(themes_decides(p, 0.35, 2) == [0, 1],
          "le plafond `max_themes` tronque bien la liste des thèmes activés",
          f"3 thèmes au-dessus du seuil, {len(themes_decides(p, 0.35, 2))} retenus")
    check(themes_decides(np.array([0.10, 0.20, 0.05]), 0.35, 2) == [1],
          "aucun thème au-dessus du seuil → repli sur l'argmax (toujours ≥ 1 thème)")
    check(themes_decides(np.array([0.9, 0.8]), 0.35, 1) == [0],
          "`max_themes = 1` ne retourne qu'un seul thème")

    # Sur-activation typique : le seuillage seul émet plus de thèmes que la décision.
    rng = np.random.default_rng(0)
    probs = rng.uniform(0.3, 0.9, size=(200, 11))
    seuil, cap = 0.35, 2
    avant = (probs >= seuil).astype(int).sum(axis=1).mean()
    apres = matrice_decidee(probs, seuil, cap).sum(axis=1).mean()
    check(apres <= cap < avant,
          "le F1 avant/après plafond porte sur des décisions différentes",
          f"{avant:.2f} thèmes activés au seuil seul vs {apres:.2f} après plafond")

    y_true = np.zeros((200, 11), int)
    for i in range(200):
        y_true[i, rng.integers(0, 11)] = 1
    st = precision_second_theme(y_true, probs, seuil, cap)
    check({"precision_second_theme", "taux_faux_second_theme",
           "rappel_second_theme"} <= set(st),
          "les métriques du second thème sont calculables (§7.2 famille B)",
          f"n bi-thèmes annotés = {st['verbatims_bi_themes_annotes']}")
    d = distribution_nb_themes(matrice_decidee(probs, seuil, cap))
    check(abs(d["part_mono_theme"] + d["part_bi_theme"] - 1.0) < 1e-9,
          "la distribution du nombre de thèmes est cohérente (EF-4)",
          f"{d['part_bi_theme']*100:.1f} % de sorties bi-thèmes")

    # ---------------------------------------------------------------- #
    section("Contrôle de non-fuite — sur cas construits")
    # ---------------------------------------------------------------- #
    fuite = pd.DataFrame({
        "__text_raw__": ["le colis est arrivé cassé", "Le Colis est arrivé cassé  ", "autre"],
        "split": ["train", "test", "train"],
    })
    try:
        verifier_absence_de_fuite(fuite)
        check(False, "une fuite est détectée et bloque", "aucune exception levée")
    except FuiteDetectee:
        check(True, "une fuite est détectée et bloque",
              "y compris sur variantes de casse et d'espaces")

    propre = pd.DataFrame({
        "__text_raw__": ["aaa", "aaa", "bbb"],
        "split": ["train", "train", "test"],
    })
    try:
        verifier_absence_de_fuite(propre)
        check(True, "un découpage propre passe le contrôle")
    except FuiteDetectee as exc:
        check(False, "un découpage propre passe le contrôle", str(exc))

    # ---------------------------------------------------------------- #
    section("Split de la livraison réelle du 09/09")
    # ---------------------------------------------------------------- #
    try:
        df, _ = charger_cultura(cfg)
    except Exception as exc:  # noqa: BLE001
        skip("split de la livraison réelle", f"{type(exc).__name__}: {exc}")
        return _bilan()

    sp = split_par_texte_unique(df, cfg)      # lève FuiteDetectee si fuite
    rap = rapport_split(sp)
    check(True, "le split de la livraison réelle passe le contrôle bloquant",
          f"{rap['lignes']} lignes · {rap['textes_uniques']} textes uniques · "
          f"{rap['taux_de_doublons']*100:.1f} % de doublons")

    ens = {s: {cle_texte(t) for t in sp[sp["split"] == s]["__text_raw__"]}
           for s in ("train", "val", "test")}
    inters = (len(ens["train"] & ens["val"]) + len(ens["train"] & ens["test"])
              + len(ens["val"] & ens["test"]))
    check(inters == 0,
          "l'intersection des textes entre les trois splits est vide",
          f"intersections : {inters}")

    conf = cfg["dataset"]
    ecarts = []
    for nom, cible in (("train", conf["split_train"]), ("val", conf["split_val"]),
                       ("test", conf["split_test"])):
        obtenu = rap["par_split"][nom]["part"]
        if abs(obtenu - cible) > 0.02:
            ecarts.append(f"{nom}: {obtenu:.3f} vs {cible}")
    check(not ecarts, "les proportions 70/15/15 sont respectées au niveau des lignes",
          "; ".join(ecarts) or
          " · ".join(f"{n} {rap['par_split'][n]['part']*100:.2f} %"
                     for n in ("train", "val", "test")))

    sp2 = split_par_texte_unique(df, cfg)
    check(bool((sp["split"].values == sp2["split"].values).all()),
          "le split est déterministe à seed fixe (ENF-7)")

    # Stratification : la composition thématique doit rester comparable.
    ref = sp[sp["theme1_niv1"].notna()]["theme1_niv1"].value_counts(normalize=True)
    pires = []
    for s in ("train", "val", "test"):
        sub = sp[(sp["split"] == s) & sp["theme1_niv1"].notna()]["theme1_niv1"]
        part = sub.value_counts(normalize=True)
        for theme in ref.index[:5]:
            ecart = abs(part.get(theme, 0.0) - ref[theme])
            if ecart > 0.05:
                pires.append(f"{s}/{theme}: {ecart:.3f}")
    check(not pires, "la stratification par thème de niveau 1 est préservée",
          "; ".join(pires))

    # ---------------------------------------------------------------- #
    section("Ce que produirait un split par ligne — mesure de référence")
    # ---------------------------------------------------------------- #
    rng2 = random.Random(int(cfg.get("model", {}).get("seed", 42)))
    ordre = list(range(len(df)))
    rng2.shuffle(ordre)
    n = len(df)
    bornes = (int(0.70 * n), int(0.85 * n))
    naif = [None] * n
    for rang, pos in enumerate(ordre):
        naif[pos] = ("train" if rang < bornes[0]
                     else "val" if rang < bornes[1] else "test")
    naive = df.copy()
    naive["split"] = naif
    textes_train = {cle_texte(t) for t in naive[naive["split"] == "train"]["__text_raw__"]}
    test_rows = naive[naive["split"] == "test"]
    contamines = sum(1 for t in test_rows["__text_raw__"] if cle_texte(t) in textes_train)
    taux = contamines / max(len(test_rows), 1)
    check(taux > 0,
          "un split par ligne produirait bien une fuite — d'où l'invariant",
          f"{contamines}/{len(test_rows)} lignes de test contaminées "
          f"({taux*100:.1f} %) ; prototype : 99,6 %")
    try:
        verifier_absence_de_fuite(naive)
        check(False, "le contrôle rejette le split par ligne", "aucune exception")
    except FuiteDetectee:
        check(True, "le contrôle rejette le split par ligne")

    return _bilan()


def _bilan() -> int:
    print("=" * 78)
    print("  RECETTE L2 — protocole d'évaluation sans fuite")
    print("=" * 78)
    fails = oks = skips = 0
    for status, label, detail in _RESULTS:
        if status == "--":
            print(f"\n▸ {label}")
            continue
        icon = {"OK": "✅", "ÉCHEC": "❌", "SKIP": "⏭️ "}[status]
        line = f"  {icon} {label}"
        if detail and status in ("ÉCHEC", "SKIP"):
            line += f"  →  {detail}"
        elif detail:
            line += f"  ({detail})"
        print(line)
        oks += status == "OK"
        fails += status == "ÉCHEC"
        skips += status == "SKIP"
    print("\n" + "-" * 78)
    print(f"  Bilan : {oks} OK · {fails} ÉCHEC · {skips} SKIP")
    print("-" * 78)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
