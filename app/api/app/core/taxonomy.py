"""Chargement léger de la taxonomie (référentiel) côté API.

Utilisé pour alimenter les listes contraintes de la revue humaine et valider
qu'un couple (niv.1, niv.2) appartient bien au référentiel. Stdlib uniquement
(pas de numpy) : l'API reste légère.

Deux sources fusionnées :
  * le référentiel « officiel » (fichier JSON monté en lecture seule) ;
  * les thèmes/sous-thèmes ajoutés à la volée en revue humaine, stockés en base
    (table ``taxonomy_entries``) et réutilisables ensuite.
"""
from __future__ import annotations

import functools
import json
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.models import TaxonomyEntry

from .config import settings


@functools.lru_cache(maxsize=1)
def load_taxonomy() -> Dict[str, Any]:
    with open(settings.taxonomy_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    themes = data["themes"]
    return {
        "themes": themes,
        "children": {t["niv1"]: list(t["niv2"]) for t in themes},
        "parent": {n2: t["niv1"] for t in themes for n2 in t["niv2"]},
        "niv1": [t["niv1"] for t in themes],
    }


def themes() -> List[dict]:
    return load_taxonomy()["themes"]


def is_valid_niv1(niv1: str) -> bool:
    return niv1 in load_taxonomy()["children"]


def is_valid_pair(niv1: str, niv2: str) -> bool:
    """Couple présent dans le référentiel *de base* (fichier JSON)."""
    return load_taxonomy()["parent"].get(niv2) == niv1


# --------------------------------------------------------------------------- #
#  Fusion référentiel de base + ajouts en base                                #
# --------------------------------------------------------------------------- #

def _norm(s: Optional[str]) -> str:
    """Clé de comparaison : sans espaces superflus, insensible à la casse."""
    return (s or "").strip().casefold()


def merged_themes(db: Session) -> List[dict]:
    """Référentiel de base + ajouts (``taxonomy_entries``), fusionnés.

    L'ordre du référentiel de base est conservé ; les thèmes/sous-thèmes ajoutés
    sont insérés à la suite (triés) sans jamais dupliquer un couple existant.
    """
    base = load_taxonomy()
    # Ordre des niv.1 : base d'abord, ajouts ensuite.
    order: List[str] = list(base["niv1"])
    order_norm = {_norm(n): n for n in order}
    # Enfants par niv.1, avec index de normalisation pour la déduplication.
    children: Dict[str, List[str]] = {n: list(base["children"][n]) for n in order}
    children_norm: Dict[str, set] = {n: {_norm(c) for c in children[n]} for n in order}

    entries = db.query(TaxonomyEntry).order_by(TaxonomyEntry.niv1, TaxonomyEntry.niv2).all()
    for e in entries:
        n1, n2 = (e.niv1 or "").strip(), (e.niv2 or "").strip()
        if not n1 or not n2:
            continue
        key1 = _norm(n1)
        display1 = order_norm.get(key1)
        if display1 is None:  # nouveau niv.1
            display1 = n1
            order.append(display1)
            order_norm[key1] = display1
            children[display1] = []
            children_norm[display1] = set()
        key2 = _norm(n2)
        if key2 not in children_norm[display1]:
            children[display1].append(n2)
            children_norm[display1].add(key2)

    return [{"niv1": n, "niv2": children[n]} for n in order]


def pair_is_known(db: Session, niv1: str, niv2: str) -> bool:
    """Couple connu (référentiel de base OU ajout en base), insensible à la casse
    et aux espaces — même normalisation (_norm) que la fusion/déduplication."""
    key1, key2 = _norm(niv1), _norm(niv2)
    if not key1 or not key2:
        return False
    # Référentiel de base : comparaison normalisée (is_valid_pair reste sensible à
    # la casse pour ses autres appelants ; ici on veut la clé de _norm).
    for n2, n1 in load_taxonomy()["parent"].items():
        if _norm(n2) == key2 and _norm(n1) == key1:
            return True
    # Ajouts en base : table minuscule -> itération directe, _norm fait foi. On évite
    # un pré-filtre SQL (ilike/lower non portable sur les accents FR : « CAFÉ » vs « café »).
    for e in db.query(TaxonomyEntry).all():
        if _norm(e.niv1) == key1 and _norm(e.niv2) == key2:
            return True
    return False


def register_pair(db: Session, niv1: str, niv2: str, user_id: Optional[int] = None) -> bool:
    """Enregistre un nouveau couple (niv.1, niv.2) s'il est inconnu.

    Renvoie ``True`` si un enregistrement a été créé, ``False`` s'il existait déjà.
    Ne committe pas : la transaction est gérée par l'appelant.
    """
    n1, n2 = (niv1 or "").strip(), (niv2 or "").strip()
    if not n1 or not n2:
        return False
    if pair_is_known(db, n1, n2):
        return False
    db.add(TaxonomyEntry(niv1=n1, niv2=n2, created_by=user_id))
    try:
        db.flush()  # matérialise l'insert pour capter une éventuelle collision d'unicité
    except IntegrityError:
        db.rollback()
        return False
    return True
