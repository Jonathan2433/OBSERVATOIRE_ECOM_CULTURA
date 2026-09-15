"""Chargeur des exports Cultura 2026 — lot L1a (docs/SPEC_CHARGEUR.md).

Remplace ``loader.py``, dont **aucun mapping ne survit** face aux fichiers réels :
``Niveau de satisfaction général`` -> ``Satisfaction``, ``Verbatim justification``
-> ``Justification niveau de satisfaction``, ``Date de commande`` -> ``Date
d'achat``… Zéro survivant, mesuré le 09/09/2026.

Principe directeur (§9) : **échouer bruyamment sur un défaut de structure,
journaliser sur un défaut de contenu.** Le chargeur précédent dégradait en
silence — c'est ce qui a permis aux défauts du prototype de rester invisibles
deux mois.

Sortie : un ``DataFrame`` à **une ligne par verbatim** (et non par répondant,
D-17/D-30), plus un rapport de chargement JSON (§9.3) qui rend la prochaine
livraison Cultura indolore : un simple diff dira si un nouveau défaut est apparu.
"""
from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.preprocessing.column_norm import assert_no_collision, normalize_column_name
from src.preprocessing.label_norm import (
    ANNOTATION_RECOPIEE,
    COUPLE_INVALIDE,
    LabelNormalizer,
    SENTIMENT_ABSENT,
    SOUSTHEME_HORS_PERIMETRE,
    TEXTE_COURT,
    TEXTE_VIDE,
    fold,
    is_blank,
)
from src.utils.taxonomy import Taxonomy

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Contrat interne de sortie (§2)
# --------------------------------------------------------------------------- #
COL_SOURCE = "__source__"
COL_RESPONDENT = "__respondent_id__"
COL_FIELD = "__field__"
COL_TEXT = "__text_raw__"
COL_SATISFACTION = "__satisfaction__"
COL_SATISFACTION_RAW = "__satisfaction_raw__"
COL_DATE = "__date__"
COL_PAGE_TYPE = "__page_type__"
COL_URL = "__url__"
COL_DEVICE = "__device__"
COL_ANOMALIES = "__anomalies__"
COL_FICHIER = "__fichier__"

#: Colonnes d'annotation produites, en libellés canoniques du référentiel.
ANNOTATION_OUT = [
    "theme1_niv1", "theme1_niv2", "theme2_niv1", "theme2_niv2",
    "sentiment", "signal",
]

OUTPUT_ORDER = [
    COL_SOURCE, COL_FICHIER, COL_RESPONDENT, COL_FIELD, COL_TEXT,
    COL_SATISFACTION, COL_SATISFACTION_RAW, COL_DATE,
    COL_PAGE_TYPE, COL_URL, COL_DEVICE,
    *ANNOTATION_OUT, COL_ANOMALIES,
]


# --------------------------------------------------------------------------- #
#  Échecs de structure (§9.1) — la lecture s'arrête
# --------------------------------------------------------------------------- #
class ChargeurError(ValueError):
    """Erreur de structure : la lecture s'arrête."""


class SchemaInconnuError(ChargeurError):
    """Aucun — ou plusieurs — schéma(s) ne correspond(ent) au jeu de colonnes (R-18)."""


class ColonneManquanteError(ChargeurError):
    """Une colonne attendue par le schéma est absente : le fichier n'est pas celui annoncé."""


class EncodageError(ChargeurError):
    """Encodage indétectable — éviter tout remplacement silencieux de caractères."""


