#!/usr/bin/env python3
"""Recette automatisée — couche de décision de niveau 1 (trois leviers).

Contrôle les invariants de la couche de décision industrialisée le 11/09/2026 :

1. **Une seule implémentation.** Ce que ``build_output`` décide en production est
   exactement ce que ``PolitiqueDecision`` décide en évaluation. C'est la raison
   d'être du refactoring : depuis que les leviers déplacent le *thème 1*, une
   évaluation qui rejouerait une décision approchée mesurerait autre chose que
   le produit.
2. **Dégradation propre.** Sans bloc ``decision``, le comportement est
   *identique* à celui d'avant les leviers (seuil unique, repli, plafond).
3. **Jamais de levier muet.** Un libellé de règle absent du référentiel échoue au
   démarrage ; une source qui n'arrive pas jusqu'à la décision est comptabilisée.
4. **Contrat de sortie inchangé** — ``OUTPUT_COLUMNS`` n'a pas bougé (D-…, aucun
   arbitrage PO n'a autorisé de nouvelle colonne).

Ne charge aucun modèle : torch n'est pas requis.

Usage :
    python app/tests/recette_couche_decision.py

Code de sortie : 0 si aucun ÉCHEC, 1 sinon.
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import List, Tuple

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from src.evaluation.decision_niv1 import themes_decides  # noqa: E402
from src.inference.decision import (  # noqa: E402
    ConfigurationDecisionError,
    PolitiqueDecision,
    fold_libelle,
)
from src.inference.predictor import OUTPUT_COLUMNS, build_output  # noqa: E402
from src.utils import (  # noqa: E402
    config_du_profil,
    libelle_modele,
    modele_present,
    profil_par_racine,
    profils,
)
from src.utils.config import load_config, resolve_path  # noqa: E402
from src.utils.taxonomy import Taxonomy  # noqa: E402

_RESULTS: List[Tuple[str, str, str]] = []

#: Colonnes de sortie gelées au 11/09/2026. Toute modification exige un
#: arbitrage PO explicite : le front, les exports et les tableaux de bord de
#: Cultura sont calés dessus.
OUTPUT_COLUMNS_ATTENDUES = [
    "verbatim_analysé", "nb_themes",
    "theme1_niv1", "theme1_niv2", "theme1_sentiment", "theme1_score_confiance",
    "theme2_niv1", "theme2_niv2", "theme2_sentiment", "theme2_score_confiance",
    "signal_rupture_client", "signal_churn", "signal_insatisfaction_forte",
    "confidence_globale", "revue_humaine_requise",
]


def section(label: str) -> None:
    _RESULTS.append(("--", label, ""))


def check(cond: bool, label: str, detail: str = "") -> bool:
    _RESULTS.append(("OK" if cond else "ÉCHEC", label, detail))
    return bool(cond)


def main() -> int:
    cfg = load_config()
    taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg["cultura_sources"]["taxonomy"]))
    labels = list(taxonomy.niv1_labels)
    idx = {l: i for i, l in enumerate(labels)}
    politique = PolitiqueDecision.depuis_config(cfg, taxonomy)
    seuil_defaut = float(cfg["thresholds"]["classification_niv1"])
    cap = int(cfg["thresholds"]["max_themes"])

    def probs(**valeurs) -> np.ndarray:
        p = np.full(len(labels), 0.01)
        for nom, v in valeurs.items():
            p[idx[nom]] = v
        return p

    def noms(p, source=None, pol=None) -> List[str]:
        return [labels[i] for i in (pol or politique).themes(p, source)]

    # ---------------------------------------------------------------- #
    section("Configuration — les trois leviers sont chargés")
    # ---------------------------------------------------------------- #
    r = politique.resume()
    check(len(r["seuils_par_theme"]) == 4,
          "levier 1 : quatre seuils par thème sont surchargés",
          ", ".join(f"{k} {v}" for k, v in r["seuils_par_theme"].items()))
    check(len(r["regles_source"]) == 1,
          "levier 2 : une règle d'arbitrage par source est déclarée",
          str(r["regles_source"]))
    check(len(r["paires_confusables"]) >= 1,
          "levier 3 : au moins une paire confusable est déclarée",
          str(r["paires_confusables"]))
    check(seuil_defaut == 0.85,
          "le seuil de niveau 1 déclaré est le seuil opérationnel calé en L5'",
          f"classification_niv1 = {seuil_defaut}")

    # ---------------------------------------------------------------- #
    section("Levier 1 — seuils par thème")
    # ---------------------------------------------------------------- #
    # Le repli argmax garantit toujours un thème : pour isoler l'effet du seuil,
    # il faut un second thème qui, lui, franchit le sien — sans quoi on mesure
    # le repli et non le seuil.
    p_bug = probs(**{"Bug": 0.90, "Espace client": 0.88})   # seuils 0,95 et 0,85
    check(noms(p_bug) == ["Espace client"],
          "un thème sous SON seuil n'est pas activé, même s'il est le plus probable",
          f"Bug 0,90 < 0,95 et Espace client 0,88 ≥ 0,85 → {noms(p_bug)}")
    check(noms(probs(**{"Bug": 0.96, "Espace client": 0.88})) == ["Bug", "Espace client"],
          "le même thème au-dessus de son seuil est activé (0,96 ≥ 0,95)")
    check(noms(probs(**{"Bug": 0.90})) == ["Bug"],
          "sans aucun thème au-dessus de son seuil, le repli argmax s'applique",
          "un verbatim ne sort jamais sans thème")
    check(noms(probs(**{"Recherche produit": 0.65})) == ["Recherche produit"],
          "un seuil abaissé active sous le seuil commun (0,65 < 0,85 mais ≥ 0,60)")
    check(noms(probs(**{"Académie": 0.80})) == ["Académie"],
          "un thème sans surcharge et sous le seuil commun tombe au repli argmax",
          "le repli garantit toujours au moins un thème")
    check(noms(probs(**{"Académie": 0.80, "Espace client": 0.70})) == ["Académie"],
          "le repli argmax ne retient QU'UN thème, jamais deux")

    # ---------------------------------------------------------------- #
    section("Levier 2 — arbitrage contextuel par source")
    # ---------------------------------------------------------------- #
    # Les fixtures se déduisent de la marge CONFIGURÉE, jamais d'une valeur
    # recopiée : la marge est un réglage calibré (cf. calibrer_regle_source.py),
    # et une recette qui fige l'ancienne valeur échoue à la première
    # recalibration en faisant croire à une régression.
    marge = float(cfg["decision"]["regles_source"]["regles"][0]["avance_max"])
    p_serre = probs(**{"Général": 0.90, "Réception commande": 0.90 - marge / 2})
    p_franc = probs(**{"Général": 0.99, "Réception commande": 0.99 - marge * 2})
    check(noms(p_serre, "MDTC-postrecep") == ["Réception commande"],
          "sur la source visée, une avance faible bascule vers le thème cible",
          f"avance {marge / 2:.2f} < {marge:.2f}")
    check(noms(p_franc, "MDTC-postrecep") == ["Général"],
          "une avance franche n'est PAS basculée",
          f"avance {marge * 2:.2f} ≥ {marge:.2f}")
    check(noms(p_serre, None) == ["Général"],
          "sans source, la règle ne s'applique pas")
    check(noms(p_serre, "MDTC-postachat") == ["Général"],
          "sur une AUTRE source, la règle ne s'applique pas")
    check(noms(p_serre, "mdtc-POSTRECEP") == ["Réception commande"],
          "la source est comparée sous forme tolérante (casse, accents)")
    # La bascule peut créer un doublon : deux étiquettes pour un seul sujet.
    p_deux = probs(**{"Général": 0.90, "Réception commande": 0.90 - marge / 3})
    check(noms(p_deux, "MDTC-postrecep") == ["Réception commande"],
          "la bascule fusionne le doublon au lieu de produire deux fois le thème",
          f"sans source : {noms(p_deux)}")

    # ---------------------------------------------------------------- #
    section("Levier 3 — suppression des paires qui se recouvrent")
    # ---------------------------------------------------------------- #
    # Les fixtures se déduisent des paires CONFIGURÉES : la composition du
    # levier est un réglage (le PO a retiré une paire le 11/09), pas une
    # constante — une recette qui fige l'ancienne liste échoue au premier
    # arbitrage en faisant croire à une régression.
    a, b = r["paires_confusables"][0]
    check(noms(probs(**{a: 0.90, b: 0.88})) == [a],
          "d'une paire retenue ensemble, le membre le moins probable est retiré",
          f"{a} 0,90 + {b} 0,88")
    check(noms(probs(**{a: 0.90, b: 0.95})) == [b],
          "le membre conservé est bien le plus probable, quel que soit l'ordre",
          f"{a} 0,90 + {b} 0,95 -> {b}")

    # Un thème hors de toute paire déclarée ne doit jamais être supprimé.
    apparies = {fold_libelle(x) for paire in r["paires_confusables"] for x in paire}
    hors = next(l for l in labels
                if fold_libelle(l) not in apparies | {fold_libelle(a)}
                and l not in r["seuils_par_theme"])
    check(len(noms(probs(**{a: 0.90, hors: 0.95}))) == 2,
          "deux thèmes hors paire déclarée restent tous les deux",
          f"{a} + {hors}")

    # Le plafond précède la suppression : le créneau libéré n'est PAS repourvu.
    p3 = probs(**{a: 0.95, b: 0.93, hors: 0.90})
    check(noms(p3) == [a],
          "le créneau libéré par une suppression n'est pas repourvu par un 3e thème",
          f"retenu : {noms(p3)} — le plafond s'applique avant la suppression")

    # ---------------------------------------------------------------- #
    section("Garde-fous")
    # ---------------------------------------------------------------- #
    check(len(politique.themes(probs())) >= 1,
          "aucun verbatim ne sort sans thème, même à probabilités nulles")
    for _ in range(200):
        p = np.random.default_rng().uniform(0, 1, len(labels))
        if len(politique.themes(p, "MDTC-postrecep")) > cap:
            check(False, "le plafond `max_themes` est toujours respecté")
            break
    else:
        check(True, "le plafond `max_themes` est toujours respecté",
              f"200 tirages aléatoires, max_themes = {cap}")

    faux = deepcopy(cfg)
    faux["decision"] = {"paires_confusables":
                        {"actif": True, "paires": [["Bug", "Thème inexistant"]]}}
    try:
        PolitiqueDecision.depuis_config(faux, taxonomy)
        check(False, "un libellé absent du référentiel échoue AU DÉMARRAGE",
              "aucune exception levée — le levier serait silencieusement muet")
    except ConfigurationDecisionError:
        check(True, "un libellé absent du référentiel échoue AU DÉMARRAGE",
              "un levier muet serait pire que pas de levier")

    # Un AUTRE référentiel n'est pas une erreur : l'application V1 tourne sur les
    # 20 thèmes de l'ancien, où des seuils calés sur 11 n'ont aucun sens. Ce cas
    # a réellement cassé la recette V1 avant d'être traité — il est verrouillé ici.
    class _AutreReferentiel:
        niv1_labels = [f"Thème V1 n°{i}" for i in range(20)]

    autre = deepcopy(cfg)
    try:
        pol_autre = PolitiqueDecision.depuis_config(autre, _AutreReferentiel())
        check(not pol_autre.actif,
              "un référentiel différent DÉSACTIVE les leviers au lieu d'échouer",
              "20 thèmes au lieu des 11 attendus — cas de l'application V1")
    except ConfigurationDecisionError as exc:
        check(False, "un référentiel différent DÉSACTIVE les leviers au lieu d'échouer",
              f"exception levée : {exc}")

    check((cfg.get("decision") or {}).get("referentiel_attendu", {}).get("n_themes_niv1")
          == len(labels),
          "le référentiel attendu est déclaré et correspond au référentiel chargé",
          f"{len(labels)} thèmes de niveau 1")

    # ---------------------------------------------------------------- #
    section("Dégradation — sans bloc `decision`, comportement historique")
    # ---------------------------------------------------------------- #
    nu = deepcopy(cfg)
    nu["decision"] = {}
    pol_nue = PolitiqueDecision.depuis_config(nu, taxonomy)
    check(not pol_nue.actif, "la politique nue se déclare inactive")
    rng = np.random.default_rng(7)
    ecarts = 0
    for _ in range(500):
        p = rng.uniform(0, 1, len(labels))
        if pol_nue.themes(p, "MDTC-postrecep") != themes_decides(p, seuil_defaut, cap):
            ecarts += 1
    check(ecarts == 0,
          "sans leviers, la décision est identique à l'implémentation historique",
          f"500 tirages, {ecarts} écart(s) — source ignorée puisque aucune règle")

    # ---------------------------------------------------------------- #
    section("Équivalence production / évaluation — l'invariant du refactoring")
    # ---------------------------------------------------------------- #
    n_niv2 = len(taxonomy.niv2_labels)
    sentiments = cfg["sentiment"]["labels"]
    seuils_signaux = {"rupture": 1.0, "churn": 1.0, "insatisfaction": 1.0}
    rng = np.random.default_rng(11)
    desaccords = 0
    for _ in range(300):
        p1 = rng.uniform(0, 1, len(labels))
        p2 = rng.uniform(0, 1, n_niv2)
        ps = rng.dirichlet(np.ones(len(sentiments)))
        source = rng.choice(["MDTC-postrecep", "MDTC-postachat", None])
        attendu = [labels[i] for i in politique.themes(p1, source)]
        out = build_output("texte de contrôle", p1, p2, ps, {}, None,
                           taxonomy, cfg, seuils_signaux, sentiments,
                           source=source, politique=politique)
        obtenu = [out["theme1_niv1"]]
        if out["nb_themes"] == 2:
            obtenu.append(out["theme2_niv1"])
        if obtenu != attendu:
            desaccords += 1
    check(desaccords == 0,
          "`build_output` et `PolitiqueDecision` décident exactement pareil",
          f"300 verbatims simulés, sources mélangées, {desaccords} désaccord(s)")

    # La source doit vraiment traverser build_output, pas seulement la politique.
    out_sans = build_output("t", p_serre, np.full(n_niv2, 0.5),
                            np.array([0.1, 0.1, 0.8]), {}, None, taxonomy, cfg,
                            seuils_signaux, sentiments, source=None,
                            politique=politique)
    out_avec = build_output("t", p_serre, np.full(n_niv2, 0.5),
                            np.array([0.1, 0.1, 0.8]), {}, None, taxonomy, cfg,
                            seuils_signaux, sentiments, source="MDTC-postrecep",
                            politique=politique)
    check(out_sans["theme1_niv1"] == "Général"
          and out_avec["theme1_niv1"] == "Réception commande",
          "la source traverse bien `build_output` jusqu'à la décision",
          f"sans source → {out_sans['theme1_niv1']} · "
          f"avec source → {out_avec['theme1_niv1']}")
    check(taxonomy.is_valid_pair(out_avec["theme1_niv1"], out_avec["theme1_niv2"])
          or out_avec["theme1_niv2"] == "",
          "le couple (niv1, niv2) reste valide APRÈS bascule de la règle de source",
          f"{out_avec['theme1_niv1']} / {out_avec['theme1_niv2'] or '(vide)'}")

    # ---------------------------------------------------------------- #
    section("Moteurs multiples — le nouveau s'ajoute, il ne remplace pas")
    # ---------------------------------------------------------------- #
    profs = profils(cfg)
    presents = [p for p in profs if modele_present(cfg, p)]
    check(len(profs) >= 2,
          "au moins deux moteurs CamemBERT sont déclarés",
          ", ".join(p.get("id", "?") for p in profs))
    check(len(presents) == len(profs),
          "tous les moteurs déclarés ont leurs quatre sous-modèles sur disque",
          ", ".join(f"{p['id']}={modele_present(cfg, p)}" for p in profs))

    libelles = [libelle_modele(cfg, p) for p in presents]
    check(len(set(libelles)) == len(libelles),
          "chaque moteur a un libellé de registre distinct",
          " · ".join(libelles))

    # Chaque profil doit être RETROUVÉ depuis le chemin que le registre stocke,
    # sinon le prédicteur serait servi avec la configuration d'un autre moteur.
    egares = [p["id"] for p in presents
              if (profil_par_racine(cfg, str(resolve_path(cfg, p["racine"]))) or {})
              .get("id") != p["id"]]
    check(not egares,
          "chaque moteur est retrouvé depuis le chemin enregistré au registre",
          ", ".join(egares) or "aucun égaré")

    # Les deux moteurs ne doivent surtout PAS partager leurs réglages.
    confs = {p["id"]: config_du_profil(cfg, p) for p in presents}
    taxos = {i: Taxonomy.from_json(resolve_path(c, c["paths"]["taxonomy"]))
             for i, c in confs.items()}
    check(len({t.n_niv1 for t in taxos.values()}) == len(taxos),
          "chaque moteur charge SON référentiel",
          " · ".join(f"{i} : {t.n_niv1} thèmes" for i, t in taxos.items()))
    check(len({c["thresholds"]["classification_niv1"] for c in confs.values()})
          == len(confs),
          "chaque moteur applique SON seuil de niveau 1",
          " · ".join(f"{i} : {c['thresholds']['classification_niv1']}"
                     for i, c in confs.items()))
    check(len({c["cleaning"].get("lowercase") for c in confs.values()}) == len(confs),
          "chaque moteur applique le nettoyage de SA carte d'entraînement",
          " · ".join(f"{i} : lowercase={c['cleaning'].get('lowercase')}"
                     for i, c in confs.items()))

    politiques = {i: PolitiqueDecision.depuis_config(c, taxos[i])
                  for i, c in confs.items()}
    avec = [i for i, pol in politiques.items() if pol.actif]
    check(len(avec) == 1 and "cultura_2026" in avec,
          "seul le moteur pour lequel les leviers ont été calés les applique",
          " · ".join(f"{i} : leviers={pol.actif}" for i, pol in politiques.items()))

    # Les configurations doivent être des objets DISTINCTS : le prédicteur
    # mémoïse sa politique sur l'identité du dict de configuration.
    ids = [id(c) for c in confs.values()] + [id(cfg)]
    check(len(set(ids)) == len(ids),
          "les configurations de moteur sont des copies indépendantes",
          "sinon deux moteurs partageraient la même politique de décision")

    # Chaque modèle doit EMBARQUER son référentiel : c'est la seule forme qui
    # survive au conteneur, qui ne monte que le répertoire des modèles.
    sans_ref = [p["id"] for p in presents
                if not (Path(resolve_path(cfg, p["racine"])) / "taxonomy.json").is_file()]
    check(not sans_ref,
          "chaque modèle embarque son référentiel à sa racine (taxonomy.json)",
          ", ".join(sans_ref) or "tous")
    embarquees = {i: Path(c["paths"]["taxonomy"]).name for i, c in confs.items()}
    check(all(n == "taxonomy.json" for n in embarquees.values()),
          "c'est bien le référentiel embarqué qui est retenu, pas celui de `paths`",
          " · ".join(f"{i} : {n}" for i, n in embarquees.items()))

    # ---------------------------------------------------------------- #
    section("Portage en conteneur — les profils survivent à la réécriture")
    # ---------------------------------------------------------------- #
    # Les profils déclarent des chemins relatifs au projet ; le conteneur monte
    # les modèles ailleurs. Sans réécriture, AUCUN moteur n'est détecté et
    # l'application retombe silencieusement sur le stub.
    import os as _os

    if str(ROOT / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "app"))
    ancien = {k: _os.environ.get(k) for k in
              ("MODELS_DIR", "PROCESSED_DIR", "TAXONOMY_PATH", "CONFIG_PATH")}
    try:
        _os.environ.update({"MODELS_DIR": "/data/models",
                            "PROCESSED_DIR": "/data/processed",
                            "TAXONOMY_PATH": "/app/taxonomy.json"})
        _os.environ.pop("CONFIG_PATH", None)
        from worker.config_worker import build_worker_cfg

        conteneur = build_worker_cfg()
    except Exception as exc:  # noqa: BLE001
        conteneur = None
        check(False, "la configuration conteneur se construit", f"{type(exc).__name__}: {exc}")
    finally:
        for k, v in ancien.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v

    if conteneur is not None:
        racines = {p["id"]: p["racine"] for p in conteneur.get("moteurs_camembert", [])}
        hors = [i for i, r in racines.items() if not str(r).startswith("/data/models")]
        check(racines and not hors,
              "les racines de moteur sont réécrites vers le volume du conteneur",
              " · ".join(f"{i} : {r}" for i, r in racines.items()))
        check(len(set(racines.values())) == len(racines),
              "les moteurs restent distincts après réécriture",
              str(sorted(racines.values())))
        rapports = {p["id"]: p.get("eval_report")
                    for p in conteneur.get("moteurs_camembert", [])
                    if p.get("eval_report")}
        check(all(str(r).startswith("/data/processed") for r in rapports.values()),
              "les rapports d'évaluation pointent vers le volume du conteneur",
              " · ".join(f"{i} : {r}" for i, r in rapports.items()) or "aucun déclaré")

    # ---------------------------------------------------------------- #
    section("Contrat de sortie")
    # ---------------------------------------------------------------- #
    check(OUTPUT_COLUMNS == OUTPUT_COLUMNS_ATTENDUES,
          "OUTPUT_COLUMNS est inchangé — aucune colonne ajoutée par les leviers",
          f"{len(OUTPUT_COLUMNS)} colonnes")

    # ---------------------------------------------------------------- #
    section("Auditabilité")
    # ---------------------------------------------------------------- #
    audit = PolitiqueDecision.depuis_config(cfg, taxonomy)
    audit.themes(p_serre, "MDTC-postrecep")          # règle appliquée
    audit.themes(p_franc, "MDTC-postrecep")          # règle non déclenchée
    audit.themes(p_serre, None)                      # source absente
    audit.themes(p_serre, "Mopinion-mobile")         # source non couverte
    c = audit.compteurs
    check(c["regle_source_appliquee"] == 1 and c["source_absente"] == 1
          and c["source_non_reconnue"] == 1 and c["verbatims"] == 4,
          "les compteurs distinguent règle appliquée / source absente / source autre",
          str({k: v for k, v in c.items() if v}))

    return _bilan()


def _bilan() -> int:
    print("=" * 78)
    print("  RECETTE — couche de décision de niveau 1")
    print("=" * 78)
    fails = oks = 0
    for status, label, detail in _RESULTS:
        if status == "--":
            print(f"\n▸ {label}")
            continue
        icon = "✅" if status == "OK" else "❌"
        line = f"  {icon} {label}"
        if detail:
            line += f"  {'→  ' if status == 'ÉCHEC' else ''}({detail})" \
                if status != "ÉCHEC" else f"  →  {detail}"
        print(line)
        oks += status == "OK"
        fails += status == "ÉCHEC"
    print("\n" + "-" * 78)
    print(f"  Bilan : {oks} OK · {fails} ÉCHEC")
    print("-" * 78)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
