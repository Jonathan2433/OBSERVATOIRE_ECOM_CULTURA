"""Logique de décision PARTAGÉE par les moteurs LLM (LM Studio, Claude) — V5.

Ce module regroupe les fonctions **pures** (sans I/O, sans torch, sans spaCy)
mutualisées entre les backends LLM :

  - construction du prompt en mode **proposeur** (``build_llm_prompt``) et en mode
    **raffineur** (``build_refiner_prompt``, cascade V5) ;
  - revalidation taxonomie + repli + garde-fous (``map_llm_response``) ;
  - gabarit de sortie (``empty_output``, ``OUTPUT_COLUMNS``) et helpers de
    normalisation (casse/accents).

Extrait de ``lmstudio_predictor`` (V4) **sans changement de comportement** : le
moteur LM Studio ré-importe ces symboles et la recette V4 doit rester 50/50.
Le **transport HTTP reste propre à chaque moteur** (``call_llm_chat`` côté LM
Studio en OpenAI-compatible, Messages API côté Claude) : seule la logique de
décision est ici. cf. docs/SPEC_V5_MULTI_MOTEUR §4.2.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from src.utils import Taxonomy

# Gabarit de sortie — MIROIR de src.inference.predictor.OUTPUT_COLUMNS.
# Répliqué ici volontairement pour rester torch-free (predictor.py importe torch).
OUTPUT_COLUMNS = [
    "verbatim_analysé",
    "nb_themes",
    "theme1_niv1", "theme1_niv2", "theme1_sentiment", "theme1_score_confiance",
    "theme2_niv1", "theme2_niv2", "theme2_sentiment", "theme2_score_confiance",
    "signal_rupture_client", "signal_churn", "signal_insatisfaction_forte",
    "confidence_globale", "revue_humaine_requise",
]

FALLBACK_THEME_DEFAULT = "Autre / Non classé"

# Schéma JSON imposé au LLM (sortie structurée). Garantit la forme ; la validité
# métier (taxonomie), la limite à 2 thèmes et le plafonnement de confiance sont
# assurés ENSUITE par map_llm_response. On reste sur le sous-ensemble de
# JSON-schema supporté par la grammaire de LM Studio (llama.cpp) : type / enum /
# required / properties — SANS minItems/maxItems/minimum/maximum (HTTP 500
# « grammar » sur LM Studio). Côté Claude (tool use) le même schéma est réutilisé.
LLM_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "niv1": {"type": "string"},
                    "niv2": {"type": "string"},
                    "sentiment": {"type": "string", "enum": ["Négatif", "Neutre", "Positif"]},
                    "confidence": {"type": "number"},
                },
                "required": ["niv1", "niv2", "sentiment", "confidence"],
            },
        },
        "signaux": {
            "type": "object",
            "properties": {
                "rupture": {"type": "boolean"},
                "churn": {"type": "boolean"},
                "insatisfaction_forte": {"type": "boolean"},
            },
            "required": ["rupture", "churn", "insatisfaction_forte"],
        },
    },
    "required": ["themes", "signaux"],
}


# --------------------------------------------------------------------------- #
#  Gabarit de sortie
# --------------------------------------------------------------------------- #
def empty_output(cleaned_text: str) -> Dict[str, Any]:
    """Sortie neutre (verbatim non classifiable) -> revue humaine."""
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


# --------------------------------------------------------------------------- #
#  PROMPT (pur) — versionné via cfg.<moteur>.prompt_version
# --------------------------------------------------------------------------- #
PROMPT_VERSION_DEFAULT = "v1"


def _taxonomy_block(taxonomy: Taxonomy) -> str:
    lines = []
    for niv1 in taxonomy.niv1_labels:
        children = ", ".join(taxonomy.children.get(niv1, []))
        lines.append(f"- {niv1} : {children}")
    return "\n".join(lines)


def _satisfaction_line(satisfaction: Optional[float]) -> str:
    """Ligne « Note de satisfaction » injectée dans le prompt (vide si absente/invalide)."""
    if satisfaction is None:
        return ""
    try:
        return f"\nNote de satisfaction (1-10) : {int(round(float(satisfaction)))}"
    except (ValueError, TypeError):
        return ""


def build_llm_prompt(
    taxonomy: Taxonomy, cleaned_text: str, satisfaction: Optional[float],
    fallback_theme: str = FALLBACK_THEME_DEFAULT, version: str = PROMPT_VERSION_DEFAULT,
) -> Dict[str, str]:
    """Construit (system, user) du mode PROPOSEUR. Fonction pure et versionnée.

    Le numéro de version est tracé dans le system prompt pour reproductibilité.
    Pour faire évoluer la formulation, ajouter une branche ``version`` ici.
    """
    system = (
        f"[prompt {version}] Tu es un classifieur de verbatims clients e-commerce pour "
        "Cultura. Tu classes chaque verbatim STRICTEMENT dans la taxonomie fournie, sans "
        "jamais inventer de thème. Tu réponds UNIQUEMENT en JSON conforme au schéma "
        "demandé, sans aucun texte autour."
    )
    sat_line = _satisfaction_line(satisfaction)
    user = (
        "Taxonomie autorisée (niv1 : sous-thèmes niv2 valides) :\n"
        f"{_taxonomy_block(taxonomy)}\n\n"
        "Règles impératives :\n"
        "1. Choisis 1 thème, ou 2 SEULEMENT si le verbatim aborde deux sujets DISTINCTS.\n"
        "2. Recopie les libellés niv1 et niv2 EXACTEMENT comme ci-dessus (un couple doit "
        "toujours être un sous-thème listé sous son niv1).\n"
        "3. N'invente JAMAIS de thème. Si rien ne correspond, mets niv1="
        f"\"{fallback_theme}\" et niv2=\"\".\n"
        "4. sentiment ∈ {Négatif, Neutre, Positif}. confidence ∈ [0,1], HONNÊTE : basse "
        "si tu hésites ou si le verbatim est ambigu.\n"
        "5. signaux : rupture (le client annonce rompre la relation / partir à la "
        "concurrence), churn (risque de départ), insatisfaction_forte.\n\n"
        f"Verbatim à classer :{sat_line}\n\"\"\"\n{cleaned_text}\n\"\"\""
    )
    return {"system": system, "user": user}


# --------------------------------------------------------------------------- #
#  PROMPT RAFFINEUR (pur) — cascade V5 (cf. SPEC_V5 §5/§6)
# --------------------------------------------------------------------------- #
def _proposal_block(proposal: Optional[Dict[str, Any]]) -> str:
    """Rend la proposition du moteur 1 (format OUTPUT_COLUMNS) en texte compact."""
    p = proposal or {}
    lines: List[str] = []
    n1 = p.get("theme1_niv1", "")
    if n1:
        lines.append(
            f"- Thème 1 : {n1} › {p.get('theme1_niv2', '')} "
            f"(sentiment {p.get('theme1_sentiment', '')}, "
            f"confiance {p.get('theme1_score_confiance', '')})"
        )
    n2 = p.get("theme2_niv1", "")
    if n2:
        lines.append(
            f"- Thème 2 : {n2} › {p.get('theme2_niv2', '')} "
            f"(sentiment {p.get('theme2_sentiment', '')}, "
            f"confiance {p.get('theme2_score_confiance', '')})"
        )
    sig = []
    if p.get("signal_rupture_client"):
        sig.append("rupture")
    if p.get("signal_churn"):
        sig.append("churn")
    if p.get("signal_insatisfaction_forte"):
        sig.append("insatisfaction_forte")
    lines.append("- Signaux : " + (", ".join(sig) if sig else "aucun"))
    return "\n".join(lines) if lines else "- (aucune proposition exploitable)"


def build_refiner_prompt(
    taxonomy: Taxonomy, cleaned_text: str, proposal: Optional[Dict[str, Any]],
    satisfaction: Optional[float] = None,
    fallback_theme: str = FALLBACK_THEME_DEFAULT, version: str = PROMPT_VERSION_DEFAULT,
) -> Dict[str, str]:
    """Construit (system, user) du mode RAFFINEUR. Fonction pure et versionnée.

    Le raffineur reçoit le verbatim + la **proposition d'un premier moteur**
    (niv1/niv2, sentiment, signaux, confiance) et la **valide ou la corrige**,
    en restant strictement dans la taxonomie. Même schéma de sortie que le
    proposeur (``LLM_OUTPUT_SCHEMA``) → revalidé par ``map_llm_response``, donc
    les garde-fous V4 (taxo + repli + plafonds) sont conservés tels quels.
    """
    system = (
        f"[prompt {version} · raffineur] Tu es un classifieur de verbatims clients "
        "e-commerce pour Cultura, en mode RELECTURE. On te fournit un verbatim et une "
        "proposition de classification produite par un premier modèle. Tu la VALIDES si "
        "elle est correcte, sinon tu la CORRIGES, en restant STRICTEMENT dans la "
        "taxonomie fournie, sans jamais inventer de thème. Tu réponds UNIQUEMENT en JSON "
        "conforme au schéma demandé, sans aucun texte autour."
    )
    sat_line = _satisfaction_line(satisfaction)
    user = (
        "Taxonomie autorisée (niv1 : sous-thèmes niv2 valides) :\n"
        f"{_taxonomy_block(taxonomy)}\n\n"
        "Proposition du premier modèle (à valider ou corriger) :\n"
        f"{_proposal_block(proposal)}\n\n"
        "Règles impératives :\n"
        "1. Conserve la proposition si elle est pertinente ; corrige-la sinon.\n"
        "2. Recopie les libellés niv1 et niv2 EXACTEMENT comme dans la taxonomie (un "
        "couple doit toujours être un sous-thème listé sous son niv1).\n"
        "3. N'invente JAMAIS de thème. Si rien ne correspond, mets niv1="
        f"\"{fallback_theme}\" et niv2=\"\".\n"
        "4. sentiment ∈ {Négatif, Neutre, Positif}. confidence ∈ [0,1], HONNÊTE.\n"
        "5. signaux : rupture (le client annonce rompre la relation / partir à la "
        "concurrence), churn (risque de départ), insatisfaction_forte.\n\n"
        f"Verbatim à reclasser :{sat_line}\n\"\"\"\n{cleaned_text}\n\"\"\""
    )
    return {"system": system, "user": user}


# --------------------------------------------------------------------------- #
#  MAPPING réponse -> sortie (pur) — validation taxonomie + repli + garde-fous
# --------------------------------------------------------------------------- #
def _clamp01(x: Any) -> float:
    try:
        v = float(x)
    except (ValueError, TypeError):
        return 0.0
    return max(0.0, min(1.0, v))


def _valid_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, float) and value != value:  # NaN
            return None
        return int(round(float(value)))
    except (ValueError, TypeError):
        return None


def _norm(s: Any) -> str:
    """Normalise un libellé pour un appariement tolérant (casse + accents + espaces).

    Permet de retrouver le libellé canonique de la taxonomie même si le LLM
    altère la casse ou les accents — sans jamais « deviner » un thème : on
    n'accepte que ce qui correspond à un libellé EXISTANT après normalisation.
    """
    txt = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return " ".join(txt.split()).casefold()


def _canon_map(labels: List[str]) -> Dict[str, str]:
    """Table normalisé -> libellé canonique (dernier gagne en cas de collision rare)."""
    return {_norm(l): l for l in labels}


def map_llm_response(
    raw: Dict[str, Any],
    cleaned_text: str,
    satisfaction: Optional[float],
    taxonomy: Taxonomy,
    cfg: Dict[str, Any],
    sentiment_labels: List[str],
) -> Dict[str, Any]:
    """Transforme la réponse JSON du LLM en dict de sortie validé. Fonction pure.

    Étapes : appariement TOLÉRANT des libellés (casse/accents) à la taxonomie ->
    repli + revue forcée si hors référentiel -> dé-doublonnage -> garde-fous de
    confiance (deux plafonds) -> désaccord de sentiment -> assemblage.

    Les garde-fous sont lus sous ``cfg["lmstudio"]`` (clé historique partagée par
    les moteurs LLM ; un moteur peut surcharger en fournissant son propre bloc).
    """
    if not cleaned_text or str(cleaned_text).strip() == "":
        return empty_output(cleaned_text)

    engine = cfg.get("lmstudio", {}) or {}
    guards = engine.get("guardrails", {}) or {}
    fallback_theme = engine.get("fallback_theme", FALLBACK_THEME_DEFAULT)
    repli_cap = float(guards.get("repli_confidence_max", 0.40))
    bad_json_cap = float(guards.get("invalid_json_confidence_max", 0.30))
    review_on_conflict = bool(guards.get("review_on_sentiment_conflict", True))
    max_themes = int(cfg.get("thresholds", {}).get("max_themes", 2))
    seuil = float(cfg.get("thresholds", {}).get("revue_humaine", 0.50))
    score_max = int(cfg.get("signals", {}).get("insatisfaction_score_max", 3))

    sent_canon = _canon_map(sentiment_labels)
    niv1_canon = _canon_map(taxonomy.niv1_labels)

    themes_in = raw.get("themes") if isinstance(raw, dict) else None
    if not isinstance(themes_in, list) or not themes_in:
        # Réponse hors-forme (JSON cassé / vide) -> repli au plafond le plus bas + revue.
        return _assemble(cleaned_text, [_fallback_theme(fallback_theme, bad_json_cap)],
                         raw.get("signaux", {}) if isinstance(raw, dict) else {},
                         satisfaction, score_max, seuil, forced_review=True)

    mapped: List[Dict[str, Any]] = []
    forced_review = False
    for t in themes_in[:max_themes]:
        t = t if isinstance(t, dict) else {}
        conf = _clamp01(t.get("confidence", 0.0))

        # Sentiment : appariement tolérant -> sinon Neutre + revue.
        cs = sent_canon.get(_norm(t.get("sentiment", "")))
        if cs is None:
            cs = "Neutre"
            conf = min(conf, repli_cap)
            forced_review = True

        # Couple niv1/niv2 : appariement tolérant contre la taxonomie.
        canon_niv1 = niv1_canon.get(_norm(t.get("niv1", "")))
        canon_niv2 = None
        if canon_niv1 is not None:
            canon_niv2 = _canon_map(taxonomy.children.get(canon_niv1, [])).get(_norm(t.get("niv2", "")))

        if canon_niv1 is not None and canon_niv2 is not None:
            mapped.append({"niv1": canon_niv1, "niv2": canon_niv2, "sentiment": cs, "conf": conf})
        else:
            # Hors référentiel -> sentinelle de repli (décision a+c) + revue forcée.
            fb = _fallback_theme(fallback_theme, min(conf, repli_cap))
            fb["sentiment"] = cs
            mapped.append(fb)
            forced_review = True

    # Dé-doublonnage des couples identiques (garde la 1re occurrence).
    deduped: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for m in mapped:
        key = (m["niv1"], m["niv2"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
    if not deduped:
        deduped = [_fallback_theme(fallback_theme, repli_cap)]
        forced_review = True

    # Garde-fou : 2 thèmes au sentiment divergent (dont un Négatif) -> revue.
    if review_on_conflict and len(deduped) == 2:
        sents = {deduped[0]["sentiment"], deduped[1]["sentiment"]}
        if len(sents) > 1 and "Négatif" in sents:
            forced_review = True

    return _assemble(cleaned_text, deduped,
                     raw.get("signaux", {}) if isinstance(raw, dict) else {},
                     satisfaction, score_max, seuil, forced_review)


def _fallback_theme(label: str, conf: float) -> Dict[str, Any]:
    return {"niv1": label, "niv2": "", "sentiment": "Neutre", "conf": float(conf)}


def _assemble(
    cleaned_text: str, themes: List[Dict[str, Any]], signaux: Dict[str, Any],
    satisfaction: Optional[float], score_max: int, seuil: float, forced_review: bool,
) -> Dict[str, Any]:
    t1 = themes[0]
    sg = signaux if isinstance(signaux, dict) else {}
    rupture = bool(sg.get("rupture", False))
    churn = bool(sg.get("churn", False)) or rupture        # rupture => churn (parité moteurs)
    insat = bool(sg.get("insatisfaction_forte", False))
    si = _valid_int(satisfaction)
    if si is not None and si <= score_max and t1["sentiment"] == "Négatif":
        insat = True                                        # règle métier déterministe

    confidence_globale = float(t1["conf"])
    revue = bool(forced_review or confidence_globale < seuil)

    out = empty_output(cleaned_text)
    out.update({
        "verbatim_analysé": cleaned_text,
        "nb_themes": len(themes),
        "theme1_niv1": t1["niv1"],
        "theme1_niv2": t1["niv2"],
        "theme1_sentiment": t1["sentiment"],
        "theme1_score_confiance": round(confidence_globale, 4),
        "signal_rupture_client": rupture,
        "signal_churn": churn,
        "signal_insatisfaction_forte": insat,
        "confidence_globale": round(confidence_globale, 4),
        "revue_humaine_requise": revue,
    })
    if len(themes) == 2:
        t2 = themes[1]
        out.update({
            "theme2_niv1": t2["niv1"],
            "theme2_niv2": t2["niv2"],
            "theme2_sentiment": t2["sentiment"],
            "theme2_score_confiance": round(float(t2["conf"]), 4),
        })
    return out