# --------------------------------------------------------------------------- #
#  Rapport de chargement (§9.3)
# --------------------------------------------------------------------------- #
@dataclass
class RapportFichier:
    """Décomptes d'un fichier.

    Les anomalies sont comptées à **deux mailles**, et c'est délibéré :

    - ``anomalies_annotation`` — une fois par ligne source. C'est la maille de
      l'audit du 09/09 : directement diffable avec ``AUDIT_DONNEES §4``.
    - ``anomalies_verbatim`` — une fois par verbatim émis. Un répondant Mopinion
      renseignant 4 champs produit 4 verbatims qui portent la même annotation ;
      compter à cette maille gonflerait mécaniquement les volumes (mesuré :
      ``ANNOTATION_RECOPIEE`` 6 annotations -> 12 verbatims).
    """

    fichier: str
    schema: str
    encodage: str
    lignes_lues: int = 0
    verbatims_produits: int = 0
    lignes_sans_texte: int = 0
    verbatims_non_classables: int = 0
    lignes_annotees: int = 0
    anomalies_annotation: Counter = field(default_factory=Counter)
    anomalies_verbatim: Counter = field(default_factory=Counter)
    #: Détail par emplacement de thème (``theme1`` / ``theme2``). L'audit du 09/09
    #: n'a mesuré que le thème 1 ; la ventilation rend les deux comparables.
    couples_invalides: Counter = field(default_factory=Counter)
    hors_perimetre: Counter = field(default_factory=Counter)
    #: Champs de contexte renseignés (D-30) : `vus` compte toutes les valeurs de
    #: la source, `rattaches` celles portées par un verbatim émis. L'écart, ce
    #: sont les répondants n'ayant rempli QUE ce champ — donnée structurée sans
    #: verbatim porteur.
    contexte_vus: Counter = field(default_factory=Counter)
    contexte_rattaches: Counter = field(default_factory=Counter)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fichier": self.fichier,
            "schema": self.schema,
            "encodage": self.encodage,
            "lignes_lues": self.lignes_lues,
            "verbatims_produits": self.verbatims_produits,
            "lignes_sans_texte": self.lignes_sans_texte,
            "verbatims_non_classables_ecartes": self.verbatims_non_classables,
            "lignes_annotees": self.lignes_annotees,
            "anomalies_annotation": dict(sorted(self.anomalies_annotation.items())),
            "anomalies_verbatim": dict(sorted(self.anomalies_verbatim.items())),
            "couples_invalides": dict(sorted(self.couples_invalides.items())),
            "sous_themes_hors_perimetre": dict(sorted(self.hors_perimetre.items())),
            "champs_contexte": {
                nom: {"vus": n, "rattaches_a_un_verbatim": self.contexte_rattaches.get(nom, 0)}
                for nom, n in sorted(self.contexte_vus.items())
            },
        }


# --------------------------------------------------------------------------- #
#  Lecture brute
# --------------------------------------------------------------------------- #
def read_table(path: Path, encodages: Sequence[str], separateur: str) -> Tuple[pd.DataFrame, str]:
    """Lit un CSV (séparateur configuré) ou un XLSX, en texte brut.

    ``keep_default_na=False`` est délibéré : pandas transformerait sinon des
    verbatims comme « NA » ou « null » en valeurs manquantes.
    """
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str, keep_default_na=False, na_values=[]), "xlsx"

    derniere: Optional[Exception] = None
    for enc in encodages:
        try:
            df = pd.read_csv(path, sep=separateur, dtype=str, encoding=enc,
                             keep_default_na=False, na_values=[])
        except (UnicodeDecodeError, UnicodeError) as exc:
            derniere = exc
            continue
        if df.shape[1] <= 1:
            derniere = ValueError(
                f"une seule colonne détectée avec le séparateur {separateur!r}"
            )
            continue
        return df, enc
    raise EncodageError(
        f"Encodage indétectable pour {path.name} (essayés : {list(encodages)}). "
        f"Dernière erreur : {derniere}"
    )


# --------------------------------------------------------------------------- #
#  Détection de schéma (§3) — par le jeu de colonnes, jamais par le nom du fichier
# --------------------------------------------------------------------------- #
def detect_schema(colonnes_normalisees: Sequence[str],
                  schemas: Dict[str, Any],
                  contexte: str) -> str:
    """Retourne le nom du schéma reconnu, ou échoue (§9.1).

    Une entrée de ``signature`` préfixée par ``!`` exige l'**absence** de la
    colonne : c'est ce qui distingue MDTC post-réception de MDTC post-achat,
    dont il est un sous-ensemble strict.
    """
    presentes = set(colonnes_normalisees)
    reconnus = []
    for nom, spec in schemas.items():
        ok = True
        for exigence in spec.get("signature", []):
            if exigence.startswith("!"):
                if exigence[1:] in presentes:
                    ok = False
                    break
            elif exigence not in presentes:
                ok = False
                break
        if ok:
            reconnus.append(nom)

    if len(reconnus) == 1:
        return reconnus[0]
    if not reconnus:
        raise SchemaInconnuError(
            f"[{contexte}] Aucun schéma connu ne correspond au jeu de colonnes "
            f"({len(presentes)} colonnes). Un cinquième schéma est probablement "
            f"apparu (R-18) : déclarer le schéma dans `cultura_sources.schemas`. "
            f"Colonnes lues : {sorted(presentes)}"
        )
    raise SchemaInconnuError(
        f"[{contexte}] Plusieurs schémas correspondent ({reconnus}) : les "
        "signatures ne sont pas discriminantes."
    )


