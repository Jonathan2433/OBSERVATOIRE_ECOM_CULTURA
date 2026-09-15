"""Pipeline d'inférence complet pour un (ou plusieurs) verbatim(s).

Sépare volontairement DEUX responsabilités :
  - ``build_output`` : LOGIQUE DE DÉCISION PURE (numpy/python, sans torch).
    Prend les probabilités brutes des modèles et applique la sélection des
    thèmes (déléguée à ``decision.PolitiqueDecision``), la contrainte
    hiérarchique (masquage niv.2), les règles de signaux, l'agrégation de
    confiance et le routage en revue humaine. Testable isolément.
  - ``VerbatimPredictor`` : ORCHESTRATION (charge les modèles, anonymise,
    nettoie, tokenise, infère par lots, puis délègue à ``build_output``).

Sortie : un dict par verbatim contenant exactement les colonnes enrichies du
CSV mensuel (cf. OUTPUT_COLUMNS).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import numpy as np

from ..modeling import EmbeddingExtractor, load_classifier
from ..modeling.architecture import resolve_model_dir
from ..preprocessing import Anonymizer, TextCleaner
from ..utils import Taxonomy, load_config, resolve_path, sentiment_input
from .decision import PolitiqueDecision, fold_libelle

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
    source: Optional[str] = None,
    politique: Optional[PolitiqueDecision] = None,
) -> Dict[str, Any]:
    """Assemble la sortie finale d'un verbatim à partir des probabilités modèles.

    ``source`` est la provenance FINE du verbatim (``MDTC-postrecep``…). Elle
    n'entre dans aucun modèle : elle sert uniquement aux règles d'arbitrage
    contextuel de la couche de décision (cf. ``decision.py``). Absente, ces
    règles ne s'appliquent pas — et la politique le comptabilise.

    ``politique`` évite de reconstruire la politique à chaque verbatim ; elle
    est déduite de ``cfg`` et du référentiel si elle n'est pas fournie.
    """
    thr = cfg["thresholds"]
    empty_template = _empty_result(cleaned_text)

    # Verbatim vide / non exploitable -> revue humaine systématique.
    if not cleaned_text or str(cleaned_text).strip() == "":
        return empty_template

    niv1_probs = np.asarray(niv1_probs, dtype=float)
    niv2_probs = np.asarray(niv2_probs, dtype=float)
    sentiment_probs = np.asarray(sentiment_probs, dtype=float)

    # --- 1. Sélection des thèmes niv.1 ----------------------------------------
    # Seuils par thème, plafond, arbitrage contextuel par source, suppression des
    # paires qui se recouvrent : une seule implémentation, celle que l'évaluation
    # rejoue à l'identique (cf. `decision.py`).
    if politique is None:
        politique = _politique(cfg, taxonomy)
    activated = politique.themes(niv1_probs, source)

    # --- 2. Sentiment (au niveau du verbatim, appliqué à chaque thème) --------
    sent_idx = int(np.argmax(sentiment_probs))
    sentiment_label = sentiment_labels[sent_idx]
    sentiment_conf = float(sentiment_probs[sent_idx])

    # --- 3. Construction des thèmes (niv.2 masqué par la hiérarchie) ----------
    # D-40 : quand le sous-thème retenu relève des 16 hors périmètre (D-32), le
    # modèle produit le niveau 1, laisse le niveau 2 VIDE et force la revue —
    # l'humain qualifie le sous-thème. Aucune colonne n'est ajoutée à
    # OUTPUT_COLUMNS ; c'est la sémantique de `theme*_niv2` qui s'élargit au vide.
    hors_perimetre = _sous_themes_hors_perimetre(cfg)
    vider_hors_perimetre = bool(thr.get("niv2_hors_perimetre_vide", False))
    seuil_niv2_actif = bool(thr.get("niv2_seuil_actif", False))
    seuil_niv2 = float(thr.get("classification_niv2", 0.0))

    themes = []
    revue_forcee = False
    for niv1_idx in activated:
        niv1_label = taxonomy.idx_to_niv1[int(niv1_idx)]
        niv2_label, niv2_conf = taxonomy.best_niv2_for_niv1(niv1_label, niv2_probs)
        if vider_hors_perimetre and _fold_label(niv2_label) in hors_perimetre:
            niv2_label, revue_forcee = "", True
        elif seuil_niv2_actif and float(niv2_conf) < seuil_niv2:
            # `classification_niv2` était déclaré en configuration sans jamais
            # être lu. Sous ce seuil, la confiance du niveau 2 est trop diffuse
            # pour être exploitable : c'est la signature d'un sous-thème absent
            # du périmètre. Inactif par défaut, à calibrer en L6/L7.
            niv2_label, revue_forcee = "", True
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
    revue = bool(confidence_globale < thr["revue_humaine"] or revue_forcee)

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


_HORS_PERIMETRE_CACHE: Dict[int, frozenset] = {}
_POLITIQUE_CACHE: Dict[tuple, PolitiqueDecision] = {}

#: Conservé pour les appelants existants ; l'implémentation vit dans `decision`.
_fold_label = fold_libelle


def _politique(cfg: Dict[str, Any], taxonomy: Taxonomy) -> PolitiqueDecision:
    """Politique de décision, construite une fois par (config, référentiel).

    ``build_output`` reste appelable sans contexte d'orchestration : la
    politique est déduite si l'appelant ne la fournit pas. Le cache évite de
    re-résoudre les libellés à chaque verbatim — et surtout de remettre à zéro
    les compteurs d'application, qui sont ce qui rend les règles auditables.
    """
    cle = (id(cfg), id(taxonomy))
    if cle not in _POLITIQUE_CACHE:
        _POLITIQUE_CACHE[cle] = PolitiqueDecision.depuis_config(cfg, taxonomy)
    return _POLITIQUE_CACHE[cle]


def _sous_themes_hors_perimetre(cfg: Dict[str, Any]) -> frozenset:
    """Sous-thèmes sous le seuil de D-32, sous forme tolérante. Mémoïsé.

    La liste est FIGÉE en configuration : la recalculer sur le corpus la ferait
    varier d'une exécution à l'autre, ce qui changerait l'espace de labels et
    invaliderait les modèles entraînés.
    """
    cle = id(cfg)
    if cle not in _HORS_PERIMETRE_CACHE:
        libelles = (cfg.get("label_normalization", {}) or {}).get(
            "sous_themes_hors_perimetre", []) or []
        _HORS_PERIMETRE_CACHE[cle] = frozenset(_fold_label(x) for x in libelles)
    return _HORS_PERIMETRE_CACHE[cle]


def signaux_sans_modele(cfg: Dict[str, Any]) -> List[str]:
    """Signaux du contrat de sortie qui n'ont AUCUN détecteur entraîné (D-41).

    N'ouvre aucun modèle : elle regarde les fichiers présents. C'est ce qui
    permet à l'API de le dire à l'interface sans charger CamemBERT.

    Pourquoi cette fonction existe (arbitrage PO du 11/09) : `churn` et
    `rupture` sortent constamment à ``False`` faute d'effectif suffisant pour
    un détecteur évaluable. Un ``False`` affiché comme une mesure ferait croire
    qu'aucun client n'est en rupture, alors que nous ne l'avons pas cherché.
    L'interface doit pouvoir distinguer « mesuré, négatif » de « non mesuré ».
    """
    from ..modeling.architecture import resolve_model_dir
    from ..utils import resolve_path

    try:
        dossier = resolve_model_dir(resolve_path(cfg, cfg["paths"]["model_signals"]))
    except Exception:                     # modèle absent : tout est non mesuré
        return list(SIGNAL_KEYS)
    return [s for s in SIGNAL_KEYS if not (dossier / f"{s}.joblib").is_file()]


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
        # Politique de décision résolue au démarrage : un libellé de règle absent
        # du référentiel doit échouer ici, pas au millième verbatim.
        self.politique = _politique(cfg, self.taxonomy)
        if self.politique.actif:
            logger.info("Couche de décision : %s", self.politique.resume())
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
        # D-41 : tous les signaux n'ont pas nécessairement de modèle. `churn`
        # (64 positifs) et `rupture` (32) sont trop rares pour être entraînés
        # sans produire des métriques trompeuses ; ils restent au contrat de
        # sortie mais sans détecteur. Un modèle absent n'est PAS une erreur —
        # en revanche il est journalisé, jamais silencieux.
        seuils_meta = self.signals_meta.get("signals") or self.signals_meta.get("thresholds") or {}
        for short in SIGNAL_KEYS:
            chemin = sig_dir / f"{short}.joblib"
            if not chemin.is_file():
                self.signal_models[short] = None
                self.signal_thresholds[short] = 1.0   # jamais franchi
                logger.warning(
                    "Signal '%s' : aucun modèle dans %s — produit à False. "
                    "Cf. D-41 : effectif insuffisant pour un détecteur évaluable ; "
                    "la règle métier reste à définir en L4.", short, sig_dir.name)
                continue
            self.signal_models[short] = joblib.load(chemin)
            entree = seuils_meta.get(short)
            self.signal_thresholds[short] = (
                entree["threshold"] if isinstance(entree, dict) else
                float(entree) if entree is not None else
                float(self.cfg["thresholds"].get(f"signal_{short}", 0.5)))
        self.signaux_sans_modele = [s for s, m in self.signal_models.items() if m is None]
        attendu = signaux_sans_modele(self.cfg)
        if sorted(attendu) != sorted(self.signaux_sans_modele):
            # L'API annonce à l'interface ce que `signaux_sans_modele` détecte
            # sans charger les modèles. Si les deux divergent, l'interface ment.
            logger.warning(
                "Incohérence entre les signaux détectés sans modèle (%s) et ceux "
                "réellement absents au chargement (%s) : l'interface annoncerait "
                "un périmètre de mesure faux.", attendu, self.signaux_sans_modele)
        self.embedder = EmbeddingExtractor(self.cfg)

    # ------------------------------------------------------------------ #
    def predict(self, text: str, satisfaction_score: Optional[float] = None,
                source: Optional[str] = None) -> Dict[str, Any]:
        """Prédit pour UN verbatim brut. Renvoie le dict de sortie complet."""
        return self.predict_batch([text], [satisfaction_score], [source])[0]

    # ------------------------------------------------------------------ #
    def predict_batch(
        self, texts: List[str], satisfactions: Optional[List[Optional[float]]] = None,
        sources: Optional[List[Optional[str]]] = None,
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
        return self.predict_cleaned_batch(cleaned, satisfactions, sources)

    # ------------------------------------------------------------------ #
    def predict_cleaned_batch(
        self, cleaned: List[str], satisfactions: Optional[List[Optional[float]]] = None,
        sources: Optional[List[Optional[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """Prédit à partir de textes DÉJÀ anonymisés + nettoyés (inférence pure).

        ``sources`` porte la provenance FINE de chaque verbatim, utilisée par les
        règles d'arbitrage contextuel. Omise, ces règles ne s'appliquent pas ;
        :meth:`politique.journaliser_couverture` l'annonce en fin de lot.
        """
        n = len(cleaned)
        if satisfactions is None:
            satisfactions = [None] * n
        if sources is None:
            sources = [None] * n

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
                    source=sources[i], politique=self.politique,
                )
            self.politique.journaliser_couverture()

        # --- Verbatims vides -> gabarit revue humaine ------------------------
        for i in range(n):
            if results[i] is None:
                results[i] = _empty_result(cleaned[i])
        return results  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    def _signal_probs(self, texts: List[str]) -> Dict[str, np.ndarray]:
        """Probabilités des signaux (embeddings gelés -> LogReg).

        Un signal sans modèle (D-41) renvoie une probabilité nulle : la colonne
        reste au contrat de sortie, à False, plutôt que de disparaître.
        """
        emb = self.embedder.embed(texts, batch_size=self.batch_size)
        out = {}
        for short in SIGNAL_KEYS:
            modele = self.signal_models.get(short)
            out[short] = (modele.predict_proba(emb)[:, 1] if modele is not None
                          else np.zeros(len(texts), dtype=float))
        return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    predictor = VerbatimPredictor(load_config())
    demo = predictor.predict(
        "Plus de 2 semaines de retard. Sans notification pour prévenir.", satisfaction_score=2
    )
    print(json.dumps(demo, ensure_ascii=False, indent=2))
