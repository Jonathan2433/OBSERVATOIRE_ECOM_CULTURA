"""Chargement léger de la taxonomie (référentiel) côté API.

Utilisé pour alimenter les listes contraintes de la revue humaine et valider
qu'un couple (niv.1, niv.2) appartient bien au référentiel. Stdlib uniquement
(pas de numpy) : l'API reste légère.
"""
from __future__ import annotations

import functools
import json
from typing import Any, Dict, List

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
    return load_taxonomy()["parent"].get(niv2) == niv1