def _colonnes_attendues(spec: Dict[str, Any], annotation: Dict[str, str]) -> List[str]:
    """Toutes les colonnes que le chargeur lira effectivement pour ce schéma."""
    attendues = list(spec.get("champs_libres", []))
    attendues += list((spec.get("champs_contexte") or {}).values())
    attendues += list((spec.get("meta") or {}).values())
    attendues += list(annotation.values())
    if spec.get("satisfaction_col"):
        attendues.append(spec["satisfaction_col"])
    if spec.get("respondent_id_col"):
        attendues.append(spec["respondent_id_col"])
    return sorted(set(attendues))


# --------------------------------------------------------------------------- #
#  Satisfaction (§7)
# --------------------------------------------------------------------------- #
def normaliser_satisfaction(brut: object, echelle: Dict[str, Any]) -> Tuple[Optional[int], str]:
    """Convertit une note vers l'échelle 1–4 commune. Retourne ``(note, brut)``.

    Accepte une note **numérique** ou un **libellé textuel** (« Très satisfait(e) »).
    Les exports MDTC de production donnent la satisfaction en toutes lettres là où
    la livraison d'entraînement l'encode en chiffres ; sans la table `libelles`
    déclarée en configuration, la note serait silencieusement perdue — et avec
    elle le préfixe de satisfaction du modèle de sentiment et la règle
    déterministe d'insatisfaction.
    """
    brut_txt = "" if brut is None else str(brut).strip()
    if is_blank(brut):
        return None, brut_txt
    try:
        valeur = int(round(float(brut_txt.replace(",", "."))))
    except (TypeError, ValueError):
        # Pas un nombre : tenter la table de libellés, en comparaison tolérante.
        libelles = echelle.get("libelles") or {}
        if libelles:
            cible = fold(brut_txt)
            for libelle, note in libelles.items():
                if fold(libelle) == cible:
                    return int(note), brut_txt
        return None, brut_txt
    attendues = echelle.get("valeurs_attendues") or []
    if attendues and valeur not in attendues:
        return None, brut_txt
    conversion = echelle.get("conversion")
    if conversion:
        valeur = int(conversion.get(valeur, conversion.get(str(valeur), valeur)))
    return valeur, brut_txt


# --------------------------------------------------------------------------- #
#  Dates (§2 — `__date__` est contractuellement en ISO)
# --------------------------------------------------------------------------- #
#: Formats rencontrés : `01/08/2026` (CSV MDTC, jour en tête) et
#: `2026-03-07 10:25:45` (Mopinion, XLSX post-réception).
_FORMATS_DATE = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                 "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def neutraliser_url(brut: object) -> str:
    """Retire la partie interrogative et le fragment d'une URL.

    Mesuré le 15/09/2026 sur l'export Mopinion desktop : 4 URL sur 480 portent
    un identifiant de commande dans leur requête
    (``/account?orderId=P90000003#Order``). Le chemin, lui, porte le signal utile
    — de quelle page vient le retour — et aucune donnée personnelle.

    On ne masque pas, on **tronque** : une URL de page compte reste identifiable
    comme telle (``/account``) sans emporter l'identifiant. C'est la même logique
    que la liste blanche des colonnes (D-18) — ne pas lire plutôt qu'anonymiser.
    """
    txt = ("" if brut is None else str(brut)).strip()
    if not txt:
        return ""
    for separateur in ("?", "#"):
        txt = txt.split(separateur, 1)[0]
    return txt


