"""Chargement et parsing des fichiers Excel sources (MDTC + Mopinion + historique).

Les deux sources de production ont des schémas de colonnes DIFFÉRENTS :
  - MDTC      : retours post-commande, texte principal = "Verbatim justification"
                (+ "Verbatim suggestion" en complément).
  - Mopinion  : formulaire libre, texte principal = "Description du bug" (insatisfaits)
                OU "Suggestion" (satisfaits) — on prend la (ou les) cellule(s) non vide(s).

Chaque loader renvoie le DataFrame d'origine INTACT (toutes les colonnes
préservées pour le CSV enrichi final) augmenté de colonnes techniques normalisées
(préfixées ``__`` pour éviter toute collision avec des colonnes métier) :

  __source__        : provenance, la plus FINE que le fichier permette
                      ("MDTC-postachat" / "MDTC-postrecep" quand le schéma de la
                      livraison Cultura 2026 est reconnu, "MDTC" sinon ; idem
                      Mopinion). La couche de décision s'appuie dessus pour ses
                      règles d'arbitrage contextuel — cf. src/inference/decision.py.
  __text_raw__      : texte brut à classifier (avant anonymisation/nettoyage)
  __satisfaction__  : score de satisfaction (int, NaN si absent)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

# Noms de colonnes techniques normalisées (contrat partagé avec le reste du pipeline)
COL_SOURCE = "__source__"
COL_TEXT = "__text_raw__"
COL_SATISFACTION = "__satisfaction__"
COL_SATISFACTION_NATIVE = "__satisfaction_native__"
COL_SATISFACTION_SCALE_MAX = "__satisfaction_scale_max__"
COL_SATISFACTION_INVALID = "__satisfaction_invalid__"
COL_SATISFACTION_RAW = "__satisfaction_raw__"
COL_RESPONDENT = "__respondent_id__"
COL_FICHIER = "__fichier__"
COL_CLIENT_STATUS = "__client_status__"
COL_DATE = "__date__"

logger = logging.getLogger(__name__)

SOURCE_MDTC = "MDTC"
SOURCE_MOPINION = "Mopinion"


def affiner_source(df: pd.DataFrame, source_grossiere: str,
                   cfg: Dict[str, Any]) -> str:
    """Précise la provenance quand le schéma de la livraison Cultura est reconnu.

    Les formulaires post-achat et post-réception arrivent sous la même étiquette
    « MDTC » alors qu'ils posent des questions différentes — et c'est
    précisément cette différence que la règle d'arbitrage contextuel exploite
    (38,6 % des erreurs de thème viennent du post-réception).

    Prudence délibérée : la source n'est affinée QUE si la signature de colonnes
    est positivement reconnue. Un export au format V1, dont les colonnes ne
    ressemblent à aucun schéma déclaré, garde l'étiquette grossière — la règle
    ne s'appliquera pas, ce qui est le comportement voulu : mieux vaut un levier
    inactif qu'un levier appliqué à un formulaire qu'on n'a pas identifié.
    """
    schemas = ((cfg.get("cultura_sources") or {}).get("schemas") or {})
    if not schemas:
        return source_grossiere
    candidats = {n: s for n, s in schemas.items()
                 if n.split("-")[0].lower() == source_grossiere.lower()}
    if not candidats:
        return source_grossiere
    from .column_norm import normalize_column_name
    from .cultura_loader import SchemaInconnuError, detect_schema

    colonnes = [normalize_column_name(c) for c in df.columns]
    try:
        return detect_schema(colonnes, candidats, source_grossiere)
    except SchemaInconnuError:
        # Format non reconnu : on reste sur l'étiquette grossière, sans échouer.
        # Le chargement mensuel ne doit pas s'interrompre parce qu'un levier
        # d'optimisation ne pourra pas s'appliquer.
        return source_grossiere


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
    out[COL_SOURCE] = affiner_source(df, SOURCE_MDTC, cfg)
    out[COL_TEXT] = out.apply(_build_text, axis=1)
    _ajouter_contexte_repondant(out, Path(path), cfg, conf["satisfaction_col"], 4,
                               client_status_col=conf.get("client_status_col"),
                               date_col=conf.get("date_col"))
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
    out[COL_SOURCE] = affiner_source(df, SOURCE_MOPINION, cfg)
    out[COL_TEXT] = out.apply(_build_text, axis=1)
    _ajouter_contexte_repondant(out, Path(path), cfg, conf["satisfaction_col"], 5,
                               conf.get("respondent_id_col"),
                               date_col=conf.get("date_col"))
    return out


def _ajouter_contexte_repondant(out: pd.DataFrame, path: Path, cfg: Dict[str, Any],
                                satisfaction_col: str, scale_max: int,
                                respondent_id_col: Optional[str] = None,
                                client_status_col: Optional[str] = None,
                                date_col: Optional[str] = None) -> None:
    """Complète le chemin historique avec le contrat répondant du chemin 2026."""
    from .cultura_loader import normaliser_date, normaliser_statut_client, opaque_respondent_key

    source = str(out[COL_SOURCE].iloc[0]) if len(out) else "inconnue"
    out[COL_FICHIER] = path.name

    def parse_native(value):
        if not _non_empty(value):
            return float("nan"), False
        try:
            number = float(value)
        except (TypeError, ValueError):
            return float("nan"), True
        if not number.is_integer() or not (1 <= int(number) <= scale_max):
            return float("nan"), True
        return int(number), False

    parsed = out[satisfaction_col].apply(parse_native)
    out[COL_SATISFACTION_NATIVE] = parsed.apply(lambda item: item[0])
    out[COL_SATISFACTION_SCALE_MAX] = scale_max
    out[COL_SATISFACTION_INVALID] = parsed.apply(lambda item: item[1])
    if scale_max == 5:
        conversion = {1: 1, 2: 2, 3: 2, 4: 3, 5: 4}
        out[COL_SATISFACTION] = out[COL_SATISFACTION_NATIVE].map(conversion)
    else:
        out[COL_SATISFACTION] = out[COL_SATISFACTION_NATIVE]
    out[COL_SATISFACTION_RAW] = out[satisfaction_col].fillna("").astype(str)
    mappings = (cfg.get("cultura_sources") or {}).get("statuts_client") or {}
    if client_status_col and client_status_col in out.columns:
        out[COL_CLIENT_STATUS] = out[client_status_col].apply(
            lambda value: normaliser_statut_client(value, mappings))
    else:
        out[COL_CLIENT_STATUS] = "non_renseigne"
    # La date est conservée sous la même forme ISO que dans le chargeur 2026.
    # Une colonne absente ou illisible reste vide : la couche KPI signalera que
    # la période métier n'est pas disponible, sans utiliser la date d'upload.
    if date_col and date_col in out.columns:
        out[COL_DATE] = out[date_col].apply(normaliser_date)
    else:
        out[COL_DATE] = ""
    out[COL_RESPONDENT] = [
        opaque_respondent_key(
            source, path.name,
            (row.get(respondent_id_col) if respondent_id_col and _non_empty(row.get(respondent_id_col))
             else f"row:{idx}"),
        )
        for idx, row in out.iterrows()
    ]


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
# --------------------------------------------------------------------------- #
#  Exports au format Cultura 2026 (CSV ou XLSX)
# --------------------------------------------------------------------------- #
#: Colonnes techniques et de contexte conservées d'un export 2026.
#: Tout le reste est écarté par la LISTE BLANCHE du chargeur (D-18) — c'est elle
#: qui garantit qu'un numéro de commande ou un identifiant client ne descend pas
#: dans la base ni dans l'export enrichi.
COLONNES_CONSERVEES_2026 = (
    "__source__", "__text_raw__", "__satisfaction__", "__satisfaction_native__",
    "__satisfaction_scale_max__", "__satisfaction_invalid__", "__satisfaction_raw__",
    "__respondent_id__", "__client_status__",
    "__field__", "__fichier__", "__date__", "__page_type__", "__url__", "__device__",
)


def detecter_schema_2026(path: str | Path, cfg: Dict[str, Any]) -> Optional[str]:
    """Nom du schéma Cultura 2026 reconnu pour ce fichier, ``None`` sinon.

    Ne lève jamais : un fichier au format V1, ou illisible, renvoie ``None`` et
    le chargement repart sur le chemin historique. La détection porte sur le
    JEU DE COLONNES, jamais sur le nom du fichier.
    """
    from .column_norm import normalize_column_name
    from .cultura_loader import SchemaInconnuError, read_table

    sources = cfg.get("cultura_sources") or {}
    if not sources.get("schemas"):
        return None
    try:
        df, _ = read_table(Path(path), sources.get("encodages", ["utf-8-sig"]),
                           sources.get("separateur_csv", ";"))
        from .cultura_loader import detect_schema

        return detect_schema([normalize_column_name(c) for c in df.columns],
                             sources["schemas"], Path(path).name)
    except SchemaInconnuError:
        return None
    except Exception as exc:  # fichier illisible : on laisse le chemin V1 trancher
        logger.debug("Détection 2026 impossible sur %s (%s).", Path(path).name, exc)
        return None


def load_cultura_2026(path: str | Path, cfg: Dict[str, Any]) -> pd.DataFrame:
    """Charge un export au format Cultura 2026 pour un traitement de lot.

    Réutilise le chargeur de la livraison Cultura en mode **production**
    (``annote=False``) : même détection de schéma, même liste blanche, même
    composition des champs libres (D-30), mais sans exiger les colonnes
    d'annotation — un export mensuel vient chercher une prédiction, pas la
    fournir.

    Ce chemin apporte trois choses que le chargeur historique ne sait pas faire :

    * il lit le **CSV** comme le XLSX, avec détection d'encodage ;
    * il produit la **source fine** (``MDTC-postrecep``…), sans laquelle la règle
      d'arbitrage contextuel de la couche de décision ne peut pas s'appliquer ;
    * il n'emporte que les colonnes **déclarées**, ce qui laisse dehors les
      numéros de commande et identifiants client présents dans les exports.
    """
    from .cultura_loader import charger_fichier

    sources = cfg["cultura_sources"]
    min_tokens = int(cfg.get("cleaning", {}).get("min_tokens", 0))

    # Pas de normaliseur de libellés : il ne sert qu'à résoudre une annotation,
    # et un export de production n'en porte aucune. Le demander imposerait de
    # monter le référentiel Cultura dans le conteneur du worker pour rien.
    lignes, rapport = charger_fichier(Path(path), sources, None,
                                      min_tokens, annote=False)
    logger.info(
        "Export Cultura 2026 « %s » : schéma %s · %d lignes lues · %d verbatims · "
        "%d ligne(s) sans texte", Path(path).name, rapport.schema,
        rapport.lignes_lues, rapport.verbatims_produits, rapport.lignes_sans_texte)

    if not lignes:
        return pd.DataFrame(columns=list(COLONNES_CONSERVEES_2026))
    out = pd.DataFrame(lignes)
    return out[[c for c in COLONNES_CONSERVEES_2026 if c in out.columns]].copy()


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
    for chemin, charger_v1, nom in ((mdtc_path, load_mdtc, "MDTC"),
                                    (mopinion_path, load_mopinion, "Mopinion")):
        if not chemin:
            continue
        frames.append(_charger_une_source(chemin, charger_v1, nom, cfg))
    if not frames:
        raise ValueError("Aucun fichier source fourni (mdtc et mopinion absents).")
    combined = pd.concat(frames, ignore_index=True, sort=False)
    return combined


def load_many(chemins: Sequence[str | Path], cfg: Dict[str, Any]) -> pd.DataFrame:
    """Charge un nombre quelconque d'exports dans un seul lot.

    Chaque fichier est identifié **par son jeu de colonnes** : il n'y a plus à
    déclarer lequel est MDTC et lequel est Mopinion, ni à se limiter à un de
    chaque. Un mois complet — post-achat ancien et nouveau, post-réception
    ancien et nouveau, Mopinion desktop et mobile — se dépose en une fois.

    Un fichier au format Cultura 2026 part vers le chargeur 2026 ; les autres
    sont routés vers le chargeur historique d'après leurs colonnes. Un fichier
    qui n'est reconnu par aucun des deux **fait échouer le lot** avec son nom :
    traiter un mois amputé d'une source sans le dire fausserait les volumes, et
    les volumes sont la raison d'être de l'outil.
    """
    if not chemins:
        raise ValueError("Aucun fichier source fourni.")

    frames, erreurs, resume = [], [], []
    for chemin in chemins:
        nom = Path(chemin).name
        try:
            df = _charger_un_fichier(chemin, cfg)
        except Exception as exc:
            erreurs.append(f"{nom} : {exc}")
            continue
        frames.append(df)
        sources = sorted(set(df[COL_SOURCE].dropna().unique())) if COL_SOURCE in df.columns else []
        resume.append(f"{nom} -> {', '.join(sources) or 'source inconnue'} ({len(df)})")

    if erreurs:
        raise ValueError(
            "Fichier(s) non exploitable(s) : " + " | ".join(erreurs) +
            ". Le lot n'est pas lancé : un mois amputé d'une source fausserait "
            "les volumes.")

    logger.info("Lot multi-fichiers : %s", " · ".join(resume))
    combined = pd.concat(frames, ignore_index=True, sort=False)
    return combined


def _charger_un_fichier(chemin: str | Path, cfg: Dict[str, Any]) -> pd.DataFrame:
    """Charge un export sans savoir à l'avance de quelle source il vient."""
    schema = detecter_schema_2026(chemin, cfg)
    if schema:
        logger.info("%s : format Cultura 2026 (%s).", Path(chemin).name, schema)
        return load_cultura_2026(chemin, cfg)

    # Format historique : on choisit le chargeur d'après les colonnes présentes,
    # et non d'après le nom du fichier, qui ne garantit rien.
    colonnes = set(_lire_entetes(chemin))
    mdtc = cfg["sources"]["mdtc"]
    mopinion = cfg["sources"]["mopinion"]
    if mdtc["text_col_primary"] in colonnes:
        logger.info("%s : format historique MDTC.", Path(chemin).name)
        return load_mdtc(chemin, cfg)
    if any(c in colonnes for c in mopinion["text_cols_primary"]):
        logger.info("%s : format historique Mopinion.", Path(chemin).name)
        return load_mopinion(chemin, cfg)
    raise ValueError(
        f"aucun format reconnu (ni Cultura 2026, ni historique). "
        f"Colonnes lues : {sorted(colonnes)[:8]}")


def _lire_entetes(chemin: str | Path) -> List[str]:
    """En-têtes d'un fichier, sans charger son contenu."""
    from .cultura_loader import read_table

    df, _ = read_table(Path(chemin), ["utf-8-sig", "cp1252", "iso-8859-1"], ";")
    return [str(c) for c in df.columns]


def _charger_une_source(chemin: str | Path, charger_v1, nom: str,
                        cfg: Dict[str, Any]) -> pd.DataFrame:
    """Aiguille un fichier vers le chargeur qui sait le lire.

    Le format est déduit du JEU DE COLONNES, jamais de l'extension ni du nom :
    un export au format Cultura 2026 part vers `load_cultura_2026`, tout le reste
    vers le chargeur historique. Aucun réglage à faire côté utilisateur — il
    dépose son fichier, l'application reconnaît ce que c'est.
    """
    schema = detecter_schema_2026(chemin, cfg)
    if schema:
        logger.info("[%s] %s : format Cultura 2026 reconnu (%s).",
                    nom, Path(chemin).name, schema)
        return load_cultura_2026(chemin, cfg)
    logger.info("[%s] %s : format historique.", nom, Path(chemin).name)
    return charger_v1(chemin, cfg)
