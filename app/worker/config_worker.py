"""Construction de la configuration du moteur ML côté worker.

Charge la config.yaml du POC (seuils, nettoyage, anonymisation, sentiment,
signaux) puis réécrit les CHEMINS en absolu vers les volumes du conteneur
(/data/...), au lieu des chemins relatifs du POC.

⚠️ Les **profils de moteurs** (`moteurs_camembert`) et le référentiel déclaré
par LM Studio doivent être réécrits eux aussi. Ils utilisent des chemins relatifs
à la racine du projet
(`data/models/cultura_2026`) qui, dans le conteneur, se résoudraient en
`/app/data/models/...` — un répertoire qui n'existe pas, puisque les modèles
sont montés sur `/data/models`. Sans cette réécriture, AUCUN moteur CamemBERT
n'est détecté et l'application retombe silencieusement sur le stub.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from src.utils import load_config


def build_worker_cfg() -> Dict[str, Any]:
    cfg = load_config(os.environ.get("CONFIG_PATH") or None)
    models = os.environ.get("MODELS_DIR", "/data/models")
    processed = os.environ.get("PROCESSED_DIR", "/data/processed")

    cfg["paths"]["models"] = models
    cfg["paths"]["model_classifier_niv1"] = f"{models}/classifier_niv1"
    cfg["paths"]["model_classifier_niv2"] = f"{models}/classifier_niv2"
    cfg["paths"]["model_sentiment"] = f"{models}/sentiment"
    cfg["paths"]["model_signals"] = f"{models}/signals"
    cfg["paths"]["taxonomy"] = os.environ.get("TAXONOMY_PATH", "/app/taxonomy.json")
    cfg["paths"]["eval_report"] = f"{processed}/eval_report.json"
    cfg["model"]["local_model_dir"] = os.environ.get("CAMEMBERT_DIR", f"{models}/camembert-base")

    _reecrire_profils(cfg, models, processed)

    # --- LM Studio : surcharge env + chemin du référentiel Cultura 2026 monté --
    lms = cfg.setdefault("lmstudio", {})
    enabled_env = os.environ.get("LMSTUDIO_ENABLED")
    if enabled_env is not None:
        lms["enabled"] = enabled_env.strip().lower() in ("1", "true", "yes", "on")
    lms["base_url"] = os.environ.get("LMSTUDIO_BASE_URL", lms.get("base_url", "http://host.docker.internal:1234/v1"))
    lms["model"] = os.environ.get("LMSTUDIO_MODEL", lms.get("model", "local-model"))
    taxonomy = str(lms.get("taxonomy") or "")
    if taxonomy == "data/models":
        lms["taxonomy"] = models
    elif taxonomy.startswith("data/models/"):
        lms["taxonomy"] = f"{models}/{taxonomy[len('data/models/'):]}"
    mp = os.environ.get("LMSTUDIO_MAX_PARALLEL")
    if mp:
        try:
            lms["max_parallel"] = max(1, int(mp))
        except ValueError:
            pass

    # --- Moteur Claude (V5) : surcharge env du bloc claude de config.yaml ----------
    # Comparaison/test uniquement. La CLÉ n'entre JAMAIS dans la config : on n'expose
    # que le booléen ``api_key_present`` (dérivé de l'env) pour la détection.
    cl = cfg.setdefault("claude", {})
    claude_enabled_env = os.environ.get("CLAUDE_ENABLED")
    if claude_enabled_env is not None:
        cl["enabled"] = claude_enabled_env.strip().lower() in ("1", "true", "yes", "on")
    cl["model"] = os.environ.get("CLAUDE_MODEL", cl.get("model", "claude-opus-4-8"))
    cl["base_url"] = os.environ.get("CLAUDE_BASE_URL", cl.get("base_url", "https://api.anthropic.com"))
    cl["api_key_present"] = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return cfg


def _reecrire_profils(cfg: Dict[str, Any], models: str, processed: str) -> None:
    """Réécrit les chemins des profils de moteurs vers les volumes du conteneur.

    Les profils déclarent leur racine **relativement au répertoire des
    modèles** du projet (``data/models``, ``data/models/cultura_2026``). Dans le
    conteneur ce répertoire est monté ailleurs : seule la partie qui suit
    ``data/models`` est conservée, et recollée sous ``MODELS_DIR``.

    Le référentiel n'est pas réécrit : chaque modèle embarque le sien à sa
    racine (``taxonomy.json``), qui suit donc le déplacement. Un profil dont le
    modèle n'embarque pas son référentiel retombera sur ``paths.taxonomy`` — et
    `moteurs.taxonomie_du_profil` l'aura signalé au journal.
    """
    profils = cfg.get("moteurs_camembert") or []
    racine_projet = "data/models"
    for profil in profils:
        declaree = str(profil.get("racine", "")).strip("/")
        if declaree == racine_projet:
            profil["racine"] = models
        elif declaree.startswith(racine_projet + "/"):
            profil["racine"] = f"{models}/{declaree[len(racine_projet) + 1:]}"
        # Un profil hors de `data/models` est laissé tel quel : il désigne un
        # emplacement que l'opérateur a choisi, et que nous n'avons pas à deviner.

        rapport = profil.get("eval_report")
        if rapport and str(rapport).startswith("data/processed/"):
            profil["eval_report"] = f"{processed}/{str(rapport)[len('data/processed/'):]}"