def normaliser_date(brut: object) -> str:
    """Convertit une date source en ISO 8601. Chaîne vide si non interprétable.

    Le jour est en tête dans les exports MDTC (`01/08/2026` = 1er août) : une
    lecture mois-en-tête inverserait silencieusement 11 mois sur 12.
    """
    from datetime import datetime

    txt = ("" if brut is None else str(brut)).strip()
    if not txt or txt.lower() in {"nan", "nat", "none"}:
        return ""
    for fmt in _FORMATS_DATE:
        try:
            dt = datetime.strptime(txt, fmt)
        except ValueError:
            continue
        if dt.hour or dt.minute or dt.second:
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y-%m-%d")
    logger.debug("Date non interprétable, conservée vide : %r", txt)
    return ""


# --------------------------------------------------------------------------- #
#  Chargement d'un fichier
# --------------------------------------------------------------------------- #
def _compter_tokens(texte: str) -> int:
    return len([t for t in texte.split() if t])


def _resoudre_annotation(row, annotation: Dict[str, str], normalizer: LabelNormalizer,
                         anomalies_annotation: List[str], rapport: "RapportFichier"):
    """Résout l'annotation Cultura d'une ligne. Extrait de ``charger_fichier``.

    Comportement inchangé : la seule raison de l'extraction est de pouvoir la
    SAUTER sur un export de production, qui ne porte aucune annotation.
    """
    t1, code = normalizer.resolve_theme(row.get(annotation["theme1_niv1"]))
    if code:
        anomalies_annotation.append(code)
    s1, code = normalizer.resolve_sous_theme(row.get(annotation["theme1_niv2"]))
    if code:
        anomalies_annotation.append(code)
    t2, code = normalizer.resolve_theme(row.get(annotation["theme2_niv1"]))
    if code:
        anomalies_annotation.append(code)
    s2, code = normalizer.resolve_sous_theme(row.get(annotation["theme2_niv2"]))
    if code:
        anomalies_annotation.append(code)
    signal, code = normalizer.resolve_signal(row.get(annotation["signal"]))
    if code:
        anomalies_annotation.append(code)
    sentiment, _ = normalizer.resolve_sentiment(row.get(annotation["sentiment"]))

    # §8.4 — couples invalides : écartés et journalisés, jamais corrigés.
    # Ils valent plus comme matière première de l'atelier de règles
    # d'arbitrage (L3) que comme correction : (Général, Retrait magasin)
    # ×11 n'est pas une faute de frappe mais une divergence d'interprétation.
    for slot, (tn, sn) in (("theme1", (t1, s1)), ("theme2", (t2, s2))):
        if tn and sn and not normalizer.couple_valide(tn, sn):
            if COUPLE_INVALIDE not in anomalies_annotation:
                anomalies_annotation.append(COUPLE_INVALIDE)
            rapport.couples_invalides[f"{slot} | {tn} > {sn}"] += 1
    # D-32 — sous-thème sous le seuil : conservé pour le niveau 1, exclu du niveau 2.
    for slot, sn in (("theme1", s1), ("theme2", s2)):
        if normalizer.hors_perimetre(sn):
            if SOUSTHEME_HORS_PERIMETRE not in anomalies_annotation:
                anomalies_annotation.append(SOUSTHEME_HORS_PERIMETRE)
            rapport.hors_perimetre[f"{slot} | {sn}"] += 1

    est_annote = t1 is not None or t2 is not None
    if est_annote and sentiment is None:
        anomalies_annotation.append(SENTIMENT_ABSENT)
    return t1, s1, t2, s2, signal, sentiment, est_annote


