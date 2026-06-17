"""Pipeline d'inférence complet pour un (ou plusieurs) verbatim(s).

Sépare volontairement DEUX responsabilités :
  - ``build_output`` : LOGIQUE DE DÉCISION PURE (numpy/python, sans torch).
    Prend les probabilités brutes des modèles et applique seuils, contrainte
    hiérarchique (masquage niv.2), plafond à 2 thèmes, règles de signaux,
    agrégation de confiance et routage en revue humaine. Testable isolément.
  - ``VerbatimPredictor`` : ORCHESTRATION (charge les modèles, anonymise,
    nettoie, tokenise, infère par lots, puis délègue à ``build_output``).

Sortie : un dict par verbatim contenant exactement les colonnes enrichies du
CSV mensuel (cf. OUTPUT_COLUMNS).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..modeling import EmbeddingExtractor, load_classifier
from ..modeling.architecture import resolve_model_dir
from ..preprocessing import Anonymizer, TextCleaner
from ..utils import Taxonomy, load_config, resolve_path, sentiment_input

logger = logging.getLogger(__name__)

# Colonnes enrichies produites pour CHAQUE verbatim (ordre = format de sortie).
OUTPUT_COLUMNS = [
    "verbatim_analysé",
    "nb_themes",
    "theme1_niv1", "theme1_niv2", "theme1_sentiment", "theme1_score_confiance",
    "theme2_niv1", "theme2_niv2", "theme2_sentiment", "theme2_score_confiance",
    "signal_rupture_client", "signal_churn", "signal_insatisfaction_forte",
    "confidence_globale", "revue_humaine_requise",
]

SIGNAL_KEYS = ["rupture", "churn", "insatisfaction"]


# --------------------------------------------------------------------------- #
#  LOGIQUE DE DÉCISION PURE (sans torch — testable)
# --------------------------------------------------------------------------- #
def build_output(
    cleaned_text: str,
    niv1_probs: np.ndarray,
    niv2_probs: np.ndarray,
    sentiment_probs: np.ndarray,
    signal_probs: Dict[str, float],
    satisfaction: Optional[float],
    taxonomy: Taxonomy,
    cfg: Dict[str, Any],
    signal_thresholds: Dict[str, float],
    sentiment_labels: List[str],
) -> Dict[str, Any]:
    """Assemble la sortie finale d'un verbatim à partir des probabilités modèles."""
    thr = cfg["thresholds"]
    empty_template = _empty_result(cleaned_text)

    # Verbatim vide / non exploitable -> revue humaine systématique.
    if not cleaned_text or str(cleaned_text).strip() == "":
        return empty_template

    niv1_probs = np.asarray(niv1_probs, dtype=float)
    niv2_probs = np.asarray(niv2_probs, dtype=float)
    sentiment_probs = np.asarray(sentiment_probs, dtype=float)

    # --- 1. Sélection des thèmes niv.1 (multi-label, plafond = max_themes) ----
    order = np.argsort(-niv1_probs)  # indices triés par proba décroissante
    activated = [i for i in order if niv1_probs[i] >= thr["classification_niv1"]]
    if not activated:
        activated = [int(order[0])]  # toujours au moins 1 thème (faible confiance)
    activated = activated[: thr["max_themes"]]

    # --- 2. Sentiment (au niveau du verbatim, appliqué à chaque thème) --------
    sent_idx = int(np.argmax(sentiment_probs))
    sentiment_label = sentiment_labels[sent_idx]
    sentiment_conf = float(sentiment_probs[sent_idx])

    # --- 3. Construction des thèmes (niv.2 masqué par la hiérarchie) ----------
    themes = []
    for niv1_idx in activated:
        niv1_label = taxonomy.idx_to_niv1[int(niv1_idx)]
        niv2_label, niv2_conf = taxonomy.best_niv2_for_niv1(niv1_label, niv2_probs)
        themes.append({
            "niv1": niv1_label,
            "niv2": niv2_label,
            "niv1_conf": float(niv1_probs[niv1_idx]),
            "niv2_conf": float(niv2_conf),
            "sentiment": sentiment_label,
        })

    # --- 4. Signaux -----------------------------------------------------------
    rupture = float(signal_probs.get("rupture", 0.0)) >= signal_thresholds["rupture"]
    churn = float(signal_probs.get("churn", 0.0)) >= signal_thresholds["churn"]
    insat_model = float(signal_probs.get("insatisfaction", 0.0)) >= signal_thresholds["insatisfaction"]
    # Règle déterministe (cahier des charges) : note <= 3 ET sentiment négatif.
    score_max = cfg.get("signals", {}).get("insatisfaction_score_max", 3)
    rule_insat = _valid_int(satisfaction) is not None and _valid_int(satisfaction) <= score_max \
        and sentiment_label == "Négatif"
    insatisfaction = bool(insat_model or rule_insat)
    # Règle métier : une rupture déclarée est, par construction, un churn.
    churn = bool(churn or rupture)

    # --- 5. Confidence globale + routage revue humaine ------------------------
    t1 = themes[0]
    components = [t1["niv1_conf"], t1["niv2_conf"], sentiment_conf]
    confidence_globale = float(np.mean(components))
    revue = confidence_globale < thr["revue_humaine"]

    # --- 6. Assemblage du dict de sortie --------------------------------------
    result = dict(empty_template)
    result.update({
        "verbatim_analysé": cleaned_text,
        "nb_themes": len(themes),
        "theme1_niv1": t1["niv1"],
        "theme1_niv2": t1["niv2"],
        "theme1_sentiment": t1["sentiment"],
        "theme1_score_confiance": round(t1["niv1_conf"], 4),
        "signal_rupture_client": rupture,
        "signal_churn": churn,
        "signal_insatisfaction_forte": insatisfaction,
        "confidence_globale": round(confidence_globale, 4),
        "revue_humaine_requise": bool(revue),
    })
    if len(themes) == 2:
        t2 = themes[1]
        result.update({
            "theme2_niv1": t2["niv1"],
            "theme2_niv2": t2["niv2"],
            "theme2_sentiment": t2["sentiment"],
            "theme2_score_confiance": round(t2["niv1_conf"], 4),
        })
    return result


