#!/usr/bin/env python
"""Validation de bout en bout du pipeline SANS modèles entraînés (sans torch/GPU).

Ce script vérifie que TOUTE la "plomberie" de production fonctionne sur les vrais
fichiers Excel : chargement -> anonymisation -> nettoyage -> (classification
STUB) -> CSV enrichi -> CSV de revue -> résumé.

Le STUB de classification est une heuristique par mots-clés qui REMPLACE les
modèles CamemBERT non encore entraînés. Il ne reflète PAS la performance du
modèle final ; il sert uniquement à valider l'enchaînement, le format de sortie
et la robustesse du pipeline (utile en CI, sans dépendance lourde).

Usage :
    python scripts/validate_pipeline.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.inference.batch_processor import process_dataframe  # noqa: E402
from src.inference.human_review_queue import export_review_queue  # noqa: E402
from src.inference.predictor import OUTPUT_COLUMNS, build_output  # noqa: E402
from src.output.exporter import export_enriched_csv  # noqa: E402
from src.preprocessing import Anonymizer, TextCleaner, load_for_batch  # noqa: E402
from src.utils import Taxonomy, load_config, resolve_path, sentiment_input  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("validate_pipeline")

# Règles mots-clés -> (niv1, niv2). Heuristique de SUBSTITUTION (pas le modèle).
KEYWORD_RULES = [
    (["retard", "délai", "pas reçu", "toujours pas", "jamais reçu"], "Suivi de commande et livraison", "Délai non respecté"),
    (["notification", "prévenu", "suivi"], "Suivi de commande et livraison", "Absence de notification"),
    (["colis endommagé", "abîmé", "cassé"], "Suivi de commande et livraison", "Colis endommagé"),
    (["paiement", "payer", "carte bancaire"], "Tunnel de vente - Paiement", "Bug paiement"),
    (["code promo", "réduction", "promo"], "Tunnel de vente - Paiement", "Problème code promo / réduction"),
    (["annulé", "annulation"], "Annulation commande", "Annulation sans explication"),
    (["rupture", "plus en stock"], "Disponibilité & Stock", "Rupture de stock non signalée"),
    (["facile", "intuiti", "agréable", "simple"], "Trouver son produit", "Facile"),
    (["recherche", "trouver", "filtre"], "Trouver son produit", "Recherche peu efficace"),
    (["lent", "lenteur", "rame", "chargement"], "Site / Application", "Lenteur du site"),
    (["bug", "plante", "erreur technique"], "Site / Application", "Bug technique"),
    (["navigation", "ergonomie", "mobile"], "Site / Application", "Navigation difficile"),
    (["livraison cher", "frais de port", "frais de livraison"], "Prix de la livraison", "Trop élevé"),
    (["service client", "sav", "joindre"], "Service client", "Difficile à joindre"),
    (["points", "fidélité", "bon d'achat"], "Programme de fidélité", "Bon d'achat non reçu"),
    (["remboursement", "rembourser"], "Retour / Remboursement", "Délai de remboursement trop long"),
    (["click", "collect", "retrait magasin"], "Click & Collect", "Délai de préparation trop long"),
    (["compte", "connexion", "mot de passe"], "Compte client & Connexion", "Problème de connexion / mot de passe"),
    (["email", "newsletter", "mail"], "Communication & Emails Cultura", "Trop d'emails promotionnels"),
    (["qualité", "décevant", "conforme"], "Produit", "Qualité décevante"),
    (["prix", "cher", "tarif"], "Prix produit", "Prix trop élevé vs concurrence"),
]
NEG_WORDS = ["pas", "jamais", "retard", "déçu", "decevant", "décevant", "problème", "bug", "lent",
             "annulé", "perdu", "mauvais", "nul", "honteux", "inadmissible"]
RUPTURE_WORDS = ["ne commanderai plus", "plus jamais", "adieu", "fnac", "amazon", "ne reviendrai",
                 "plus près de racheter", "fini", "je ne rachète"]


class StubPredictor:
    """Imite l'interface de VerbatimPredictor avec une heuristique mots-clés."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))
        self.anonymizer = Anonymizer(cfg)
        self.cleaner = TextCleaner(cfg)
        self.batch_size = cfg["model"]["batch_size_inference"]
        self.sentiment_labels = cfg["sentiment"]["labels"]
        self.signal_thresholds = {
            "rupture": cfg["thresholds"]["signal_rupture"],
            "churn": cfg["thresholds"]["signal_churn"],
            "insatisfaction": cfg["thresholds"]["signal_insatisfaction"],
        }

    def _probs(self, text, satisfaction):
        tax = self.taxonomy
        low = text.lower()
        niv1 = np.full(tax.n_niv1, 0.05)
        niv2 = np.full(tax.n_niv2, 0.02)
        matched = False
        for keys, n1, n2 in KEYWORD_RULES:
            if any(k in low for k in keys):
                niv1[tax.niv1_to_idx[n1]] = max(niv1[tax.niv1_to_idx[n1]], 0.85)
                niv2[tax.niv2_to_idx[n2]] = 0.8
                matched = True
        if not matched:
            niv1[tax.niv1_to_idx["Site / Application"]] = 0.4  # défaut faible confiance
        # Sentiment depuis le score + mots négatifs
        neg = any(w in low for w in NEG_WORDS)
        sent = np.array([0.2, 0.3, 0.5])  # [Nég, Neu, Pos]
        if satisfaction is not None and not (isinstance(satisfaction, float) and np.isnan(satisfaction)):
            s = float(satisfaction)
            if s <= 4 or neg:
                sent = np.array([0.8, 0.15, 0.05])
            elif s >= 7 and not neg:
                sent = np.array([0.05, 0.15, 0.8])
            else:
                sent = np.array([0.2, 0.6, 0.2])
        signals = {
            "rupture": 0.9 if any(w in low for w in RUPTURE_WORDS) else 0.05,
            "churn": 0.7 if neg else 0.1,
            "insatisfaction": 0.7 if neg else 0.1,
        }
        return niv1, niv2, sent, signals

    def predict_cleaned_batch(self, cleaned, satisfactions=None):
        if satisfactions is None:
            satisfactions = [None] * len(cleaned)
        out = []
        for text, sat in zip(cleaned, satisfactions):
            if not text or text.strip() == "":
                from src.inference.predictor import _empty_result
                out.append(_empty_result(text))
                continue
            niv1, niv2, sent, signals = self._probs(text, sat)
            out.append(build_output(text, niv1, niv2, sent, signals, sat, self.taxonomy,
                                    self.cfg, self.signal_thresholds, self.sentiment_labels))
        return out