def charger_fichier(path: Path,
                    cfg_sources: Dict[str, Any],
                    normalizer: Optional[LabelNormalizer],
                    min_tokens: int,
                    annote: bool = True) -> Tuple[List[Dict[str, Any]], RapportFichier]:
    """Lit un fichier et produit ses verbatims + son rapport.

    ``annote=False`` lit un export **de production** : même schéma, mêmes champs
    libres, même liste blanche, mais **sans colonnes d'annotation**. C'est le cas
    des exports mensuels à classer, qui n'ont ni thème ni sentiment — ils
    viennent chercher une prédiction, pas la fournir.

    Dans ce mode, ``normalizer`` peut valoir ``None`` : il ne sert qu'à résoudre
    les libellés annotés. Cela évite d'exiger le référentiel Cultura au
    chargement — un fichier que le conteneur du worker ne monte pas, et dont la
    lecture d'un export de production n'a aucun besoin.

    Un seul chargeur sert les deux usages, délibérément. Deux chargeurs
    divergeraient : la liste blanche qui protège les données personnelles, la
    composition D-30 et la détection de schéma seraient à maintenir en double, et
    c'est toujours la copie oubliée qui laisse passer une colonne de trop.
    """
    df, encodage = read_table(path,
                              cfg_sources.get("encodages", ["utf-8-sig"]),
                              cfg_sources.get("separateur_csv", ";"))

    # §4 — normalisation des libellés + contrôle de collision (échec si fusion).
    normalisees = assert_no_collision(df.columns, path.name)
    df = df.copy()
    df.columns = normalisees

    annotation = cfg_sources["colonnes_annotation"] if annote else {}
    schemas = cfg_sources["schemas"]
    nom_schema = detect_schema(normalisees, schemas, path.name)
    spec = schemas[nom_schema]

    manquantes = [c for c in _colonnes_attendues(spec, annotation) if c not in set(normalisees)]
    if manquantes:
        raise ColonneManquanteError(
            f"[{path.name}] Schéma {nom_schema} : colonnes attendues absentes "
            f"{manquantes}. Le fichier n'est pas celui annoncé."
        )

    echelle = cfg_sources["echelles_satisfaction"][spec["echelle_satisfaction"]]
    champs = list(spec.get("champs_libres", []))
    composition = spec.get("composition", "un_par_champ")
    separateur_concat = spec.get("separateur_concat", ". ")
    contexte = spec.get("champs_contexte") or {}
    meta = spec.get("meta") or {}
    id_col = spec.get("respondent_id_col")

    rapport = RapportFichier(fichier=path.name, schema=nom_schema,
                             encodage=encodage, lignes_lues=len(df))
    lignes: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        # --- annotation du répondant (partagée par ses verbatims) --------------
        anomalies_annotation: List[str] = []
        if not annote:
            # Export de production : rien à résoudre, rien à contrôler. Les
            # champs d'annotation restent vides et le verbatim part en
            # prédiction.
            t1 = s1 = t2 = s2 = signal = sentiment = None
            est_annote = False
        else:
            t1, s1, t2, s2, signal, sentiment, est_annote = _resoudre_annotation(
                row, annotation, normalizer, anomalies_annotation, rapport)

        satisfaction, satisfaction_raw = normaliser_satisfaction(
            row.get(spec["satisfaction_col"]) if spec.get("satisfaction_col") else None,
            echelle,
        )

        respondent = (str(row.get(id_col)).strip() if id_col
                      else f"{nom_schema}-{path.stem}-{idx}")

        base: Dict[str, Any] = {
            COL_SOURCE: nom_schema,
            COL_FICHIER: path.name,
            COL_RESPONDENT: respondent,
            COL_SATISFACTION: satisfaction,
            COL_SATISFACTION_RAW: satisfaction_raw,
            "theme1_niv1": t1, "theme1_niv2": s1,
            "theme2_niv1": t2, "theme2_niv2": s2,
            "sentiment": sentiment, "signal": signal,
        }
        for interne, source in meta.items():
            valeur = str(row.get(source, "")).strip()
            if interne == COL_DATE:
                valeur = normaliser_date(valeur)
            elif interne == COL_URL:
                valeur = neutraliser_url(valeur)
            base[interne] = valeur
        for interne, source in contexte.items():
            valeur = str(row.get(source, "")).strip()
            base[interne] = valeur
            if not is_blank(valeur):
                rapport.contexte_vus[interne] += 1

        # --- composition du verbatim (§5) --------------------------------------
        # `bruts` : champs non vides au sens littéral. `remplis` : champs qui
        # portent réellement du texte, après la règle 1 de §5.2 (« ponctuation
        # seule ne produit aucune ligne »). L'écart entre les deux est compté :
        # c'est ce qui réconcilie le total avec le 7 552 annoncé en §11.
        bruts = [(c, str(row.get(c, "")).strip()) for c in champs
                 if str(row.get(c, "")).strip()]
        remplis = [(c, v) for c, v in bruts if not is_blank(v)]

        if composition == "concat":
            # D-30 : deux formulations du même retour, par le même client, sur la
            # même commande. La concaténation ramène le verbatim au niveau du
            # répondant, qui est le niveau de l'annotation Cultura.
            textes = [[separateur_concat.join(v for _, v in remplis),
                       " + ".join(c for c, _ in remplis)]] if remplis else []
            perdus = (1 if bruts and not remplis else 0)
        else:
            textes = [[v, c] for c, v in remplis]
            perdus = len(bruts) - len(remplis)
        rapport.verbatims_non_classables += perdus

        for code in set(anomalies_annotation):
            rapport.anomalies_annotation[code] += 1

        if not textes:
            rapport.lignes_sans_texte += 1
            continue

        for interne in contexte:
            if not is_blank(base.get(interne)):
                rapport.contexte_rattaches[interne] += 1

        # §5.2 règle 3 — un répondant Mopinion multi-champs annoté verrait son
        # annotation recopiée sur chaque champ : marqué et écarté de l'entraînement.
        recopiee = est_annote and composition != "concat" and len(textes) > 1
        if recopiee:
            rapport.anomalies_annotation[ANNOTATION_RECOPIEE] += 1
        if est_annote:
            rapport.lignes_annotees += 1

        for texte, nom_champ in textes:
            anomalies = list(anomalies_annotation)
            if recopiee:
                anomalies.append(ANNOTATION_RECOPIEE)
            if _compter_tokens(texte) < min_tokens:
                anomalies.append(TEXTE_COURT)
                rapport.anomalies_annotation[TEXTE_COURT] += 1
            ligne = dict(base)
            ligne[COL_FIELD] = nom_champ
            ligne[COL_TEXT] = texte
            ligne[COL_ANOMALIES] = anomalies
            lignes.append(ligne)
            for a in anomalies:
                rapport.anomalies_verbatim[a] += 1

    rapport.verbatims_produits = len(lignes)
    return lignes, rapport


