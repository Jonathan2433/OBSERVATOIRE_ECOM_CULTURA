"""Chargement léger de la taxonomie (référentiel) côté API.

Utilisé pour alimenter les listes contraintes de la revue humaine et valider
qu'un couple (niv.1, niv.2) appartient bien au référentiel. Stdlib uniquement
(pas de numpy) : l'API reste légère.

Deux sources fusionnées :
  * le référentiel « officiel » du **modèle actif** ;
  * les thèmes/sous-thèmes ajoutés à la volée en revue humaine, stockés en base
    (table ``taxonomy_entries``) et réutilisables ensuite.

Le référentiel suit le modèle actif
-----------------------------------
Depuis que plusieurs moteurs CamemBERT coexistent (arbitrage PO du 11/09), le
référentiel n'est plus une constante de déploiement. Les deux modèles ne
partagent **aucun** sous-thème (D-36 : 0 libellé commun sur 67/59) : servir à la
revue le référentiel du POC pendant que le modèle 2026 produit ses propres
libellés offrirait au relecteur une liste sans rapport avec ce qu'il relit, et
enregistrerait en base un couple « inconnu » à chaque correction.

Chaque modèle embarque donc son référentiel à sa racine (``taxonomy.json``), et
c'est celui du modèle actif qui est servi. Le fichier de ``settings`` reste le
repli — déploiement mono-modèle, ou modèle sans référentiel embarqué.
"""
from __future__ import annotations

import functools
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.models import TaxonomyEntry

from .config import settings


#: Nom du référentiel embarqué à la racine d'un modèle.
TAXONOMY_EMBARQUEE = "taxonomy.json"

logger = logging.getLogger("api.taxonomy")


@functools.lru_cache(maxsize=8)
def _charger(chemin: str) -> Dict[str, Any]:
    """Lit et indexe un fichier de référentiel. Mémoïsé PAR CHEMIN.

    Le cache était à une seule entrée : il figeait le premier référentiel lu
    pour la durée du processus, ce qui aurait servi l'ancien après une bascule
    de modèle.
    """
    with open(chemin, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    themes = data["themes"]
    return {
        "themes": themes,
        "children": {t["niv1"]: list(t["niv2"]) for t in themes},
        "parent": {n2: t["niv1"] for t in themes for n2 in t["niv2"]},
        "niv1": [t["niv1"] for t in themes],
        "_chemin": chemin,
    }


def chemin_referentiel(db: Optional[Session] = None,
                       model_label: Optional[str] = None) -> str:
    """Référentiel d'un modèle donné, du modèle actif sinon, du déploiement à défaut.

    ``model_label`` sert à relire un lot **produit par un autre moteur** que
    l'actif : c'est le cas dès qu'on bascule. Un relecteur qui reprend un lot
    ancien doit voir le référentiel du modèle qui l'a produit, pas celui qui se
    trouve actif au moment où il ouvre la page.

    Ne lève jamais : un référentiel introuvable fait retomber sur le fichier de
    ``settings``. Mieux vaut la liste de l'ancien modèle qu'une page de revue en
    erreur — mais le journal le dit, car cette liste serait trompeuse.
    """
    if db is None:
        return settings.taxonomy_path
    try:
        from common.models import MODEL_KIND_REAL, ModelVersion

        modele = None
        if model_label:
            modele = db.query(ModelVersion).filter_by(
                label=model_label, kind=MODEL_KIND_REAL).first()
        if modele is None:
            modele = db.query(ModelVersion).filter_by(
                is_active=True, available=True, kind=MODEL_KIND_REAL).first()
        if modele and modele.path:
            candidat = Path(modele.path) / TAXONOMY_EMBARQUEE
            if candidat.is_file():
                return str(candidat)
            logger.warning(
                "Modèle « %s » : aucun %s à sa racine (%s). Le référentiel "
                "de déploiement sera servi à la revue — il peut ne pas "
                "correspondre aux libellés que ce modèle produit.",
                modele.label, TAXONOMY_EMBARQUEE, modele.path)
    except Exception as exc:  # pragma: no cover - l'API ne doit pas tomber pour ça
        logger.warning("Référentiel du modèle indéterminable (%s).", exc)
    return settings.taxonomy_path


def load_taxonomy(db: Optional[Session] = None,
                  model_label: Optional[str] = None) -> Dict[str, Any]:
    """Référentiel de base à servir, celui du modèle concerné quand il est connu."""
    return _charger(chemin_referentiel(db, model_label))


def themes(db: Optional[Session] = None,
           model_label: Optional[str] = None) -> List[dict]:
    return load_taxonomy(db, model_label)["themes"]


def is_valid_niv1(niv1: str, db: Optional[Session] = None) -> bool:
    return niv1 in load_taxonomy(db)["children"]


def is_valid_pair(niv1: str, niv2: str, db: Optional[Session] = None) -> bool:
    """Couple présent dans le référentiel *de base* (fichier JSON)."""
    return load_taxonomy(db)["parent"].get(niv2) == niv1


# --------------------------------------------------------------------------- #
#  Fusion référentiel de base + ajouts en base                                #
# --------------------------------------------------------------------------- #

def _norm(s: Optional[str]) -> str:
    """Clé de comparaison : sans espaces superflus, insensible à la casse."""
    return (s or "").strip().casefold()


def merged_themes(db: Session, model_label: Optional[str] = None) -> List[dict]:
    """Référentiel de base + ajouts (``taxonomy_entries``), fusionnés.

    L'ordre du référentiel de base est conservé ; les thèmes/sous-thèmes ajoutés
    sont insérés à la suite (triés) sans jamais dupliquer un couple existant.

    ``model_label`` cible le référentiel d'un moteur précis — celui qui a produit
    le lot en cours de relecture, qui n'est pas forcément l'actif.
    """
    base = load_taxonomy(db, model_label)
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
    for n2, n1 in load_taxonomy(db)["parent"].items():
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
