#!/usr/bin/env python3
"""Prépare une variante du corpus avec le CONTEXTE DE COLLECTE en préfixe.

L'idée
------
Un verbatim de deux mots — « Pratique » — est étiqueté `Réception commande /
Retrait magasin` huit fois dans le corpus. Ce n'est pas une erreur d'annotation :
l'annotateur voyait le **formulaire** d'où venait la réponse. Le modèle, lui, ne
voit que le mot, et ne peut pas trancher.

Or ce contexte, nous l'avons : le chargeur produit `__source__` pour chaque
verbatim. Mesuré sur le corpus annoté, il porte **0,508 bit** d'information sur
le thème — une réduction d'entropie de **22,7 %** :

    MDTC post-réception : 64,7 % Réception commande
    Mopinion desktop    : 71,0 % Général
    Mopinion mobile     : 32,0 % Bug   (contre ~5 % ailleurs)

Le préfixe suit exactement le mécanisme déjà éprouvé pour la satisfaction
(`[SATISFACTION 3/4] …`) : du texte, pas de tête custom, compatible ONNX.

Ce n'est **pas** une fuite : la source est connue à l'inférence comme à
l'entraînement — c'est le fichier d'où vient le verbatim. C'est la même
information dont disposait l'annotateur humain.

Usage :
    python scripts/preparer_variante_contexte.py
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


def prefixe_source(source: object) -> str:
    s = str(source).strip()
    return f"[SOURCE {s}] " if s and s.lower() not in ("nan", "none", "") else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="data/processed/cultura_2026_lc_false")
    ap.add_argument("--sortie", default="data/processed/cultura_2026_contexte")
    args = ap.parse_args()

    base = Path(ROOT / args.base)
    d = pd.read_csv(base / "dataset.csv", encoding="utf-8")
    d["text_clean"] = [prefixe_source(s) + str(t)
                       for s, t in zip(d["__source__"], d["text_clean"].fillna(""))]

    sortie = ROOT / args.sortie
    sortie.mkdir(parents=True, exist_ok=True)
    d.to_csv(sortie / "dataset.csv", index=False, encoding="utf-8")
    (sortie / "encoders.json").write_text(
        (base / "encoders.json").read_text(encoding="utf-8"), encoding="utf-8")
    (sortie / "dataset_stats.json").write_text(json.dumps({
        "origine": args.base,
        "modification": "préfixe `[SOURCE <source>] ` ajouté à text_clean",
        "sources": {k: int(v) for k, v in d["__source__"].value_counts().items()},
        "avertissement": ("le découpage gelé est repris tel quel ; seul le texte "
                          "change. L'inférence DEVRA appliquer le même préfixe."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"variante écrite : {sortie.relative_to(ROOT)}  ({len(d)} verbatims)")
    for s, n in d["__source__"].value_counts().items():
        print(f"   {s:20s} {n:5d}")
    print(f"\n   exemple : {d['text_clean'].iloc[0][:90]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
