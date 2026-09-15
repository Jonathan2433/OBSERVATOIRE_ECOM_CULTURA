"""Profils de moteurs CamemBERT — plusieurs modèles coexistent dans le registre.

Pourquoi ce module existe
-------------------------
Jusqu'au 11/09/2026, l'application ne connaissait **qu'un seul** modèle
CamemBERT : celui déposé dans ``data/models``. Activer le modèle Cultura 2026
signifiait donc écraser le précédent.

Le PO a tranché autrement : le nouveau moteur s'**ajoute** à la sélection, il ne
remplace rien. Les deux doivent donc coexister — or ils ne partagent presque
rien :

===========================  ==========================  =========================
                             V1 (POC)                    Cultura 2026
===========================  ==========================  =========================
Référentiel                  20 thèmes / 67 sous-thèmes  11 / 59
Seuil d'activation niv.1     0,35                        0,85 (calé en L5')
Couche de décision           aucune                      trois leviers
Préfixe de satisfaction      échelle 1-5, inconditionnel échelle 1-4, conditionnel
Minuscules au nettoyage      oui                         non
Détecteurs de signaux        les trois                   `insatisfaction` seul
===========================  ==========================  =========================

Un seul réglage global ne peut pas décrire les deux. Ce module porte donc, pour
chaque moteur, l'**écart** à la configuration de référence, et fabrique à la
demande la configuration complète du moteur choisi.

Deux règles tiennent tout le reste :

* **C'est le modèle qui commande.** La politique de préfixe et le nettoyage sont
  lus dans la ``training_card.json`` du modèle, jamais imposés par la config —
  un modèle entraîné sans minuscules évalué sur un corpus en minuscules produit
  des chiffres faux, et le projet a déjà payé ce genre d'erreur.
* **Un profil mal déclaré échoue au chargement**, pas au millième verbatim.
"""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import resolve_path

logger = logging.getLogger(__name__)

#: Sous-dossiers de modèles portés par un profil.
SOUS_MODELES = ("classifier_niv1", "classifier_niv2", "sentiment", "signals")

#: Référentiel embarqué à la racine du modèle. Un modèle sans son espace de
#: labels n'est pas exploitable : le faire voyager avec lui évite qu'un déploiement
#: serve un modèle à 11 thèmes avec le référentiel à 20 de son prédécesseur — et
#: c'est ce qui fait fonctionner les conteneurs, qui ne montent que `data/models`.
TAXONOMY_EMBARQUEE = "taxonomy.json"


class ProfilMoteurError(ValueError):
    """Un profil de moteur est mal déclaré, ou son modèle est introuvable."""


