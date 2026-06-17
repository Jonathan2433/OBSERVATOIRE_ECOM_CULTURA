"""Chargement de la configuration, résolution des chemins et reproductibilité.

Toute la configuration vit dans ``config/config.yaml``. Ce module fournit :
  - ``load_config``      : charge le YAML en dict ;
  - ``get_project_root`` : racine du projet (indépendante du cwd) ;
  - ``resolve_path``     : transforme un chemin relatif de la config en absolu ;
  - ``set_seed``         : fixe TOUTES les graines (reproductibilité, SEED=42).
"""
from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def get_project_root() -> Path:
    """Racine du projet = dossier contenant ``config/`` et ``data/``.

    Calculée à partir de l'emplacement de ce fichier
    (``<root>/src/utils/config.py``) afin d'être indépendante du répertoire
    de travail courant.
    """
    return Path(__file__).resolve().parents[2]


def load_config(config_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """Charge ``config/config.yaml`` (ou un chemin explicite) en dictionnaire.

    Le dictionnaire renvoyé contient une clé technique ``_root`` pointant vers
    la racine du projet, utilisée par :func:`resolve_path`.
    """
    root = get_project_root()
    if config_path is None:
        config_path = root / "config" / "config.yaml"
    config_path = Path(config_path)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Fichier de configuration introuvable : {config_path}. "
            "Vérifiez que vous lancez les scripts depuis la racine du projet."
        )
    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg["_root"] = str(root)
    return cfg


def resolve_path(cfg: Dict[str, Any], relative_path: str) -> Path:
    """Transforme un chemin relatif (issu de la config) en chemin absolu.

    Tous les chemins de ``config.yaml`` sont relatifs à la racine du projet ;
    cette fonction garantit qu'ils fonctionnent quel que soit le cwd.
    """
    root = Path(cfg.get("_root", get_project_root()))
    p = Path(relative_path)
    return p if p.is_absolute() else (root / p)


def set_seed(seed: int = 42) -> None:
    """Fixe les graines aléatoires pour une reproductibilité totale.

    Couvre ``random``, ``numpy``, ``torch`` (CPU + CUDA) et la variable
    d'environnement ``PYTHONHASHSEED``. L'import de ``torch``/``numpy`` est
    protégé pour rester utilisable dans un environnement allégé (sans torch).
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:  # pragma: no cover - numpy quasi toujours présent
        pass
    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        # Déterminisme renforcé (léger surcoût, acceptable pour un POC).
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except ImportError:
        pass


def resolve_device(cfg: Dict[str, Any]) -> str:
    """Résout le device d'exécution ('cpu' / 'cuda') selon la config.

    Le POC vise le CPU ; ``device: auto`` choisit CUDA seulement si disponible.
    """
    requested = cfg.get("model", {}).get("device", "auto")
    if requested == "cpu":
        return "cpu"
    try:
        import torch

        if requested == "cuda":
            return "cuda" if torch.cuda.is_available() else "cpu"
        # auto
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"
