"""Normalisation des noms de colonnes des exports Cultura — lot L1a, §4 de SPEC_CHARGEUR.

Les libellés de colonnes varient entre deux exports d'une même source. Divergences
mesurées le 09/09/2026 sur ``Mopinion-mobile`` :

    jan-mai : "Avez-vous une remarque ou des idées à nous partager ?\\x0b"
    août    : "Avez-vous une remarque ou des idées à nous partager ??"

Le ``\\x0b`` (tabulation verticale) est **invisible** à l'affichage : c'est la cause
réelle de la divergence, pas seulement le ``?`` final. Sans normalisation, l'export
jan-mai perd ses champs libres en silence.

⚠️ **Les traits d'union ne sont jamais touchés.** ``Dites-nous en plus :`` et
``Dites nous en plus :`` sont deux colonnes DISTINCTES coexistant dans le même
fichier Mopinion mobile (colonnes 13 et 14, mesuré sur les deux exports). Une
normalisation qui les fusionnerait perdrait des verbatims — et, ici, ferait échouer
le chargement via :func:`normalize_columns` (c'est voulu : mieux vaut un échec
bruyant qu'une perte silencieuse).
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

# Caractères de contrôle C0 + DEL. L'espace insécable est traité à part (voir plus bas).
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
# Ponctuation et espaces en FIN de libellé : "… partager ??" == "… partager ?".
_TRAILING_RE = re.compile(r"[?!.\s]+$")
_WHITESPACE_RE = re.compile(r"\s+")

#: Espace insécable. Traité comme un espace, **non supprimé** — voir :func:`normalize_column_name`.
_NBSP = "\xa0"


class ColumnCollisionError(ValueError):
    """Deux colonnes distinctes d'un même fichier obtiennent le même nom normalisé.

    Signale une normalisation trop agressive (§9.1 de SPEC_CHARGEUR). Échec
    immédiat : la lecture s'arrête, plutôt que de laisser deux champs libres
    s'écraser l'un l'autre.
    """


def normalize_column_name(raw: object) -> str:
    """Forme canonique d'un libellé de colonne (§4).

    Étapes, dans cet ordre :

    1. espace insécable → espace, puis suppression des caractères de contrôle ;
    2. apostrophe typographique ``’`` → ``'`` ;
    3. suites d'espaces → un espace unique, puis rognage des deux bords ;
    4. suppression de la ponctuation et des espaces **en fin** de libellé ;
    5. passage en minuscules.

    .. note:: **Écart assumé avec la lettre de la spécification.** §4 demande de
       *supprimer* l'espace insécable au même titre que les caractères de contrôle.
       Le supprimer souderait les mots qu'il sépare (``"Date\\xa0d'achat"`` →
       ``"dated'achat"``), qui ne s'apparierait alors plus avec ``"Date d'achat"``
       d'une livraison suivante — précisément le défaut que §4 existe pour empêcher.
       Il est donc converti en espace. Aucune colonne des 9 fichiers du 09/09 ne
       contient de ``\\xa0`` : l'écart est sans effet sur la livraison courante et
       protège les suivantes.
    """
    s = str(raw).replace(_NBSP, " ")
    s = _CONTROL_RE.sub("", s)
    s = s.replace("’", "'")
    s = _WHITESPACE_RE.sub(" ", s).strip()
    s = _TRAILING_RE.sub("", s)
    return s.lower().strip()


def normalize_columns(columns: Iterable[object]) -> Tuple[List[str], Dict[str, List[str]]]:
    """Normalise une liste de libellés et détecte les collisions.

    Retourne ``(noms_normalisés, collisions)`` où ``collisions`` associe un nom
    normalisé à la liste des libellés d'origine (≥ 2) qui l'ont produit. Ne lève
    rien : c'est à l'appelant de décider, via :func:`assert_no_collision`.
    """
    originals = [str(c) for c in columns]
    normalized = [normalize_column_name(c) for c in originals]

    seen: Dict[str, List[str]] = {}
    for norm, orig in zip(normalized, originals):
        seen.setdefault(norm, []).append(orig)
    collisions = {norm: origs for norm, origs in seen.items() if len(origs) > 1}
    return normalized, collisions


def assert_no_collision(columns: Iterable[object], contexte: str) -> List[str]:
    """Normalise et **échoue** si deux colonnes distinctes se rejoignent (§9.1).

    ``contexte`` identifie le fichier dans le message d'erreur.
    """
    normalized, collisions = normalize_columns(columns)
    if collisions:
        detail = " ; ".join(
            f"{norm!r} <- {origs!r}" for norm, origs in sorted(collisions.items())
        )
        raise ColumnCollisionError(
            f"[{contexte}] La normalisation fusionne des colonnes distinctes : {detail}. "
            "La règle de normalisation est trop agressive (§4 de SPEC_CHARGEUR) — "
            "vérifier notamment que les traits d'union ne sont pas touchés."
        )
    return normalized
