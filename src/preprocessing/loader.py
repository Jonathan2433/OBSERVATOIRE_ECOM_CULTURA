"""Chargement et parsing des fichiers Excel sources (MDTC + Mopinion + historique).

Les deux sources de production ont des schémas de colonnes DIFFÉRENTS :
  - MDTC      : retours post-commande, texte principal = "Verbatim justification"
                (+ "Verbatim suggestion" en complément).
  - Mopinion  : formulaire libre, texte principal = "Description du bug" (insatisfaits)
                OU "Suggestion" (satisfaits) — on prend la (ou les) cellule(s) non vide(s).

Chaque loader renvoie le DataFrame d'origine INTACT (toutes les colonnes
préservées pour le CSV enrichi final) augmenté de colonnes techniques normalisées
(préfixées ``__`` pour éviter toute collision avec des colonnes métier) :

  __source__        : "MDTC" | "Mopinion"
  __text_raw__      : texte brut à classifier (avant anonymisation/nettoyage)
  __satisfaction__  : score de satisfaction (int, NaN si absent)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

# Noms de colonnes techniques normalisées (contrat partagé avec le reste du pipeline)
COL_SOURCE = "__source__"
COL_TEXT = "__text_raw__"
COL_SATISFACTION = "__satisfaction__"

SOURCE_MDTC = "MDTC"
SOURCE_MOPINION = "Mopinion"


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _read_excel(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Fichier Excel introuvable : {path}")
    return pd.read_excel(path, engine="openpyxl")


def validate_columns(df: pd.DataFrame, required: List[str], source_name: str) -> None:
    """Lève une erreur explicite si une colonne obligatoire est absente.

    Utilisé par run_monthly_batch.py pour valider les fichiers avant traitement.
    """
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"[{source_name}] Colonnes obligatoires manquantes : {missing}. "
            f"Colonnes présentes : {list(df.columns)}"
        )


def _non_empty(value: Any) -> bool:
    """True si la valeur est un texte exploitable (non NaN, non vide)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return str(value).strip() != ""


def _coerce_int(value: Any):
    """Convertit en int si possible, sinon renvoie NaN (sécurise les scores)."""
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return float("nan")
        return int(round(float(value)))
    except (ValueError, TypeError):
        return float("nan")


# --------------------------------------------------------------------------- #
#  MDTC
# --------------------------------------------------------------------------- #
def load_mdtc(path: str | Path, cfg: Dict[str, Any]) -> pd.DataFrame:
    """Charge un export MDTC (retours post-commande)."""
    conf = cfg["sources"]["mdtc"]
    df = _read_excel(path)
    validate_columns(
        df,
        [conf["satisfaction_col"], conf["text_col_primary"]],
        SOURCE_MDTC,
    )

    primary = conf["text_col_primary"]
    secondary = conf.get("text_col_secondary")

    def _build_text(row) -> str:
        # Texte principal (justification) + suggestion en complément si présente.
        # Les deux émanent du même client sur la même commande : les concaténer
        # enrichit le signal thématique sans risque de mélange de contextes.
        parts = []
        if _non_empty(row.get(primary)):
            parts.append(str(row[primary]).strip())
        if secondary and _non_empty(row.get(secondary)):
            parts.append(str(row[secondary]).strip())
        return ". ".join(parts)

    out = df.copy()
    out[COL_SOURCE] = SOURCE_MDTC
    out[COL_TEXT] = out.apply(_build_text, axis=1)
    out[COL_SATISFACTION] = out[conf["satisfaction_col"]].apply(_coerce_int)
    return out


# --------------------------------------------------------------------------- #
#  Mopinion
# --------------------------------------------------------------------------- #
def load_mopinion(path: str | Path, cfg: Dict[str, Any]) -> pd.DataFrame:
    """Charge un export Mopinion (formulaire de satisfaction libre)."""
    conf = cfg["sources"]["mopinion"]
    df = _read_excel(path)
    validate_columns(df, [conf["satisfaction_col"]], SOURCE_MOPINION)

    text_cols = [c for c in conf["text_cols_primary"] if c in df.columns]
    if not text_cols:
        raise ValueError(
            f"[{SOURCE_MOPINION}] Aucune colonne texte parmi "
            f"{conf['text_cols_primary']} n'est présente."
        )

    def _build_text(row) -> str:
        # Insatisfaits -> "Description du bug" ; satisfaits -> "Suggestion".
        # On concatène toutes les cellules texte non vides (en pratique une seule).
        parts = [str(row[c]).strip() for c in text_cols if _non_empty(row.get(c))]
        return ". ".join(parts)

    out = df.copy()
    out[COL_SOURCE] = SOURCE_MOPINION
    out[COL_TEXT] = out.apply(_build_text, axis=1)
    out[COL_SATISFACTION] = out[conf["satisfaction_col"]].apply(_coerce_int)
    return out


# --------------------------------------------------------------------------- #
#  Historique (dataset d'entraînement)
# --------------------------------------------------------------------------- #
def load_historique(path: str | Path, cfg: Dict[str, Any]) -> pd.DataFrame:
    """Charge le dataset d'entraînement labellisé (historique_labels_poc.xlsx)."""
    df = _read_excel(path)
    required = [
        "source", "verbatim_original", "satisfaction_score", "nb_themes",
        "theme1_niv1", "theme1_niv2", "theme1_sentiment",
        "signal_rupture_client", "signal_churn", "signal_insatisfaction_forte",
    ]
    validate_columns(df, required, "historique")

    out = df.copy()
    out[COL_SOURCE] = out["source"]
    out[COL_TEXT] = out["verbatim_original"].astype(str)
    out[COL_SATISFACTION] = out["satisfaction_score"].apply(_coerce_int)
    # Normalise les booléens des signaux (gère True/False, 0/1, "VRAI"/"FAUX").
    for col in ["signal_rupture_client", "signal_churn", "signal_insatisfaction_forte"]:
        out[col] = out[col].apply(_to_bool)
    return out


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(int(value))
    s = str(value).strip().lower()
    return s in {"true", "vrai", "1", "oui", "yes"}


# --------------------------------------------------------------------------- #
#  Chargement combiné pour le traitement mensuel par lots
# --------------------------------------------------------------------------- #
def load_for_batch(
    mdtc_path: str | Path | None,
    mopinion_path: str | Path | None,
    cfg: Dict[str, Any],
) -> pd.DataFrame:
    """Charge et concatène MDTC + Mopinion pour un traitement mensuel.

    Les deux schémas étant différents, la concaténation produit l'UNION des
    colonnes (valeurs manquantes = NaN). Les colonnes techniques ``__*__`` sont
    communes et permettent au pipeline d'inférence de traiter les deux sources
    de manière homogène. Une colonne ``source`` est conservée via ``__source__``.
    """
    frames = []
    if mdtc_path:
        frames.append(load_mdtc(mdtc_path, cfg))
    if mopinion_path:
        frames.append(load_mopinion(mopinion_path, cfg))
    if not frames:
        raise ValueError("Aucun fichier source fourni (mdtc et mopinion absents).")
    combined = pd.concat(frames, ignore_index=True, sort=False)
    return combined
