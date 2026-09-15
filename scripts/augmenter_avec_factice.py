#!/usr/bin/env python3
"""Augmente le corpus d'entraînement avec le jeu factice reprojeté — R-1.

Ce que fait ce script
---------------------
Le jeu factice du 12/08 (`data/raw/fake/fake_labeled.xlsx`, 1 445 verbatims) est
annoté dans **l'ancien référentiel** : 1 thème sur 20 correspond au nouveau, 0
sous-thème sur 67. Il est donc inutilisable tel quel.

`config/correspondance_referentiels.yaml` le reprojette sur le référentiel
Cultura 2026. L'intérêt n'est pas le volume — 1 445 verbatims contre 7 501 réels —
mais **ce qu'il contient en abondance et qui manque cruellement au réel** :

    bi-thèmes                289 (réel : 314)
    signal_churn             219 (réel :  64)
    signal_rupture_client     15 (réel :  32)

Trois règles non négociables
----------------------------
1. **Le factice ne va QUE dans le train.** La validation et le test restent
   purement réels : mesurer un modèle sur du texte synthétique ne dirait rien.
2. **Le découpage gelé n'est pas touché.** Les verbatims factices reçoivent le
   split `train` d'office ; aucun identifiant réel ne change de camp.
3. **Le texte est marqué** (`__synthetique__`), pour qu'aucune mesure ultérieure
   ne puisse le confondre avec du réel par inadvertance.

⚠️ Le texte reste **synthétique** : le modèle peut apprendre les tournures du
générateur plutôt que celles des clients. C'est précisément pour cela que
l'évaluation se fait sur le jeu de test réel gelé — si l'augmentation dégrade, la
mesure le dira.

Usage :
    python scripts/augmenter_avec_factice.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from src.preprocessing import Anonymizer, TextCleaner  # noqa: E402
from src.preprocessing.label_norm import fold  # noqa: E402
from src.utils.config import load_config, resolve_path  # noqa: E402
from src.utils.taxonomy import Taxonomy  # noqa: E402

VRAI = {"true", "1", "vrai", "oui", "yes"}


def _bool(v) -> bool:
    return str(v).strip().lower() in VRAI


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="data/processed/cultura_2026_lc_false")
    ap.add_argument("--factice", default="data/raw/fake/fake_labeled.xlsx")
    ap.add_argument("--sortie", default="data/processed/cultura_2026_augmente")
    args = ap.parse_args()

    cfg = load_config()
    cfg["cleaning"]["lowercase"] = False          # aligné sur le corpus de base
    tx = Taxonomy.from_json(resolve_path(cfg, cfg["cultura_sources"]["taxonomy"]))
    corr = yaml.safe_load(
        (ROOT / "config/correspondance_referentiels.yaml").read_text(encoding="utf-8")
    )["correspondance_niv2"]

    base = pd.read_csv(ROOT / args.base / "dataset.csv", encoding="utf-8")
    fake = pd.read_excel(ROOT / args.factice)
    print(f"corpus réel : {len(base)} · jeu factice : {len(fake)}")

    def reprojeter(t, s):
        if not isinstance(t, str) or not isinstance(s, str) or not t.strip() or not s.strip():
            return None, None
        cible = corr.get(f"{t.strip()} | {s.strip()}")
        return (cible[0], cible[1]) if cible else (None, None)

    anonymizer, cleaner = Anonymizer(cfg), TextCleaner(cfg)
    lignes, perdus = [], 0
    for _, r in fake.iterrows():
        t1, s1 = reprojeter(r.get("theme1_niv1"), r.get("theme1_niv2"))
        if t1 is None:
            perdus += 1
            continue
        t2, s2 = reprojeter(r.get("theme2_niv1"), r.get("theme2_niv2"))
        # Un bi-thème dont les deux faces convergent vers le même thème n'est
        # plus un bi-thème après reprojection : on le ramène à un mono-thème.
        if t2 is not None and t2 == t1 and s2 == s1:
            t2 = s2 = None
        masque, _ = anonymizer.anonymize(str(r.get("verbatim_original", "")))
        texte = cleaner.clean(masque)
        if not texte.strip():
            perdus += 1
            continue
        lignes.append({
            "__source__": "FACTICE", "__respondent_id__": str(r.get("verbatim_id")),
            "__field__": "factice", "text_clean": texte,
            "__satisfaction__": r.get("satisfaction_norm"), "__date__": "",
            "split": "train",                      # règle 1 : jamais en val ni test
            "theme1_niv1": t1, "theme1_niv2": s1,
            "theme2_niv1": t2, "theme2_niv2": s2,
            "sentiment": r.get("theme1_sentiment"),
            "signal": None,
            "y_signal_insatisfaction": int(_bool(r.get("signal_insatisfaction_forte"))),
            "y_signal_churn": int(_bool(r.get("signal_churn"))),
            "y_signal_rupture": int(_bool(r.get("signal_rupture_client"))),
            "__synthetique__": True,
        })
    aug = pd.DataFrame(lignes)
    print(f"  reprojetés : {len(aug)} · écartés : {perdus}")

    # --- cibles, recalculées pour les deux populations ------------------------
    hors = {fold(s) for s in cfg["label_normalization"]["sous_themes_hors_perimetre"]}
    base["__synthetique__"] = False
    # Le réel porte un signal à valeur unique ; on le déplie en trois booléens.
    for nom, cle in (("y_signal_insatisfaction", "insatisfaction"),
                     ("y_signal_churn", "churn"), ("y_signal_rupture", "rupture")):
        base[nom] = (base["signal"].astype(str) == cle).astype(int)

    fusion = pd.concat([base, aug], ignore_index=True, sort=False)

    labels = cfg["sentiment"]["labels"]
    idx_sent = {l: i for i, l in enumerate(labels)}
    fusion["y_sentiment"] = [idx_sent.get(s) if isinstance(s, str) else None
                             for s in fusion["sentiment"]]
    fusion["y_niv2"] = [
        tx.niv2_to_idx[s] if (isinstance(s, str) and s in tx.niv2_to_idx
                              and fold(s) not in hors) else None
        for s in fusion["theme1_niv2"]]
    fusion["apprend_niv1"] = fusion["theme1_niv1"].notna() & (fusion["theme1_niv1"] != "")
    fusion["apprend_niv2"] = fusion["y_niv2"].notna()
    fusion["apprend_sentiment"] = fusion["y_sentiment"].notna()
    fusion["apprend_signal"] = True
    fusion["y_signal"] = fusion["y_signal_insatisfaction"]   # compatibilité

    sortie = ROOT / args.sortie
    sortie.mkdir(parents=True, exist_ok=True)
    fusion.to_csv(sortie / "dataset.csv", index=False, encoding="utf-8")
    for f in ("encoders.json",):
        (sortie / f).write_text((ROOT / args.base / f).read_text(encoding="utf-8"),
                                encoding="utf-8")

    tr = fusion[fusion["split"] == "train"]
    bi = lambda df: int((df["theme2_niv1"].notna() & (df["theme2_niv1"] != "")).sum())
    stats = {
        "corpus_reel": int((~fusion["__synthetique__"]).sum()),
        "verbatims_synthetiques_ajoutes": int(fusion["__synthetique__"].sum()),
        "ecartes_a_la_reprojection": perdus,
        "train": {
            "total": int(len(tr)),
            "dont_synthetique": int(tr["__synthetique__"].sum()),
            "bi_themes_total": bi(tr),
            "bi_themes_reels": bi(tr[~tr["__synthetique__"]]),
            "bi_themes_synthetiques": bi(tr[tr["__synthetique__"]]),
        },
        "signaux_train": {
            s: {"reel": int(tr.loc[~tr["__synthetique__"], f"y_signal_{s}"].sum()),
                "synthetique": int(tr.loc[tr["__synthetique__"], f"y_signal_{s}"].sum()),
                "total": int(tr[f"y_signal_{s}"].sum())}
            for s in ("insatisfaction", "churn", "rupture")},
        "val_test_intacts": {
            "val": int((fusion["split"] == "val").sum()),
            "test": int((fusion["split"] == "test").sum()),
            "synthetique_en_val_ou_test": int(
                fusion.loc[fusion["split"].isin(["val", "test"]), "__synthetique__"].sum()),
        },
    }
    (sortie / "dataset_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    assert stats["val_test_intacts"]["synthetique_en_val_ou_test"] == 0, \
        "du texte synthétique a atteint la validation ou le test"
    print("\ncontrôle : aucun verbatim synthétique en validation ni en test ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