def _empty_result(cleaned_text: str) -> Dict[str, Any]:
    """Gabarit de sortie (valeurs neutres) — verbatim non classifiable."""
    return {
        "verbatim_analysé": cleaned_text or "",
        "nb_themes": 0,
        "theme1_niv1": "", "theme1_niv2": "", "theme1_sentiment": "",
        "theme1_score_confiance": 0.0,
        "theme2_niv1": "", "theme2_niv2": "", "theme2_sentiment": "",
        "theme2_score_confiance": "",
        "signal_rupture_client": False, "signal_churn": False,
        "signal_insatisfaction_forte": False,
        "confidence_globale": 0.0, "revue_humaine_requise": True,
    }


def _valid_int(value: Any) -> Optional[int]:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        return int(round(float(value)))
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
#  ORCHESTRATION
# --------------------------------------------------------------------------- #
class VerbatimPredictor:
    """Charge tous les modèles et produit la prédiction complète d'un verbatim."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))
        self.anonymizer = Anonymizer(cfg)
        self.cleaner = TextCleaner(cfg)
        self.batch_size = cfg["model"]["batch_size_inference"]

        # --- Classifieurs thématiques + sentiment (ONNX int8 si dispo) --------
        logger.info("Chargement des modèles d'inférence...")
        self.clf_niv1 = load_classifier(
            resolve_path(cfg, cfg["paths"]["model_classifier_niv1"]), multilabel=True, cfg=cfg)
        self.clf_niv2 = load_classifier(
            resolve_path(cfg, cfg["paths"]["model_classifier_niv2"]), multilabel=False, cfg=cfg)
        self.clf_sentiment = load_classifier(
            resolve_path(cfg, cfg["paths"]["model_sentiment"]), multilabel=False, cfg=cfg)
        self.sentiment_labels = cfg["sentiment"]["labels"]

        # --- Détecteurs de signaux (embeddings gelés + LogReg) ----------------
        self._load_signals()

    # ------------------------------------------------------------------ #
    def _load_signals(self) -> None:
        import joblib

        sig_dir = resolve_model_dir(resolve_path(self.cfg, self.cfg["paths"]["model_signals"]))
        meta_path = sig_dir / "signals_metadata.json"
        with open(meta_path, "r", encoding="utf-8") as fh:
            self.signals_meta = json.load(fh)
        self.signal_models = {}
        self.signal_thresholds = {}
        for short in SIGNAL_KEYS:
            self.signal_models[short] = joblib.load(sig_dir / f"{short}.joblib")
            self.signal_thresholds[short] = self.signals_meta["signals"][short]["threshold"]
        self.embedder = EmbeddingExtractor(self.cfg)

    # ------------------------------------------------------------------ #
    def predict(self, text: str, satisfaction_score: Optional[float] = None) -> Dict[str, Any]:
        """Prédit pour UN verbatim brut. Renvoie le dict de sortie complet."""
        return self.predict_batch([text], [satisfaction_score])[0]

    # ------------------------------------------------------------------ #
    def predict_batch(
        self, texts: List[str], satisfactions: Optional[List[Optional[float]]] = None
    ) -> List[Dict[str, Any]]:
        """Prédit pour des verbatims BRUTS (anonymisation -> nettoyage -> inférence).

        Chemin auto-suffisant (démo, notebook, prédiction unitaire). Pour le
        traitement par lots de production, ``batch_processor`` pilote lui-même
        l'anonymisation (afin de journaliser les PII) puis appelle
        :meth:`predict_cleaned_batch`.
        """
        if satisfactions is None:
            satisfactions = [None] * len(texts)
        cleaned = [self.cleaner.clean(self.anonymizer.anonymize(t)[0]) for t in texts]
        return self.predict_cleaned_batch(cleaned, satisfactions)

    # ------------------------------------------------------------------ #
    def predict_cleaned_batch(
        self, cleaned: List[str], satisfactions: Optional[List[Optional[float]]] = None
    ) -> List[Dict[str, Any]]:
        """Prédit à partir de textes DÉJÀ anonymisés + nettoyés (inférence pure)."""
        n = len(cleaned)
        if satisfactions is None:
            satisfactions = [None] * n

        # --- Inférence par lots (textes non vides uniquement) ----------------
        idx_ok = [i for i, c in enumerate(cleaned) if c.strip() != ""]
        results: List[Optional[Dict[str, Any]]] = [None] * n

        if idx_ok:
            texts_ok = [cleaned[i] for i in idx_ok]
            sats_ok = [satisfactions[i] for i in idx_ok]

            niv1_probs = self.clf_niv1.predict_proba(texts_ok, self.batch_size)
            niv2_probs = self.clf_niv2.predict_proba(texts_ok, self.batch_size)
            sent_texts = [sentiment_input(t, s, self.cfg) for t, s in zip(texts_ok, sats_ok)]
            sent_probs = self.clf_sentiment.predict_proba(sent_texts, self.batch_size)
            signal_probs = self._signal_probs(texts_ok)

            for k, i in enumerate(idx_ok):
                results[i] = build_output(
                    cleaned[i], niv1_probs[k], niv2_probs[k], sent_probs[k],
                    {s: float(signal_probs[s][k]) for s in SIGNAL_KEYS},
                    satisfactions[i], self.taxonomy, self.cfg,
                    self.signal_thresholds, self.sentiment_labels,
                )

        # --- Verbatims vides -> gabarit revue humaine ------------------------
        for i in range(n):
            if results[i] is None:
                results[i] = _empty_result(cleaned[i])
        return results  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    def _signal_probs(self, texts: List[str]) -> Dict[str, np.ndarray]:
        """Probabilités des 3 signaux (embeddings gelés -> LogReg)."""
        emb = self.embedder.embed(texts, batch_size=self.batch_size)
        out = {}
        for short in SIGNAL_KEYS:
            out[short] = self.signal_models[short].predict_proba(emb)[:, 1]
        return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    predictor = VerbatimPredictor(load_config())
    demo = predictor.predict(
        "Plus de 2 semaines de retard. Sans notification pour prévenir.", satisfaction_score=2
    )
    print(json.dumps(demo, ensure_ascii=False, indent=2))
