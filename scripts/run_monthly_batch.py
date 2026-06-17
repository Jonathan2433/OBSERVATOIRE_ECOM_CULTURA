#!/usr/bin/env python
"""Script mensuel de production : classification d'un lot de verbatims.

Charge MDTC + Mopinion, valide, anonymise, nettoie, classe, et génère :
  - le CSV enrichi (toutes colonnes d'origine + colonnes du modèle) ;
  - un CSV séparé pour les cas en revue humaine.

Usage :
    python scripts/run_monthly_batch.py \\
        --mdtc      data/raw/mdtc_poc.xlsx \\
        --mopinion  data/raw/mopinion_poc.xlsx \\
        --output    data/output/classifications_poc.csv \\
        --seuil_revue 0.70
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.inference.batch_processor import process_dataframe  # noqa: E402
from src.inference.human_review_queue import export_review_queue  # noqa: E402
from src.inference.predictor import VerbatimPredictor  # noqa: E402
from src.output.exporter import export_enriched_csv  # noqa: E402
from src.preprocessing.loader import load_for_batch  # noqa: E402
from src.utils import load_config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("run_monthly_batch")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Traitement mensuel des verbatims Cultura.")
    p.add_argument("--mdtc", default=None, help="Fichier Excel MDTC.")
    p.add_argument("--mopinion", default=None, help="Fichier Excel Mopinion.")
    p.add_argument("--output", required=True, help="Chemin du CSV enrichi de sortie.")
    p.add_argument("--seuil_revue", type=float, default=None,
                   help="Seuil de confiance sous lequel un verbatim part en revue humaine.")
    p.add_argument("--review-output", default=None,
                   help="Chemin du CSV de revue humaine (auto-dérivé sinon).")
    p.add_argument("--label", default=None, help="Libellé du lot affiché dans le résumé.")
    p.add_argument("--config", default=None)
    return p.parse_args()


def _derive_review_path(output: Path, override: str | None) -> Path:
    if override:
        return Path(override)
    stem = output.stem
    new_stem = stem.replace("classifications", "revue_humaine") if "classifications" in stem \
        else f"revue_humaine_{stem}"
    return output.with_name(new_stem + output.suffix)


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    if s >= 3600:
        return f"{s // 3600}h {(s % 3600) // 60:02d}min"
    if s >= 60:
        return f"{s // 60}min {s % 60:02d}s"
    return f"{s}s"


def print_summary(report: dict, label: str, csv_path: Path, review_path: Path, n_review: int) -> None:
    bar = "═" * 52
    n = report["n_total"]
    print(f"\n{bar}")
    print(f"  Traitement terminé — {label}")
    print(bar)
    print(f"  Verbatims traités      : {_fmt_int(n)}")
    print(f"  Durée totale           : {_fmt_duration(report['elapsed_seconds'])}")
    rate = report["review_rate"] * 100
    print(f"  Taux de revue humaine  : {rate:.1f}% ({_fmt_int(n_review)} verbatims)")
    print(f"  Vitesse                : {report['seconds_per_verbatim']:.3f} s / verbatim")
    print("  Top 5 thèmes détectés :")
    for i, (theme, cnt) in enumerate(report["top_themes"].items(), 1):
        pct = (cnt / n * 100) if n else 0
        print(f"  {i}. {theme:<34s} {pct:4.1f}%")
    sig = report["signals"]
    print("  Signaux détectés :")
    for name, key in [("Rupture client", "rupture"), ("Churn", "churn"),
                      ("Insatisfaction forte", "insatisfaction_forte")]:
        c = sig[key]
        pct = (c / n * 100) if n else 0
        print(f"  - {name:<26s} {_fmt_int(c):>6}  ({pct:.1f}%)")
    if report.get("pii_masked"):
        total_pii = sum(report["pii_masked"].values())
        print(f"  PII masquées           : {_fmt_int(total_pii)} {dict(report['pii_masked'])}")
    print("  Fichiers générés :")
    print(f"  → {csv_path}")
    print(f"  → {review_path}")
    print(bar)


def main() -> None:
    args = parse_args()
    if not args.mdtc and not args.mopinion:
        raise SystemExit("Fournir au moins --mdtc ou --mopinion.")

    cfg = load_config(args.config)
    if args.seuil_revue is not None:
        cfg["thresholds"]["revue_humaine"] = args.seuil_revue
        logger.info("Seuil de revue humaine = %.2f", args.seuil_revue)

    output_path = Path(args.output)
    review_path = _derive_review_path(output_path, args.review_output)
    label = args.label or output_path.stem.split("_", 1)[-1]

    # --- 1. Chargement + validation des fichiers ------------------------------
    logger.info("Chargement des fichiers sources...")
    df = load_for_batch(args.mdtc, args.mopinion, cfg)
    logger.info("%s verbatims chargés.", _fmt_int(len(df)))

    # --- 2. Chargement des modèles --------------------------------------------
    t0 = time.time()
    predictor = VerbatimPredictor(cfg)
    logger.info("Modèles chargés en %.1f s.", time.time() - t0)

    # --- 3. Traitement par lots -----------------------------------------------
    enriched, report = process_dataframe(df, predictor, cfg)

    # --- 4. Exports ------------------------------------------------------------
    csv_path = export_enriched_csv(enriched, output_path)
    n_review = export_review_queue(enriched, review_path)

    # --- 5. Résumé terminal ----------------------------------------------------
    print_summary(report, label, csv_path, review_path, n_review)


if __name__ == "__main__":
    main()
