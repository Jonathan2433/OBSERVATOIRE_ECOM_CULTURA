"""Normalisation des labels annotés par Cultura — lot L1a, §8 de SPEC_CHARGEUR (D-31).

Portée par le chargeur et non par un script de nettoyage jetable : Cultura
re-livrera les fichiers, et un nettoyage manuel serait à refaire à chaque
livraison. Écrit une fois, appliqué à toutes.

Ordre de résolution d'un libellé (§8.2) :

1. correspondance **exacte** avec le référentiel ;
2. correspondance **tolérante** (casse, accents, espaces, apostrophes) ;
3. **groupe de synonymes** déclaré en configuration ;
4. sinon : anomalie journalisée, ligne écartée.

Le libellé canonique est toujours **celui du référentiel** (D-7 : le référentiel
appartient à Cultura, eXalt ne le modifie pas). Les groupes de synonymes ne
nomment pas le canonique — ils déclarent des graphies équivalentes, et le
canonique est celui des membres qui figure au référentiel. Si Cultura corrige
« Attente comm​mande » en « Attente commande », la configuration reste valable.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
#  Codes d'anomalie (§9.2). Volumes mesurés sur la livraison du 09/09/2026.
# --------------------------------------------------------------------------- #
THEME_INCONNU = "THEME_INCONNU"                          # 5
SOUSTHEME_INCONNU = "SOUSTHEME_INCONNU"                  # 5
COUPLE_INVALIDE = "COUPLE_INVALIDE"                      # 18
SENTIMENT_ABSENT = "SENTIMENT_ABSENT"                    # 572
SIGNAL_INCONNU = "SIGNAL_INCONNU"                        # 0
TEXTE_VIDE = "TEXTE_VIDE"
TEXTE_COURT = "TEXTE_COURT"
ANNOTATION_RECOPIEE = "ANNOTATION_RECOPIEE"              # 6
SOUSTHEME_HORS_PERIMETRE = "SOUSTHEME_HORS_PERIMETRE"    # 58 lignes / 16 sous-thèmes

_WHITESPACE_RE = re.compile(r"\s+")


class TaxonomySynonymError(ValueError):
    """Un groupe de synonymes ne se rattache pas proprement au référentiel.

    Levée au démarrage, jamais en cours de traitement : une table de synonymes
    incohérente avec le référentiel livré doit se voir immédiatement.
    """


def fold(value: object) -> str:
    """Forme tolérante d'un libellé : casse, accents, espaces, apostrophes.

    Les traits d'union sont **préservés** (cohérent avec ``column_norm``).
    """
    s = str(value).replace("’", "'")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = _WHITESPACE_RE.sub(" ", s).strip().lower()
    return s


def is_blank(value: object) -> bool:
    """True si la cellule est vide au sens des exports Cultura.

    Couvre ``None``, ``NaN``, la chaîne vide, les espaces seuls, les littéraux
    ``nan`` / ``none`` produits par les conversions, et la ponctuation seule
    (« . », « , » — observées telles quelles dans les verbatims réels).
    """
    if value is None:
        return True
    # NaN (float) sans dépendre de pandas dans ce module.
    if isinstance(value, float) and value != value:
        return True
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return True
    return not any(ch.isalnum() for ch in s)


class LabelNormalizer:
    """Résout les libellés annotés vers les libellés canoniques du référentiel."""

    def __init__(self, taxonomy: Any, cfg: Dict[str, Any]):
        self.taxonomy = taxonomy
        self.cfg = cfg

        self._niv1 = list(taxonomy.niv1_labels)
        self._niv2 = list(taxonomy.niv2_labels)
        self._niv1_fold = {fold(l): l for l in self._niv1}
        self._niv2_fold = {fold(l): l for l in self._niv2}

        self._syn_niv1 = self._build_groups(cfg.get("groupes_themes", []),
                                            self._niv1_fold, "thème")
        self._syn_niv2 = self._build_groups(cfg.get("groupes_sous_themes", []),
                                            self._niv2_fold, "sous-thème")

        self._signaux = {fold(k): v for k, v in (cfg.get("signaux") or {}).items()}
        self._sentiments = {fold(s): s for s in (cfg.get("sentiments_attendus") or [])}
        self._hors_perimetre = {fold(s) for s in (cfg.get("sous_themes_hors_perimetre") or [])}

        #: Compteur des synonymes réellement appliqués — porté au rapport (§9.3).
        self.synonymes_appliques: Counter = Counter()
        #: Libellés non résolus, par nature ("thème" / "sous-thème" / "signal").
        #: Alimente les *candidats synonymes* du rapport : c'est ce qui rendra la
        #: prochaine livraison Cultura indolore, en rendant visible une nouvelle
        #: graphie au lieu de la laisser tomber en silence.
        self.libelles_inconnus: Dict[str, Counter] = {
            "thème": Counter(), "sous-thème": Counter(), "signal": Counter(),
        }

    # ------------------------------------------------------------------ #
    #  Construction des tables de synonymes
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_groups(groups: Sequence[Sequence[str]],
                      referential_fold: Dict[str, str],
                      kind: str) -> Dict[str, str]:
        """Associe chaque graphie d'un groupe au membre présent au référentiel.

        Échoue si un groupe n'a aucun membre au référentiel (table obsolète) ou
        en a plusieurs (le mapping serait ambigu).
        """
        table: Dict[str, str] = {}
        for group in groups:
            members = list(group)
            in_ref = [referential_fold[fold(m)] for m in members if fold(m) in referential_fold]
            in_ref = sorted(set(in_ref))
            if len(in_ref) == 0:
                raise TaxonomySynonymError(
                    f"Groupe de synonymes de {kind} sans aucun membre au référentiel : "
                    f"{members!r}. Le référentiel a changé — mettre à jour "
                    "`label_normalization` dans config/config.yaml."
                )
            if len(in_ref) > 1:
                raise TaxonomySynonymError(
                    f"Groupe de synonymes de {kind} ambigu : {members!r} contient "
                    f"plusieurs libellés du référentiel ({in_ref!r})."
                )
            canonical = in_ref[0]
            for m in members:
                if fold(m) != fold(canonical):
                    table[fold(m)] = canonical
        return table

    # ------------------------------------------------------------------ #
    #  Résolution
    # ------------------------------------------------------------------ #
    def _resolve(self, raw: object, ref_fold: Dict[str, str],
                 syn: Dict[str, str], code: str,
                 kind: str) -> Tuple[Optional[str], Optional[str]]:
        if is_blank(raw):
            return None, None
        key = fold(raw)
        hit = ref_fold.get(key)
        if hit is not None:
            if str(raw).strip() != hit:
                self.synonymes_appliques[f"{kind}: {str(raw).strip()!r} -> {hit!r}"] += 1
            return hit, None
        hit = syn.get(key)
        if hit is not None:
            self.synonymes_appliques[f"{kind}: {str(raw).strip()!r} -> {hit!r}"] += 1
            return hit, None
        self.libelles_inconnus[kind][str(raw).strip()] += 1
        return None, code

    def resolve_theme(self, raw: object) -> Tuple[Optional[str], Optional[str]]:
        """Retourne ``(libellé canonique, code d'anomalie)``."""
        return self._resolve(raw, self._niv1_fold, self._syn_niv1, THEME_INCONNU, "thème")

    def resolve_sous_theme(self, raw: object) -> Tuple[Optional[str], Optional[str]]:
        return self._resolve(raw, self._niv2_fold, self._syn_niv2,
                             SOUSTHEME_INCONNU, "sous-thème")

    def resolve_signal(self, raw: object) -> Tuple[Optional[str], Optional[str]]:
        """Fusionne les graphies de signaux (§8.3) — `Insatisfaction`/`Insatisfait`."""
        if is_blank(raw):
            return None, None
        key = fold(raw)
        hit = self._signaux.get(key)
        if hit is None:
            self.libelles_inconnus["signal"][str(raw).strip()] += 1
            return None, SIGNAL_INCONNU
        if str(raw).strip().lower() != hit:
            self.synonymes_appliques[f"signal: {str(raw).strip()!r} -> {hit!r}"] += 1
        return hit, None

    def resolve_sentiment(self, raw: object) -> Tuple[Optional[str], Optional[str]]:
        if is_blank(raw):
            return None, None
        return self._sentiments.get(fold(raw)), None

    # ------------------------------------------------------------------ #
    #  Périmètre des sous-thèmes (D-32)
    # ------------------------------------------------------------------ #
    def hors_perimetre(self, sous_theme: Optional[str]) -> bool:
        """True si le sous-thème est sous le seuil de 10 exemples (liste figée).

        La ligne reste exploitable pour l'entraînement du niveau 1 ; elle est
        exclue du niveau 2, routé en validation humaine.
        """
        return sous_theme is not None and fold(sous_theme) in self._hors_perimetre

    def couple_valide(self, niv1: Optional[str], niv2: Optional[str]) -> bool:
        """True si ``niv2`` est bien un enfant de ``niv1`` au référentiel."""
        if niv1 is None or niv2 is None:
            return True   # rien à contrôler : l'absence est traitée en amont
        return self.taxonomy.is_valid_pair(niv1, niv2)

    def libelles_hors_perimetre_inconnus(self) -> List[str]:
        """Entrées de `sous_themes_hors_perimetre` absentes du référentiel.

        Garde-fou de configuration : une faute de frappe dans cette liste
        laisserait silencieusement un sous-thème dans le périmètre du modèle.
        """
        return sorted(k for k in self._hors_perimetre if k not in self._niv2_fold)