# --------------------------------------------------------------------------- #
#  Point d'entrée
# --------------------------------------------------------------------------- #
def charger_cultura(cfg: Dict[str, Any],
                    data_dir: Optional[Path] = None,
                    taxonomy: Optional[Taxonomy] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Charge l'intégralité d'une livraison Cultura.

    Retourne ``(DataFrame, rapport)``. Le ``DataFrame`` porte une ligne par
    verbatim et **uniquement** les colonnes du contrat interne (§2) : les
    colonnes écartées par D-18 ne peuvent pas atteindre l'aval, puisque seules
    les colonnes déclarées en configuration sont recopiées (liste blanche).
    """
    from src.utils.config import resolve_path
    from src.preprocessing.anonymizer import verifier_ner_disponible

    # §10.3 — contrôle explicite AU DÉMARRAGE, jamais en cours de traitement :
    # un masquage muet des noms propres est un risque RGPD (ENF-5, R-14).
    verifier_ner_disponible(cfg)

    cfg_sources = cfg["cultura_sources"]
    racine = Path(data_dir) if data_dir else resolve_path(cfg, cfg_sources["data_dir"])
    if not racine.is_dir():
        raise ChargeurError(f"Répertoire de livraison introuvable : {racine}")

    if taxonomy is None:
        taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg_sources["taxonomy"]))

    normalizer = LabelNormalizer(taxonomy, cfg["label_normalization"])
    inconnus = normalizer.libelles_hors_perimetre_inconnus()
    if inconnus:
        raise ChargeurError(
            "`label_normalization.sous_themes_hors_perimetre` contient des libellés "
            f"absents du référentiel : {inconnus}. Une faute de frappe y laisserait "
            "silencieusement un sous-thème dans le périmètre du modèle (D-32)."
        )

    min_tokens = int(cfg.get("cleaning", {}).get("min_tokens", 0))

    fichiers = sorted(p for p in racine.rglob("*")
                      if p.is_file() and p.suffix.lower() in (".csv", ".xlsx", ".xls"))
    if not fichiers:
        raise ChargeurError(f"Aucun fichier CSV/XLSX dans {racine}")

    toutes: List[Dict[str, Any]] = []
    rapports: List[Dict[str, Any]] = []
    anomalies_annotation: Counter = Counter()
    anomalies_verbatim: Counter = Counter()
    par_schema: Dict[str, int] = defaultdict(int)
    couples_invalides: Counter = Counter()
    hors_perimetre: Counter = Counter()
    contexte_vus: Counter = Counter()
    contexte_rattaches: Counter = Counter()
    non_classables = 0

    for path in fichiers:
        lignes, rapport = charger_fichier(path, cfg_sources, normalizer, min_tokens)
        toutes.extend(lignes)
        rapports.append(rapport.to_dict())
        anomalies_annotation.update(rapport.anomalies_annotation)
        anomalies_verbatim.update(rapport.anomalies_verbatim)
        par_schema[rapport.schema] += rapport.verbatims_produits
        non_classables += rapport.verbatims_non_classables
        couples_invalides.update(rapport.couples_invalides)
        hors_perimetre.update(rapport.hors_perimetre)
        contexte_vus.update(rapport.contexte_vus)
        contexte_rattaches.update(rapport.contexte_rattaches)

    df = pd.DataFrame(toutes)
    for col in OUTPUT_ORDER:
        if col not in df.columns:
            df[col] = None
    autres = [c for c in df.columns if c not in OUTPUT_ORDER]
    df = df[OUTPUT_ORDER + autres]

    rapport_global = {
        "livraison": str(racine),
        "referentiel": {"niv1": taxonomy.n_niv1, "niv2": taxonomy.n_niv2},
        "fichiers_lus": len(fichiers),
        "lignes_lues": int(sum(r["lignes_lues"] for r in rapports)),
        "verbatims_produits": int(len(df)),
        "verbatims_par_schema": dict(sorted(par_schema.items())),
        "lignes_annotees": int(sum(r["lignes_annotees"] for r in rapports)),
        # Réconciliation avec le total de 7 552 annoncé en §11 de SPEC_CHARGEUR :
        # ce total a été établi sans appliquer la règle 1 de §5.2 (« ponctuation
        # seule ne produit aucune ligne »). Les deux chiffres sont publiés pour
        # que l'écart soit vérifiable et non subi.
        "reconciliation_spec_11": {
            "verbatims_produits": int(len(df)),
            "textes_non_classables_ecartes": int(non_classables),
            "total_si_regle_1_non_appliquee": int(len(df) + non_classables),
        },
        "anomalies_par_annotation": dict(sorted(anomalies_annotation.items())),
        "anomalies_par_verbatim": dict(sorted(anomalies_verbatim.items())),
        "synonymes_appliques": dict(sorted(normalizer.synonymes_appliques.items())),
        "libelles_inconnus": {
            nature: dict(sorted(compteur.items()))
            for nature, compteur in normalizer.libelles_inconnus.items() if compteur
        },
        "candidats_synonymes": _candidats_synonymes(normalizer, taxonomy),
        "couples_invalides": dict(sorted(couples_invalides.items())),
        "sous_themes_hors_perimetre": dict(sorted(hors_perimetre.items())),
        "champs_contexte": {
            nom: {"vus": n, "rattaches_a_un_verbatim": contexte_rattaches.get(nom, 0)}
            for nom, n in sorted(contexte_vus.items())
        },
        "details_par_fichier": rapports,
    }
    return df, rapport_global


def _candidats_synonymes(normalizer: LabelNormalizer,
                         taxonomy: Taxonomy) -> Dict[str, List[Dict[str, Any]]]:
    """Libellés non résolus **proches** d'un libellé du référentiel.

    Proposés, jamais appliqués : ajouter un synonyme change l'espace de labels,
    ce qui relève d'un arbitrage du Product Owner, pas du chargeur. Rendre ces
    quasi-correspondances visibles évite qu'une simple faute de frappe fasse
    disparaître des lignes en silence à la prochaine livraison.
    """
    import difflib

    cibles = {"thème": taxonomy.niv1_labels, "sous-thème": taxonomy.niv2_labels}
    sortie: Dict[str, List[Dict[str, Any]]] = {}
    for nature, labels in cibles.items():
        index = {fold(l): l for l in labels}
        propositions = []
        for brut, n in normalizer.libelles_inconnus.get(nature, {}).items():
            proches = difflib.get_close_matches(fold(brut), list(index), n=1, cutoff=0.85)
            if proches:
                propositions.append({
                    "observe": brut,
                    "occurrences": n,
                    "proche_du_referentiel": index[proches[0]],
                })
        if propositions:
            sortie[nature] = sorted(propositions, key=lambda d: -d["occurrences"])
    return sortie


def ecrire_rapport(rapport: Dict[str, Any], chemin: Path) -> None:
    """Écrit le rapport de chargement (§9.3), livrable obligatoire du lot."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