def main() -> None:
    cfg = load_config()
    raw = resolve_path(cfg, cfg["paths"]["data_raw"])
    out_dir = resolve_path(cfg, cfg["paths"]["output"])

    print("=" * 60)
    print(" VALIDATION PIPELINE (stub mots-clés, sans torch)")
    print("=" * 60)

    df = load_for_batch(raw / "mdtc_poc.xlsx", raw / "mopinion_poc.xlsx", cfg)
    logger.info("Chargé : %d verbatims (MDTC + Mopinion).", len(df))

    predictor = StubPredictor(cfg)
    enriched, report = process_dataframe(df, predictor, cfg)

    csv_path = export_enriched_csv(enriched, out_dir / "_validation_classifications.csv")
    n_review = export_review_queue(enriched, out_dir / "_validation_revue.csv")

    # --- Assertions de format -------------------------------------------------
    assert len(enriched) == len(df), "Nombre de lignes incohérent."
    for col in OUTPUT_COLUMNS:
        assert col in enriched.columns, f"Colonne manquante : {col}"
    assert enriched["nb_themes"].isin([0, 1, 2]).all(), "nb_themes hors {0,1,2}."
    # Hiérarchie : chaque (niv1, niv2) non vide doit exister dans la taxonomie.
    tax = predictor.taxonomy
    bad = 0
    for _, r in enriched.iterrows():
        if r["theme1_niv1"] and not tax.is_valid_pair(r["theme1_niv1"], r["theme1_niv2"]):
            bad += 1
    assert bad == 0, f"{bad} couples (niv1,niv2) hors taxonomie !"

    print(f"\nRÉSULTATS :")
    print(f"  verbatims traités   : {report['n_total']}")
    print(f"  taux revue humaine  : {report['review_rate']*100:.1f}% ({n_review})")
    print(f"  PII masquées        : {report['pii_masked']}")
    print(f"  signaux             : {report['signals']}")
    print(f"  top thèmes          : {list(report['top_themes'].items())[:3]}")
    print(f"  fichiers            : {csv_path.name}, _validation_revue.csv")
    print("\n✅ PIPELINE VALIDE — format de sortie conforme, hiérarchie respectée.")


if __name__ == "__main__":
    main()