def profils(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Profils déclarés en configuration (``moteurs_camembert``).

    Sans déclaration, on retombe sur le comportement historique : un unique
    moteur implicite, celui de ``paths``. C'est ce qui rend l'ajout rétro
    compatible — une configuration antérieure continue de fonctionner.
    """
    declares = cfg.get("moteurs_camembert") or []
    if declares:
        return [dict(p) for p in declares]
    return [{
        "id": "defaut",
        "libelle": "CamemBERT",
        "racine": cfg["paths"]["models"],
        "taxonomy": cfg["paths"]["taxonomy"],
        "eval_report": cfg["paths"].get("eval_report"),
    }]


def profil_par_id(cfg: Dict[str, Any], identifiant: str) -> Optional[Dict[str, Any]]:
    return next((p for p in profils(cfg) if p.get("id") == identifiant), None)


def profil_par_racine(cfg: Dict[str, Any], racine: object) -> Optional[Dict[str, Any]]:
    """Retrouve un profil depuis le chemin enregistré au registre.

    Le registre stocke un chemin **absolu** ; les profils déclarent un chemin
    relatif au projet. La comparaison passe donc par la résolution.
    """
    if not racine:
        return None
    cible = Path(str(racine)).resolve()
    for p in profils(cfg):
        if Path(resolve_path(cfg, p["racine"])).resolve() == cible:
            return p
    return None


def libelle_modele(cfg: Dict[str, Any], profil: Dict[str, Any]) -> str:
    """Libellé du registre : ``camembert-<id>-<horodatage niv.1>``.

    L'horodatage rend la version lisible et fait qu'un réentraînement crée une
    NOUVELLE entrée au registre au lieu d'en modifier une existante en silence.
    """
    from ..modeling.architecture import resolve_model_dir

    racine = Path(resolve_path(cfg, profil["racine"]))
    version = resolve_model_dir(racine / "classifier_niv1").name
    return f"camembert-{profil.get('id', 'defaut')}-{version}"


def modele_present(cfg: Dict[str, Any], profil: Dict[str, Any]) -> bool:
    """True si les quatre sous-modèles du profil existent et sont non vides."""
    racine = Path(resolve_path(cfg, profil["racine"]))
    for nom in SOUS_MODELES:
        d = racine / nom
        if not (d.is_dir() and any(d.iterdir())):
            return False
    return True


def taxonomie_du_profil(cfg: Dict[str, Any], profil: Dict[str, Any]) -> Optional[str]:
    """Chemin du référentiel du moteur.

    Priorité au référentiel **embarqué à la racine du modèle**
    (``<racine>/taxonomy.json``) : c'est le seul qui suive le modèle partout, y
    compris dans les conteneurs, qui ne montent que le répertoire des modèles.
    À défaut, le chemin déclaré au profil ; à défaut encore, celui de ``paths``.
    """
    racine = Path(resolve_path(cfg, profil["racine"]))
    embarquee = racine / TAXONOMY_EMBARQUEE
    if embarquee.is_file():
        return str(embarquee)
    declaree = profil.get("taxonomy")
    if declaree and Path(resolve_path(cfg, declaree)).is_file():
        return declaree
    if declaree:
        logger.warning(
            "Profil « %s » : référentiel déclaré introuvable (%s) et aucun "
            "`%s` à la racine du modèle. Le référentiel de `paths` sera "
            "utilisé — vérifier qu'il correspond bien à ce modèle.",
            profil.get("id"), declaree, TAXONOMY_EMBARQUEE)
    return None


def carte_entrainement(cfg: Dict[str, Any], profil: Dict[str, Any]) -> Dict[str, Any]:
    """``training_card.json`` du modèle de sentiment du profil (peut être vide).

    C'est elle qui porte la politique de préfixe et le nettoyage. Absente, on
    n'invente rien : la configuration de référence s'applique.
    """
    from ..modeling.architecture import resolve_model_dir

    chemin = (resolve_model_dir(Path(resolve_path(cfg, profil["racine"])) / "sentiment")
              / "training_card.json")
    if not chemin.is_file():
        return {}
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Carte d'entraînement illisible (%s) : %s", chemin, exc)
        return {}


def config_du_profil(cfg: Dict[str, Any], profil: Dict[str, Any]) -> Dict[str, Any]:
    """Configuration complète du moteur : copie de ``cfg`` avec ses écarts appliqués.

    La copie est **profonde** : le prédicteur mémoïse sa politique de décision
    sur l'identité du dict de configuration, et deux moteurs qui partageraient
    le même objet partageraient la même politique.
    """
    if not modele_present(cfg, profil):
        raise ProfilMoteurError(
            f"Profil de moteur « {profil.get('id')} » : modèle incomplet ou absent "
            f"sous {profil.get('racine')}. Les quatre sous-modèles "
            f"{SOUS_MODELES} sont requis.")

    conf = copy.deepcopy(cfg)
    racine = profil["racine"]
    for nom in SOUS_MODELES:
        conf["paths"][f"model_{nom}"] = f"{racine}/{nom}"
    conf["paths"]["models"] = racine
    taxonomie = taxonomie_du_profil(cfg, profil)
    if taxonomie:
        conf["paths"]["taxonomy"] = taxonomie
    if profil.get("eval_report"):
        conf["paths"]["eval_report"] = profil["eval_report"]
    if profil.get("seuil_niv1") is not None:
        conf["thresholds"]["classification_niv1"] = float(profil["seuil_niv1"])
    if profil.get("seuil_revue") is not None:
        conf["thresholds"]["revue_humaine"] = float(profil["seuil_revue"])

    # Les leviers de la couche de décision sont calés sur un référentiel donné.
    # Un profil qui ne les demande pas ne les subit pas — le garde-fou de
    # `referentiel_attendu` le ferait de toute façon, mais mieux vaut que la
    # configuration le dise que de compter sur un filet de sécurité.
    if not profil.get("leviers_decision", False):
        dec = conf.get("decision") or {}
        conf["decision"] = {k: v for k, v in dec.items()
                            if k in ("referentiel_attendu", "cibles")}

    _appliquer_carte(conf, carte_entrainement(cfg, profil), profil)
    return conf


def _appliquer_carte(conf: Dict[str, Any], carte: Dict[str, Any],
                     profil: Dict[str, Any]) -> None:
    """Impose au moteur la politique de préfixe et le nettoyage de SON modèle.

    C'est le modèle qui commande, jamais l'inverse : ces deux réglages décrivent
    ce que le modèle a **vu** à l'entraînement. Les lui contredire à l'inférence
    dégrade silencieusement ses sorties.
    """
    pol = carte.get("politique_prefixe") or {}
    if pol:
        conf["sentiment"]["use_satisfaction_prefix"] = bool(pol.get("actif", True))
        if pol.get("echelle_max") is not None:
            conf["sentiment"]["satisfaction_scale_max"] = pol["echelle_max"]
        conf["sentiment"]["prefixe_conditionnel"] = {
            "actif": bool(pol.get("conditionnel", False)),
            "max_mots": pol.get("max_mots") or 10,
        }
    if carte.get("lowercase") is not None:
        conf["cleaning"]["lowercase"] = bool(carte["lowercase"])
    logger.debug("Profil %s : préfixe=%s lowercase=%s",
                 profil.get("id"), pol or "config", conf["cleaning"].get("lowercase"))
