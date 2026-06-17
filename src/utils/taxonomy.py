"""Référentiel de thèmes (taxonomie) — SOURCE DE VÉRITÉ du modèle.

Le modèle ne peut prédire QUE des classes présentes dans
``taxonomy_cultura_poc.json``. Ce module charge ce référentiel et expose tous
les utilitaires d'encodage de labels et de contrainte hiérarchique :

  niv.1  : 20 grandes thématiques (classification multi-label)
  niv.2  : 67 sous-thématiques    (classification multi-classes, masquée par niv.1)

La hiérarchie est CONTRAINTE : un niv.2 n'appartient qu'à un seul niv.1 parent.
Au moment de l'inférence, on masque les logits niv.2 pour ne conserver que les
sous-thèmes enfants du niv.1 prédit — garantissant qu'aucune combinaison
hors-référentiel ne puisse être produite.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import numpy as np


class Taxonomy:
    """Encapsule le référentiel de thèmes et les contraintes hiérarchiques.

    L'ordre des classes est FIGÉ par l'ordre du fichier JSON ; il sert d'index
    de référence pour l'encodage des labels et doit rester stable entre
    l'entraînement et l'inférence. Les encodeurs sauvegardés (data/processed)
    encapsulent cet ordre afin de garantir la cohérence.
    """

    def __init__(self, themes: List[dict]):
        self.themes = themes

        # --- Listes ordonnées (l'ordre = ordre du fichier JSON) ---------------
        self.niv1_labels: List[str] = [t["niv1"] for t in themes]
        self.niv2_labels: List[str] = [n2 for t in themes for n2 in t["niv2"]]

        # --- Vérification d'intégrité du référentiel --------------------------
        if len(self.niv1_labels) != len(set(self.niv1_labels)):
            raise ValueError("Taxonomie invalide : niv.1 dupliqués.")
        # Les sous-thèmes (niv.2) doivent être globalement uniques : les données
        # historiques ne stockent que la chaîne niv.2, sans son parent. Une
        # collision rendrait l'encodage ambigu.
        if len(self.niv2_labels) != len(set(self.niv2_labels)):
            dups = sorted({x for x in self.niv2_labels if self.niv2_labels.count(x) > 1})
            raise ValueError(
                "Taxonomie invalide : sous-thèmes niv.2 dupliqués entre plusieurs "
                f"niv.1 ({dups}). L'encodage par chaîne deviendrait ambigu ; "
                "il faudrait passer à une clé composite (niv1, niv2)."
            )

        # --- Index <-> label --------------------------------------------------
        self.niv1_to_idx: Dict[str, int] = {l: i for i, l in enumerate(self.niv1_labels)}
        self.idx_to_niv1: Dict[int, str] = {i: l for l, i in self.niv1_to_idx.items()}
        self.niv2_to_idx: Dict[str, int] = {l: i for i, l in enumerate(self.niv2_labels)}
        self.idx_to_niv2: Dict[int, str] = {i: l for l, i in self.niv2_to_idx.items()}

        # --- Relations hiérarchiques -----------------------------------------
        self.children: Dict[str, List[str]] = {t["niv1"]: list(t["niv2"]) for t in themes}
        self.parent: Dict[str, str] = {
            n2: t["niv1"] for t in themes for n2 in t["niv2"]
        }

    # ------------------------------------------------------------------ #
    #  Constructeurs
    # ------------------------------------------------------------------ #
    @classmethod
    def from_json(cls, path: str | Path) -> "Taxonomy":
        """Charge la taxonomie depuis un fichier JSON ``{"themes": [...]}``."""
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Taxonomie introuvable : {path}")
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if "themes" not in data:
            raise ValueError("Le JSON de taxonomie doit contenir une clé 'themes'.")
        return cls(data["themes"])

    # ------------------------------------------------------------------ #
    #  Propriétés simples
    # ------------------------------------------------------------------ #
    @property
    def n_niv1(self) -> int:
        return len(self.niv1_labels)

    @property
    def n_niv2(self) -> int:
        return len(self.niv2_labels)

    # ------------------------------------------------------------------ #
    #  Validation
    # ------------------------------------------------------------------ #
    def is_valid_niv1(self, niv1: str) -> bool:
        return niv1 in self.niv1_to_idx

    def is_valid_niv2(self, niv2: str) -> bool:
        return niv2 in self.niv2_to_idx

    def is_valid_pair(self, niv1: str, niv2: str) -> bool:
        """True si ``niv2`` est bien un enfant de ``niv1`` dans le référentiel."""
        return self.parent.get(niv2) == niv1

    # ------------------------------------------------------------------ #
    #  Contrainte hiérarchique (masquage niv.2)
    # ------------------------------------------------------------------ #
    def niv2_indices_for_niv1(self, niv1: str) -> List[int]:
        """Indices (dans ``niv2_labels``) des sous-thèmes enfants de ``niv1``."""
        return [self.niv2_to_idx[n2] for n2 in self.children.get(niv1, [])]

    def hierarchy_mask(self) -> np.ndarray:
        """Matrice booléenne (n_niv1, n_niv2).

        ``mask[i, j] == True`` ssi le sous-thème ``j`` est enfant du thème ``i``.
        Sert à masquer les logits niv.2 lors de l'inférence conditionnée.
        """
        mask = np.zeros((self.n_niv1, self.n_niv2), dtype=bool)
        for niv1, idx1 in self.niv1_to_idx.items():
            for j in self.niv2_indices_for_niv1(niv1):
                mask[idx1, j] = True
        return mask

    def best_niv2_for_niv1(self, niv1: str, niv2_probs: np.ndarray) -> tuple[str, float]:
        """Sous-thème le plus probable parmi les enfants de ``niv1``.

        ``niv2_probs`` est un vecteur de probabilités de taille ``n_niv2``.
        Garantit un résultat TOUJOURS valide hiérarchiquement (masquage).
        """
        child_idx = self.niv2_indices_for_niv1(niv1)
        if not child_idx:
            raise ValueError(f"Thème niv.1 sans enfant dans la taxonomie : {niv1!r}")
        sub = np.asarray(niv2_probs)[child_idx]
        best_local = int(np.argmax(sub))
        best_global = child_idx[best_local]
        return self.idx_to_niv2[best_global], float(sub[best_local])
