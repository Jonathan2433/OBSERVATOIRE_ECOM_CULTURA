"""Politique de décision du niveau 1 — implémentation canonique et unique.

Pourquoi ce module existe
-------------------------
La décision « quels thèmes retenir » était écrite **deux fois** : une fois dans
``build_output`` (production) et une fois dans ``src/evaluation/decision_niv1``
(évaluation), avec la consigne de les garder identiques à la main. Tant que la
règle tenait en trois lignes — seuil, repli sur l'argmax, plafond — le risque
était théorique. Il ne l'est plus : les trois leviers validés par le PO le
11/09/2026 déplacent le **thème 1** lui-même, et une évaluation qui rejouerait
une décision approchée mesurerait un produit qui n'existe pas.

Chiffres et calibration : ``docs/COUCHE_DECISION.md``.

Ce module porte donc la décision **une seule fois**. ``build_output`` l'appelle,
l'évaluation l'appelle, la recette l'appelle. Il ne dépend ni de torch, ni de
pandas, ni de sklearn : uniquement de numpy et du référentiel.

Les trois leviers
-----------------
Aucun n'ajoute d'information au modèle : ils **arbitrent à sa place** là où les
mesures montrent qu'il ne peut pas trancher. Ils s'appliquent dans cet ordre,
qui n'est pas l'ordre chronologique de leur découverte mais le seul cohérent :

1. **Seuils par thème** — un seuil unique traite de la même façon un thème à
   40 % du corpus et un thème à 0,4 %.
2. **Plafond** ``max_themes`` — inchangé.
3. **Arbitrage contextuel par source** — 38,6 % des erreurs de thème sont un
   seul motif (`Réception commande` prédit `Général`), dont 93 cas sur 102
   viennent du formulaire post-réception. Le texte seul ne permet pas de
   trancher ; la source, si. *En pratique le plus petit des trois : les seuils
   par thème arbitrent déjà en grande partie entre ces deux thèmes, et la marge
   a dû être recalibrée en conséquence.*
4. **Suppression des paires qui se recouvrent** — deux paires de thèmes sont
   proposées ensemble sur des verbatims **mono**-thème. Ce n'est pas un second
   sujet, c'est une hésitation entre deux étiquettes pour le même sujet.
   *Le plus rentable des trois.*

Le plafond précède la suppression **délibérément** : quand une paire est
supprimée, le créneau libéré n'est PAS rempli par un troisième thème. Supprimer
la paire signifie « ces deux étiquettes désignent un seul sujet », pas « il
reste une place à pourvoir ».

Dégradation
-----------
Une configuration sans bloc ``decision`` reproduit **exactement** le
comportement antérieur (seuil unique, repli, plafond).

Deux situations très différentes se ressemblent, et il faut les séparer :

* **Le référentiel n'est pas celui pour lequel les leviers ont été calés.**
  C'est le cas de l'application V1, qui tourne sur les 20 thèmes de l'ancien
  référentiel : des seuils calés sur les 11 thèmes de Cultura 2026 n'y ont
  aucun sens. Les leviers sont alors **désactivés**, avec un avertissement — ce
  n'est pas une erreur, c'est un modèle différent.
* **Le référentiel est le bon, mais un libellé manque.** Faute de frappe, ou
  Cultura a renommé un thème. C'est une **erreur levée au démarrage** : une
  règle qui ne s'applique pas sans que personne ne le sache est pire que pas de
  règle du tout.

Le discriminant est déclaré en configuration (``decision.referentiel_attendu``)
et non deviné : deux référentiels peuvent partager un libellé — les nôtres en
partagent exactement un (D-36) — et une heuristique s'y tromperait.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class ConfigurationDecisionError(ValueError):
    """Un levier de décision référence un libellé absent du référentiel.

    Levée au démarrage. Le référentiel appartient à Cultura (D-7) : s'il change,
    une règle calée sur l'ancien doit se voir immédiatement, pas se taire.
    """


def fold_libelle(label: object) -> str:
    """Forme tolérante d'un libellé : casse, accents, espaces, apostrophes.

    Mêmes conventions que ``preprocessing.label_norm.fold`` — les traits d'union
    sont **préservés**.
    """
    s = str(label).replace("’", "'")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


# --------------------------------------------------------------------------- #
#  Levier 3 — arbitrage contextuel par source
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RegleSource:
    """Bascule un thème vers un autre sur une source donnée.

    ``avance_max`` porte sur l'**avance** du thème d'origine, c'est-à-dire
    ``p(theme_source) - p(theme_cible)``. En dessous de cette avance, la
    prédiction est jugée trop peu tranchée pour l'emporter sur le contexte du
    formulaire, et le thème cible est retenu.
    """

    source: str            # forme tolérante, utilisée pour la comparaison
    source_libelle: str    # graphie d'origine, restituée dans les rapports
    idx_source: int
    idx_cible: int
    avance_max: float
    motif: str = ""

    def declenche(self, probs: np.ndarray) -> bool:
        return float(probs[self.idx_source]) - float(probs[self.idx_cible]) < self.avance_max


# --------------------------------------------------------------------------- #
#  Politique complète
# --------------------------------------------------------------------------- #
@dataclass
class PolitiqueDecision:
    """Décision de niveau 1, seuils et règles résolus en indices une fois pour toutes."""

    seuils: np.ndarray                       # (n_themes,) — seuil d'activation par thème
    max_themes: int
    seuil_defaut: float
    regles_source: Tuple[RegleSource, ...] = ()
    paires_confusables: Tuple[Tuple[int, int], ...] = ()
    libelles: Tuple[str, ...] = ()
    #: Compteurs d'application — alimentent le rapport, jamais la décision.
    compteurs: Dict[str, int] = field(default_factory=dict)
    #: Le constat de couverture n'est utile qu'une fois par exécution.
    _couverture_dite: bool = False

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def depuis_config(cls, cfg: Dict[str, Any], taxonomy: Any) -> "PolitiqueDecision":
        thr = cfg.get("thresholds", {}) or {}
        seuil_defaut = float(thr.get("classification_niv1", 0.5))
        max_themes = int(thr.get("max_themes", 2))

        libelles = tuple(taxonomy.niv1_labels)
        index = {fold_libelle(l): i for i, l in enumerate(libelles)}
        dec = (cfg.get("decision") or {})

        # Référentiel attendu : si le référentiel chargé n'est pas celui sur
        # lequel les leviers ont été calés, ils ne veulent rien dire. On les
        # désactive en le disant, plutôt que d'échouer (l'application V1 tourne
        # légitimement sur l'ancien référentiel) ou de les appliquer au hasard.
        attendu = dec.get("referentiel_attendu") or {}
        n_attendu = attendu.get("n_themes_niv1")
        # Ne prévenir que s'il y avait réellement des leviers à désactiver : un
        # profil qui n'en demande aucun n'a pas à recevoir un avertissement.
        leviers_demandes = any(k in dec for k in
                               ("seuils_par_theme", "regles_source", "paires_confusables"))
        if leviers_demandes and n_attendu is not None and int(n_attendu) != len(libelles):
            logger.warning(
                "Couche de décision DÉSACTIVÉE : les leviers sont calés sur le "
                "référentiel « %s » (%s thèmes de niveau 1) et le référentiel "
                "chargé en compte %d. Ce n'est pas une erreur si vous exécutez "
                "un autre modèle ; c'en est une si vous attendiez les leviers.",
                attendu.get("nom", "?"), n_attendu, len(libelles))
            dec = {}

        def resoudre(libelle: object, levier: str) -> int:
            cle = fold_libelle(libelle)
            if cle not in index:
                raise ConfigurationDecisionError(
                    f"Levier « {levier} » : le thème {libelle!r} est absent du "
                    f"référentiel de niveau 1 ({len(libelles)} thèmes). Le "
                    "référentiel a changé — mettre à jour le bloc `decision` de "
                    "config/config.yaml, ou désactiver le levier."
                )
            return index[cle]

        # --- Levier 1 : seuils par thème -----------------------------------
        seuils = np.full(len(libelles), seuil_defaut, dtype=float)
        bloc = dec.get("seuils_par_theme") or {}
        if bloc.get("actif"):
            for libelle, valeur in (bloc.get("valeurs") or {}).items():
                seuils[resoudre(libelle, "seuils_par_theme")] = float(valeur)

        # --- Levier 3 : arbitrage par source --------------------------------
        regles: List[RegleSource] = []
        bloc = dec.get("regles_source") or {}
        if bloc.get("actif"):
            for r in (bloc.get("regles") or []):
                regles.append(RegleSource(
                    source=fold_libelle(r["source"]),
                    source_libelle=str(r["source"]),
                    idx_source=resoudre(r["theme_source"], "regles_source"),
                    idx_cible=resoudre(r["theme_cible"], "regles_source"),
                    avance_max=float(r["avance_max"]),
                    motif=str(r.get("motif", "")),
                ))

        # --- Levier 4 : paires confusables ----------------------------------
        paires: List[Tuple[int, int]] = []
        bloc = dec.get("paires_confusables") or {}
        if bloc.get("actif"):
            for paire in (bloc.get("paires") or []):
                if len(paire) != 2:
                    raise ConfigurationDecisionError(
                        f"Levier « paires_confusables » : {paire!r} n'est pas une paire.")
                a, b = (resoudre(x, "paires_confusables") for x in paire)
                if a == b:
                    raise ConfigurationDecisionError(
                        f"Levier « paires_confusables » : {paire!r} désigne deux fois "
                        "le même thème.")
                paires.append((a, b))

        return cls(
            seuils=seuils, max_themes=max_themes, seuil_defaut=seuil_defaut,
            regles_source=tuple(regles), paires_confusables=tuple(paires),
            libelles=libelles,
            compteurs={"verbatims": 0, "regle_source_appliquee": 0,
                       "paire_supprimee": 0, "source_absente": 0,
                       "source_non_reconnue": 0},
        )

    # ------------------------------------------------------------------ #
    #  Décision
    # ------------------------------------------------------------------ #
    @property
    def actif(self) -> bool:
        """True dès qu'un levier modifie le comportement historique."""
        return bool(self.regles_source or self.paires_confusables
                    or not np.allclose(self.seuils, self.seuil_defaut))

    def themes(self, niv1_probs: Sequence[float],
               source: Optional[str] = None) -> List[int]:
        """Indices des thèmes retenus pour UN verbatim, par probabilité décroissante.

        C'est la décision du produit — celle que l'évaluation doit rejouer.
        """
        probs = np.asarray(niv1_probs, dtype=float)
        self.compteurs["verbatims"] = self.compteurs.get("verbatims", 0) + 1

        # 1. Activation, seuil propre à chaque thème, repli sur l'argmax.
        ordre = np.argsort(-probs)
        retenus = [int(i) for i in ordre if probs[i] >= self.seuils[i]]
        if not retenus:
            retenus = [int(ordre[0])]

        # 2. Plafond.
        retenus = retenus[: self.max_themes]

        # 3. Arbitrage contextuel par source.
        if self.regles_source:
            retenus = self._appliquer_source(retenus, probs, source)

        # 4. Suppression des paires qui se recouvrent.
        if self.paires_confusables and len(retenus) >= 2:
            retenus = self._supprimer_paires(retenus, probs)

        return retenus

    # ------------------------------------------------------------------ #
    @staticmethod
    def _source_absente(source: object) -> bool:
        """Mêmes conventions de vide que ``label_norm.is_blank``.

        Un ``NaN`` de pandas devient la chaîne « nan » en le convertissant
        naïvement : sans ce filtre, une colonne source vide serait comptée comme
        une source inconnue, et le journal de couverture mentirait.
        """
        if source is None:
            return True
        if isinstance(source, float) and source != source:      # NaN
            return True
        return str(source).strip().lower() in ("", "nan", "none", "null")

    def _appliquer_source(self, retenus: List[int], probs: np.ndarray,
                          source: Optional[str]) -> List[int]:
        if self._source_absente(source):
            self.compteurs["source_absente"] += 1
            return retenus
        cle = fold_libelle(source)
        regles = [r for r in self.regles_source if r.source == cle]
        if not regles:
            self.compteurs["source_non_reconnue"] += 1
            return retenus

        modifie = False
        sortie: List[int] = []
        for idx in retenus:
            remplacant = idx
            for regle in regles:
                if idx == regle.idx_source and regle.declenche(probs):
                    remplacant = regle.idx_cible
                    modifie = True
                    break
            if remplacant not in sortie:      # la bascule peut créer un doublon
                sortie.append(remplacant)
        if modifie:
            self.compteurs["regle_source_appliquee"] += 1
        return sortie

    # ------------------------------------------------------------------ #
    def _supprimer_paires(self, retenus: List[int], probs: np.ndarray) -> List[int]:
        """Retire le membre le moins probable d'une paire qui se recouvre.

        Ne s'applique qu'entre thèmes effectivement retenus ensemble : la paire
        décrit une hésitation d'étiquetage, pas une exclusion mutuelle absolue.
        """
        presents = set(retenus)
        a_retirer = set()
        for a, b in self.paires_confusables:
            if a in presents and b in presents:
                a_retirer.add(a if probs[a] < probs[b] else b)
        if not a_retirer:
            return retenus
        sortie = [i for i in retenus if i not in a_retirer]
        self.compteurs["paire_supprimee"] += 1
        return sortie or retenus[:1]          # jamais zéro thème

    # ------------------------------------------------------------------ #
    #  Restitution
    # ------------------------------------------------------------------ #
    def resume(self) -> Dict[str, Any]:
        """Description de la politique, destinée aux rapports d'évaluation.

        Un chiffre sans son protocole n'est pas un chiffre : tout rapport
        produit sous cette politique doit pouvoir dire laquelle était active.
        """
        surcharges = {
            self.libelles[i]: round(float(s), 4)
            for i, s in enumerate(self.seuils) if not np.isclose(s, self.seuil_defaut)
        }
        return {
            "seuil_niv1_defaut": round(self.seuil_defaut, 4),
            "max_themes": self.max_themes,
            "seuils_par_theme": surcharges,
            "regles_source": [
                {"source": r.source_libelle,
                 "theme_source": self.libelles[r.idx_source],
                 "theme_cible": self.libelles[r.idx_cible],
                 "avance_max": r.avance_max}
                for r in self.regles_source
            ],
            "paires_confusables": [
                [self.libelles[a], self.libelles[b]] for a, b in self.paires_confusables
            ],
            "compteurs": dict(self.compteurs),
        }

    def journaliser_couverture(self) -> None:
        """Alerte si une règle de source configurée n'a jamais pu s'appliquer.

        Une règle qui ne se déclenche jamais parce que la source n'arrive pas
        jusqu'à la décision est un défaut silencieux — exactement le genre que
        le projet s'interdit.
        """
        if not self.regles_source or self._couverture_dite:
            return
        vus = self.compteurs.get("verbatims", 0)
        if not vus:
            return
        self._couverture_dite = True
        absentes = self.compteurs.get("source_absente", 0)
        if absentes == vus:
            logger.warning(
                "Les %d règles de source configurées n'ont JAMAIS pu s'appliquer : "
                "aucun des %d verbatims n'a été présenté avec sa source. La chaîne "
                "d'appel ne transmet pas `source` jusqu'à la décision.",
                len(self.regles_source), vus)
        elif absentes:
            logger.info("Source absente sur %d verbatims sur %d.", absentes, vus)


# --------------------------------------------------------------------------- #
#  Décision par lots — utilisée par l'évaluation
# --------------------------------------------------------------------------- #
def matrice_decidee(niv1_probs: np.ndarray,
                    politique: PolitiqueDecision,
                    sources: Optional[Sequence[Optional[str]]] = None) -> np.ndarray:
    """Matrice binaire (n, n_themes) de la décision réelle, leviers compris."""
    probs = np.asarray(niv1_probs, dtype=float)
    if sources is None:
        sources = [None] * probs.shape[0]
    y = np.zeros_like(probs, dtype=int)
    for ligne in range(probs.shape[0]):
        for idx in politique.themes(probs[ligne], sources[ligne]):
            y[ligne, idx] = 1
    return y


def themes_par_verbatim(niv1_probs: np.ndarray,
                        politique: PolitiqueDecision,
                        sources: Optional[Sequence[Optional[str]]] = None) -> List[List[int]]:
    """Liste ordonnée des thèmes retenus, verbatim par verbatim."""
    probs = np.asarray(niv1_probs, dtype=float)
    if sources is None:
        sources = [None] * probs.shape[0]
    return [politique.themes(probs[i], sources[i]) for i in range(probs.shape[0])]
