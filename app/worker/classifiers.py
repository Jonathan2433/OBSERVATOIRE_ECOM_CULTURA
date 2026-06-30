"""Classifieurs du worker : stub (heuristique) et fabrique vers le modèle réel.

Les deux exposent la même interface que ``src.inference.predictor.VerbatimPredictor``
(``anonymizer``, ``cleaner``, ``batch_size``, ``signal_thresholds``,
``sentiment_labels``, ``predict_cleaned_batch``) afin que la tâche worker soit
agnostique du backend.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from src.inference.predictor import OUTPUT_COLUMNS, _empty_result, build_output  # noqa: F401
from src.preprocessing import Anonymizer, TextCleaner
from src.utils import Taxonomy, resolve_path, sentiment_input

# --- Règles mots-clés (substitut au modèle, pour démonstration sans entraînement) ---
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
                 "plus près de racheter", "je ne rachète", "fini"]


class StubPredictor:
    """Classifieur heuristique (mots-clés) — interface compatible VerbatimPredictor."""

    def __init__(self, cfg: Dict[str, Any]):
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

    def _probs(self, text: str, satisfaction):
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
            niv1[tax.niv1_to_idx["Site / Application"]] = 0.4
        neg = any(w in low for w in NEG_WORDS)
        sent = np.array([0.2, 0.3, 0.5])
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

    def predict_cleaned_batch(self, cleaned: List[str], satisfactions: Optional[list] = None) -> List[Dict[str, Any]]:
        if satisfactions is None:
            satisfactions = [None] * len(cleaned)
        out = []
        for text, sat in zip(cleaned, satisfactions):
            if not text or text.strip() == "":
                out.append(_empty_result(text))
                continue
            niv1, niv2, sent, signals = self._probs(text, sat)
            out.append(build_output(text, niv1, niv2, sent, signals, sat, self.taxonomy,
                                    self.cfg, self.signal_thresholds, self.sentiment_labels))
        return out


def get_predictor(active_model, cfg: Dict[str, Any]):
    """Fabrique le bon backend selon le modèle actif (réel CamemBERT, LM Studio, ou stub)."""
    kind = getattr(active_model, "kind", None)
    if kind == "real":
        from src.inference.predictor import VerbatimPredictor

        return VerbatimPredictor(cfg)
    if kind == "lmstudio":
        from .lmstudio_predictor import LMStudioPredictor

        return LMStudioPredictor(cfg)
    if kind == "claude":
        # Moteur de COMPARAISON/TEST uniquement (jamais activable comme modèle de lot).
        from .claude_predictor import ClaudePredictor

        return ClaudePredictor(cfg)
    return StubPredictor(cfg)
