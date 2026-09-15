#!/usr/bin/env python3
"""Évaluation du modèle réentraîné sur le jeu de test gelé — lots L6 et L9.

Réutilise **les mêmes fonctions de mesure** que `scripts/mesurer_baseline.py`,
sur **le même jeu de test**, pour que les deux chiffres soient directement
comparables. C'est la matière de la comparaison ancien/nouveau de L9.

Différence de périmètre avec la baseline : le nouveau modèle partage l'espace de
labels des annotations, donc les métriques **thématiques** (famille A) sont ici
calculables — elles ne l'étaient pas pour l'ancien (D-36).

La politique de préfixe est lue dans ``training_card.json`` et **imposée** à la
configuration : c'est le modèle qui commande, jamais l'inverse.

Usage :
    python scripts/evaluer_cultura.py [--split test]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for chemin in (str(ROOT), str(ROOT / "scripts")):
    if chemin not in sys.path:
        sys.path.insert(0, chemin)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from mesurer_baseline import metriques_sentiment, tranche_de  # noqa: E402
from src.evaluation.decision_niv1 import (  # noqa: E402
    courbe_seuil,
    distribution_nb_themes,
    matrice_depuis_decisions,
    mesures_second_theme,
    seuils_par_defaut,
)
from src.inference.decision import PolitiqueDecision, themes_par_verbatim  # noqa: E402
from src.utils.config import load_config, resolve_path  # noqa: E402
from src.utils.features import verifier_politique_prefixe  # noqa: E402
from src.utils.taxonomy import Taxonomy  # noqa: E402


def _configurer_nouveau_modele(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Bascule la configuration sur les artefacts du modèle réentraîné."""
    for cle in ("model_classifier_niv1", "model_classifier_niv2",
                "model_sentiment", "model_signals"):
        cfg["paths"][cle] = cfg["paths"][cle].replace(
            "data/models/", "data/models/cultura_2026/")
    cfg["paths"]["taxonomy"] = cfg["cultura_sources"]["taxonomy"]

    # La politique de préfixe est celle du modèle, lue dans sa carte.
    from src.modeling.architecture import resolve_model_dir

    carte_path = (resolve_model_dir(resolve_path(cfg, cfg["paths"]["model_sentiment"]))
                  / "training_card.json")
    carte = json.loads(carte_path.read_text(encoding="utf-8"))
    pol = carte.get("politique_prefixe") or {}
    if pol:
        cfg["sentiment"]["use_satisfaction_prefix"] = pol["actif"]
        cfg["sentiment"]["satisfaction_scale_max"] = pol["echelle_max"]
        cfg["sentiment"]["prefixe_conditionnel"] = {
            "actif": pol["conditionnel"], "max_mots": pol.get("max_mots") or 10}
    if carte.get("lowercase") is not None:
        cfg["cleaning"]["lowercase"] = bool(carte["lowercase"])
    verifier_politique_prefixe(cfg, carte)
    return carte


#: Clés de `decision` qui ne sont PAS des leviers : elles décrivent le contexte
#: (référentiel attendu) et les critères d'acceptation. Les désactiver avec les
#: leviers ferait silencieusement retomber le rapport sur des cibles par défaut.
_NON_LEVIERS = ("referentiel_attendu", "cibles")


def _sans_leviers(dec: Dict[str, Any]) -> Dict[str, Any]:
    """Bloc `decision` privé de ses leviers, contexte et cibles conservés."""
    return {k: v for k, v in dec.items() if k in _NON_LEVIERS}


def _courbe_taux_de_revue(cfg: Dict[str, Any], confiances) -> Dict[str, Any]:
    """Taux de revue humaine en fonction du seuil, sur une grille FINE.

    Pourquoi une grille fine
    ------------------------
    Le critère de monotonie — aucun bond de plus de 20 points d'un pas au
    suivant — était mesuré au pas de 0,05, et affichait +39,4 points entre 0,70
    et 0,75. À pas grossier, **tout escalier ressemble à une falaise** : on ne
    peut pas distinguer une vraie discontinuité d'un empilement de petites
    marches. Le pas de 0,01 tranche.

    L'enjeu n'est pas cosmétique : si un centième de seuil fait doubler le volume
    à relire, le réglage n'est pas pilotable — impossible de viser une charge de
    10 à 15 % (D-9) sans tomber à côté.

    La confiance globale est une moyenne de trois probabilités : elle prend un
    nombre fini de valeurs, et des paliers sont attendus. Ce qui compte est leur
    HAUTEUR, pas leur existence.

    Sur quelle plage
    ----------------
    Le critère est évalué sur la **plage d'exploitation** — les seuils qui
    atteignent la charge visée (D-9), élargis d'une marge déclarée — et non sur
    toute la grille. Un saut à 0,92, où l'on relirait 9 verbatims sur 10, ne
    décrit aucun réglage que quelqu'un choisira. Le saut sur la grille entière
    reste publié, pour que l'écart entre les deux se voie.
    """
    cibles = ((cfg.get("decision") or {}).get("cibles") or {})
    g = cibles.get("taux_revue_grille") or {"debut": 0.30, "fin": 0.95, "pas": 0.01}
    saut_max = float(cibles.get("taux_revue_saut_max", 0.20))
    bas, haut = (cibles.get("taux_revue_cible") or [0.10, 0.15])[:2]

    debut, fin, pas = float(g["debut"]), float(g["fin"]), float(g["pas"])
    seuils = [round(debut + i * pas, 4)
              for i in range(int(round((fin - debut) / pas)) + 1)]
    taux = [round(float((confiances < s).mean()), 4) for s in seuils]

    sauts = [{"de": seuils[i - 1], "a": seuils[i],
              "saut": round(taux[i] - taux[i - 1], 4)}
             for i in range(1, len(seuils))]
    pire = max(sauts, key=lambda x: x["saut"]) if sauts else None

    # Même mesure sur la grille grossière d'origine, pour que l'écart se voie.
    grossiers = [round(debut + i * 0.05, 4)
                 for i in range(int(round((fin - debut) / 0.05)) + 1)]
    t_gros = [float((confiances < s).mean()) for s in grossiers]
    pire_gros = max((t_gros[i] - t_gros[i - 1] for i in range(1, len(t_gros))),
                    default=0.0)

    dans_cible = [s for s, t in zip(seuils, taux) if bas <= t <= haut]

    # Plage d'exploitation : elle se DÉDUIT de la charge visée, elle n'est pas
    # choisie a priori — sans quoi on ajusterait la plage jusqu'à ce que le
    # critère passe, ce qui ne vaudrait rien.
    marge = float(cibles.get("taux_revue_marge_plage", 0.05))
    if dans_cible:
        plage = (min(dans_cible) - marge, max(dans_cible) + marge)
        dedans = [x for x in sauts if plage[0] <= x["de"] and x["a"] <= plage[1]]
    else:
        plage, dedans = (debut, fin), sauts
    pire_plage = max(dedans, key=lambda x: x["saut"]) if dedans else None

    return {
        "moyenne": round(float(confiances.mean()), 4),
        # Grille d'origine, conservée : les rapports antérieurs s'y réfèrent.
        "taux_de_revue_par_seuil": {
            f"{s:.2f}": round(float((confiances < s).mean()), 4)
            for s in (0.50, 0.60, 0.65, 0.70, 0.75, 0.80)},
        "grille_fine": {
            "pas": pas, "debut": debut, "fin": fin,
            "taux": {f"{s:.2f}": t for s, t in zip(seuils, taux)},
        },
        "monotonie": {
            "saut_max_autorise": saut_max,
            # ---- Ce sur quoi porte le critère : la plage d'exploitation -------
            "plage_exploitation": [round(plage[0], 2), round(plage[1], 2)],
            "saut_max_dans_la_plage": pire_plage["saut"] if pire_plage else 0.0,
            "entre_dans_la_plage": ([pire_plage["de"], pire_plage["a"]]
                                    if pire_plage else None),
            "conforme": bool(pire_plage is not None
                             and pire_plage["saut"] <= saut_max),
            # ---- Pour mémoire : la grille entière, et l'ancien pas -----------
            "saut_max_grille_entiere": pire["saut"] if pire else 0.0,
            "entre_grille_entiere": [pire["de"], pire["a"]] if pire else None,
            "saut_max_grille_0_05": round(pire_gros, 4),
            "note": (
                "Critère apprécié sur la plage d'exploitation, déduite de la "
                "charge visée. Au pas de 0,05 la grille affichait %.1f points, "
                "au pas de %.2f elle en affiche %.1f sur la grille entière et "
                "%.1f sur la plage — l'essentiel de l'écart était un artefact "
                "de mesure, le reste porte sur des seuils inexploitables."
                % (pire_gros * 100, pas, (pire["saut"] if pire else 0) * 100,
                   (pire_plage["saut"] if pire_plage else 0) * 100)),
        },
        "seuils_dans_la_cible": {
            "bande_visee": [bas, haut],
            "seuils": [f"{s:.2f}" for s in dans_cible],
            "min": f"{min(dans_cible):.2f}" if dans_cible else None,
            "max": f"{max(dans_cible):.2f}" if dans_cible else None,
            "atteignable": bool(dans_cible),
        },
    }


def _criteres_famille_bc(cfg: Dict[str, Any], jeu, res,
                         niv1: Dict[str, Any]) -> Dict[str, Any]:
    """Critères d'acceptation calculables, confrontés aux cibles de configuration.

    Calculés, pas recopiés à la main : la table de recette doit se régénérer avec
    le modèle, sinon elle décrit un état antérieur sans que personne ne le voie.

    L'erreur de volume est la grandeur d'usage de Cultura (O-3) : ce sont les
    effectifs par (thème × sentiment) qui pilotent la priorisation, pas le F1.
    Le PO a tranché le 11/09 : **elle s'apprécie au global**. Le détail par
    couple reste produit et publié — en suivi, pas en engagement.
    """
    cibles = ((cfg.get("decision") or {}).get("cibles") or {})
    cible_vol = float(cibles.get("erreur_volume", 0.15))
    maille = str(cibles.get("erreur_volume_maille", "globale"))
    seuil_volume = int(cibles.get("erreur_volume_seuil_significativite", 20))
    ann = jeu["theme1_niv1"].notna() & jeu["sentiment"].notna() & (jeu["sentiment"] != "")

    reels: Dict[tuple, int] = {}
    predits: Dict[tuple, int] = {}
    for (t, s_), n in jeu.loc[ann].groupby(["theme1_niv1", "sentiment"]).size().items():
        reels[(t, s_)] = int(n)
    sous = res.loc[ann.values]
    for (t, s_), n in sous.groupby(["theme1_niv1", "theme1_sentiment"]).size().items():
        if t:
            predits[(t, s_)] = int(n)

    couples = []
    for cle in sorted(set(reels) | set(predits), key=lambda k: -reels.get(k, 0)):
        a, pr = reels.get(cle, 0), predits.get(cle, 0)
        couples.append({
            "theme": cle[0], "sentiment": cle[1], "annote": a, "predit": pr,
            "erreur_relative": round(abs(pr - a) / a, 4) if a else None,
        })
    total_a = sum(reels.values())
    erreur_globale = (sum(abs(predits.get(k, 0) - reels.get(k, 0))
                          for k in set(reels) | set(predits)) / total_a
                      if total_a else None)
    significatifs = [c for c in couples if c["annote"] >= seuil_volume]

    part_emise = niv1["distribution_nb_themes"]["part_bi_theme"]
    st = niv1["second_theme"]
    part_annotee = (st["verbatims_bi_themes_annotes"] / niv1["n"]) if niv1["n"] else 0.0
    facteur = float(cibles.get("facteur_part_bi_theme", 1.5))
    dans_bande = (part_annotee / facteur <= part_emise <= part_annotee * facteur
                  if part_annotee else None)

    return {
        "erreur_volume": {
            "cible": cible_vol,
            "maille_engagement": maille,
            "globale": round(erreur_globale, 4) if erreur_globale is not None else None,
            "conforme": (erreur_globale is not None and erreur_globale <= cible_vol)
                        if maille == "globale" else
                        all((c["erreur_relative"] or 0) <= cible_vol
                            for c in significatifs),
            "seuil_de_significativite": seuil_volume,
            "couples_significatifs": len(significatifs),
            "couples_significatifs_hors_cible": sum(
                1 for c in significatifs if (c["erreur_relative"] or 0) > cible_vol),
            "par_couple": couples,
        },
        "part_bi_theme": {
            "annotee": round(part_annotee, 4),
            "emise": part_emise,
            "facteur_cible": facteur,
            "bande": [round(part_annotee / facteur, 4), round(part_annotee * facteur, 4)],
            "dans_la_bande": dans_bande,
        },
        "faux_second_theme": {
            "mesure": st["taux_faux_second_theme"],
            "cible_cadrage": float(cibles.get("taux_faux_second_theme", 0.15)),
            "cible_resserree_proposee": float(
                cibles.get("taux_faux_second_theme_resserre", 0.10)),
            "statut": "engagement (arbitrage PO 11/09)",
            "conforme_resserree": (st["taux_faux_second_theme"] is not None
                                   and st["taux_faux_second_theme"]
                                   <= float(cibles.get("taux_faux_second_theme_resserre", 0.10))),
        },
        "precision_second_theme": {
            "mesure": st["precision_second_theme"],
            "cible": float(cibles.get("precision_second_theme", 0.70)),
            "statut_de_la_cible": cibles.get("precision_second_theme_statut", ""),
        },
    }


def _apport_des_leviers(cfg: Dict[str, Any], taxonomy, y_vrai, probs,
                        sources, f1_score) -> List[Dict[str, Any]]:
    """Rejoue la décision en ajoutant les leviers un à un.

    Chaque ligne est produite par ``PolitiqueDecision`` — la même classe que la
    production — sur une copie de la configuration où seuls les leviers voulus
    sont actifs.
    """
    dec = cfg.get("decision") or {}
    etapes = [
        ("seuil unique", []),
        ("+ seuils par thème", ["seuils_par_theme"]),
        ("+ arbitrage par source", ["seuils_par_theme", "regles_source"]),
        ("+ suppression des paires",
         ["seuils_par_theme", "regles_source", "paires_confusables"]),
    ]
    lignes: List[Dict[str, Any]] = []
    for libelle, actifs in etapes:
        variante = dict(cfg)
        variante["decision"] = {k: v for k, v in dec.items()
                                if k in actifs or k in _NON_LEVIERS}
        politique = PolitiqueDecision.depuis_config(variante, taxonomy)
        decisions = themes_par_verbatim(probs, politique, sources)
        y_dec = matrice_depuis_decisions(decisions, taxonomy.n_niv1)
        mesures = mesures_second_theme(y_vrai, decisions)
        lignes.append({
            "configuration": libelle,
            "f1_macro": round(float(f1_score(y_vrai, y_dec, average="macro",
                                             zero_division=0)), 4),
            "f1_micro": round(float(f1_score(y_vrai, y_dec, average="micro",
                                             zero_division=0)), 4),
            "part_bi_theme": distribution_nb_themes(y_dec)["part_bi_theme"],
            "precision_second_theme": mesures["precision_second_theme"],
            "taux_faux_second_theme": mesures["taux_faux_second_theme"],
            "rappel_second_theme": mesures["rappel_second_theme"],
            "compteurs": {k: v for k, v in politique.compteurs.items() if v},
        })
    return lignes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["train", "val", "test"])
    ap.add_argument("--donnees", default="data/processed/cultura_2026")
    ap.add_argument("--sortie", default="data/processed/eval_cultura_2026.json")
    ap.add_argument("--seuil", type=float, default=None,
                    help="seuil multi-label ; défaut = celui de config.yaml. "
                         "Le seuil opérationnel se cale sur la courbe de validation (L5').")
    ap.add_argument("--sans-leviers", action="store_true",
                    help="désactive les trois leviers de la couche de décision "
                         "(seuils par thème, arbitrage par source, paires "
                         "confusables) : mesure le modèle nu, à seuil unique.")
    args = ap.parse_args()

    cfg = load_config()
    carte = _configurer_nouveau_modele(cfg)
    # Le seuil est posé AVANT la construction du prédicteur. Auparavant il était
    # surchargé après l'inférence : les métriques de niveau 1 étaient calculées
    # au seuil demandé pendant que `res` (hiérarchie, D-40, confiance) sortait du
    # seuil de config. Les deux chiffres ne décrivaient plus la même décision —
    # inoffensif tant que seul le thème 1 comptait, faux dès que les leviers de
    # la couche de décision le déplacent.
    if args.seuil is not None:
        cfg["thresholds"]["classification_niv1"] = float(args.seuil)
    if args.sans_leviers:
        cfg["decision"] = _sans_leviers(cfg.get("decision") or {})
    print(f"Politique du modèle : {carte.get('politique_prefixe')} · "
          f"lowercase={carte.get('lowercase')}")

    taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))

    # Le corpus lu doit être CELUI SUR LEQUEL LE MODÈLE A ÉTÉ ENTRAÎNÉ : le
    # nettoyage est appliqué à la préparation, donc chaque variante a son
    # répertoire. Le déduire de la carte évite d'évaluer un modèle entraîné sans
    # minuscules sur un corpus mis en minuscules.
    suffixe = "" if carte.get("lowercase", True) else "_lc_false"
    dossier = ROOT / (args.donnees + suffixe)
    if not (dossier / "dataset.csv").is_file():
        raise SystemExit(
            f"Corpus introuvable : {dossier}. Le modèle déclare lowercase="
            f"{carte.get('lowercase')} ; préparer la variante correspondante.")
    print(f"Corpus : {dossier.name}")
    df = pd.read_csv(dossier / "dataset.csv", encoding="utf-8")
    df["text_clean"] = df["text_clean"].fillna("").astype(str)
    jeu = df[df["split"] == args.split].reset_index(drop=True)
    print(f"Jeu « {args.split} » : {len(jeu)} verbatims")

    # Le texte est déjà anonymisé et nettoyé par la préparation ; on ne le
    # retraite pas, sous peine de diverger de ce que le modèle a vu.
    textes = jeu["text_clean"].tolist()
    notes = [None if pd.isna(v) else float(v) for v in jeu["__satisfaction__"]]
    # La source alimente l'arbitrage contextuel de la couche de décision. Sans
    # elle, la règle post-réception ne s'appliquerait pas et l'évaluation
    # mesurerait un produit dégradé par rapport à celui qui sera livré.
    sources = [None if pd.isna(v) else str(v) for v in jeu["__source__"]]

    from src.inference.predictor import VerbatimPredictor

    predictor = VerbatimPredictor(cfg)
    t0 = time.time()
    sorties = predictor.predict_cleaned_batch(textes, notes, sources)
    duree = time.time() - t0
    res = pd.DataFrame(sorties)
    labels = cfg["sentiment"]["labels"]

    rapport: Dict[str, Any] = {
        "protocole": {
            "jeu": args.split,
            "n_verbatims": int(len(jeu)),
            "modele": "cultura_2026 (réentraîné)",
            "politique_prefixe": carte.get("politique_prefixe"),
            "lowercase": carte.get("lowercase"),
            "split": "par texte unique, sans fuite",
            "decision": predictor.politique.resume(),
        },
    }

    # --- Famille A : thématique (calculable, contrairement à la baseline) -----
    y_vrai = np.zeros((len(jeu), taxonomy.n_niv1), dtype=int)
    for i, (t1, t2) in enumerate(zip(jeu["theme1_niv1"], jeu["theme2_niv1"])):
        for t in (t1, t2):
            if isinstance(t, str) and t in taxonomy.niv1_to_idx:
                y_vrai[i, taxonomy.niv1_to_idx[t]] = 1
    annotes_theme = y_vrai.sum(axis=1) > 0

    probs_niv1 = predictor.clf_niv1.predict_proba(textes, predictor.batch_size)
    seuil = float(cfg["thresholds"]["classification_niv1"])
    rapport["protocole"]["seuil_multi_label"] = seuil
    cap = int(cfg["thresholds"]["max_themes"])
    from sklearn.metrics import f1_score, precision_score, recall_score

    yv, pv = y_vrai[annotes_theme], probs_niv1[annotes_theme]
    src_ann = [s for s, garde in zip(sources, annotes_theme) if garde]
    # LA décision — la même fonction que le prédicteur vient d'exécuter, avec les
    # mêmes sources. Ce n'est plus une réimplémentation « fidèle à la main ».
    decisions = themes_par_verbatim(pv, predictor.politique, src_ann)
    y_dec = matrice_depuis_decisions(decisions, taxonomy.n_niv1)
    rapport["niv1"] = {
        "n": int(annotes_theme.sum()),
        "f1_macro": round(float(f1_score(yv, y_dec, average="macro", zero_division=0)), 4),
        "f1_micro": round(float(f1_score(yv, y_dec, average="micro", zero_division=0)), 4),
        "precision_micro": round(float(precision_score(yv, y_dec, average="micro",
                                                       zero_division=0)), 4),
        "recall_micro": round(float(recall_score(yv, y_dec, average="micro",
                                                 zero_division=0)), 4),
        "distribution_nb_themes": distribution_nb_themes(y_dec),
        "second_theme": mesures_second_theme(yv, decisions),
        "f1_par_theme": {
            taxonomy.niv1_labels[i]: round(float(v), 4)
            for i, v in enumerate(f1_score(yv, y_dec, average=None, zero_division=0))
        },
        "support_par_theme": {
            taxonomy.niv1_labels[i]: int(yv[:, i].sum()) for i in range(taxonomy.n_niv1)
        },
    }

    # --- Apport de chaque levier, en cumulatif --------------------------------
    # Mesuré avec L'IMPLÉMENTATION DE PRODUCTION, pas une approximation : c'est
    # ce qui rend l'arbitrage du PO vérifiable. Cumulatif et non isolé, parce
    # que les leviers interagissent — les seuils par thème font monter les
    # bi-thèmes, que la suppression des paires reprend.
    rapport["apport_des_leviers"] = _apport_des_leviers(
        cfg, taxonomy, yv, pv, src_ann, f1_score)

    # Courbe de seuil (L5') — sur la VALIDATION, jamais sur le test.
    val = df[df["split"] == "val"].reset_index(drop=True)
    y_val = np.zeros((len(val), taxonomy.n_niv1), dtype=int)
    for i, (t1, t2) in enumerate(zip(val["theme1_niv1"], val["theme2_niv1"])):
        for t in (t1, t2):
            if isinstance(t, str) and t in taxonomy.niv1_to_idx:
                y_val[i, taxonomy.niv1_to_idx[t]] = 1
    m_val = y_val.sum(axis=1) > 0
    probs_val = predictor.clf_niv1.predict_proba(val["text_clean"].tolist(),
                                                 predictor.batch_size)
    rapport["courbe_seuil_validation"] = courbe_seuil(
        y_val[m_val], probs_val[m_val], seuils_par_defaut(0.20, 0.90, 0.05), cap)

    # --- Niveau 2, couple hiérarchique ----------------------------------------
    ok_couple = ok_niv2 = total_couple = 0
    for i in range(len(jeu)):
        vrai1, vrai2 = jeu["theme1_niv1"].iloc[i], jeu["theme1_niv2"].iloc[i]
        if not isinstance(vrai1, str) or not isinstance(vrai2, str):
            continue
        total_couple += 1
        if res["theme1_niv1"].iloc[i] == vrai1:
            ok_niv2 += 1
            if res["theme1_niv2"].iloc[i] == vrai2:
                ok_couple += 1
    rapport["hierarchie"] = {
        "n": total_couple,
        "p_niv1_correct": round(ok_niv2 / max(total_couple, 1), 4),
        "p_couple_correct": round(ok_couple / max(total_couple, 1), 4),
    }

    # --- Sentiment, même découpage que la baseline ----------------------------
    ann = jeu["sentiment"].notna() & (jeu["sentiment"] != "")
    vrais = jeu.loc[ann, "sentiment"].tolist()
    predits = res.loc[ann.values, "theme1_sentiment"].tolist()
    rapport["sentiment"] = {"global": metriques_sentiment(vrais, predits, labels)}
    rapport["sentiment"]["par_source"] = {
        src: metriques_sentiment(
            jeu.loc[ann & (jeu["__source__"] == src), "sentiment"].tolist(),
            res.loc[(ann & (jeu["__source__"] == src)).values, "theme1_sentiment"].tolist(),
            labels)
        for src in sorted(jeu["__source__"].unique())
    }
    tranches = cfg["baseline"]["tranches_longueur_mots"]
    jeu["__tranche__"] = [tranche_de(t, tranches) for t in jeu["text_clean"]]
    rapport["sentiment"]["par_tranche_de_longueur"] = {
        tr: metriques_sentiment(
            jeu.loc[ann & (jeu["__tranche__"] == tr), "sentiment"].tolist(),
            res.loc[(ann & (jeu["__tranche__"] == tr)).values, "theme1_sentiment"].tolist(),
            labels)
        for tr in [f"{b[0]}-{b[1]} mots" if b[1] is not None else f"{b[0]}+ mots"
                   for b in tranches]
    }

    # --- D-40 : niv2 vide + revue forcée --------------------------------------
    vides = int((res["theme1_niv2"] == "").sum())
    rapport["d40_routage_hors_perimetre"] = {
        "verbatims_niv2_vide": vides,
        "part": round(vides / max(len(res), 1), 4),
        "tous_en_revue": bool(res.loc[res["theme1_niv2"] == "",
                                      "revue_humaine_requise"].all()) if vides else None,
    }

    rapport["criteres"] = _criteres_famille_bc(cfg, jeu, res, rapport["niv1"])

    conf = res["confidence_globale"].astype(float)
    rapport["confiance"] = _courbe_taux_de_revue(cfg, conf)
    rapport["debit"] = {
        "verbatims_par_seconde": round(len(jeu) / max(duree, 1e-9), 2),
        "duree_inference_s": round(duree, 1),
    }

    chemin = ROOT / args.sortie
    chemin.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")

    n1, g = rapport["niv1"], rapport["sentiment"]["global"]
    print("\n" + "=" * 74)
    print(f"  MODÈLE RÉENTRAÎNÉ — jeu « {args.split} », {len(jeu)} verbatims")
    print("=" * 74)
    print(f"\n  Niveau 1 (n={n1['n']}) : F1-macro {n1['f1_macro']} · F1-micro {n1['f1_micro']}")
    print(f"     précision micro {n1['precision_micro']} · rappel micro {n1['recall_micro']}")
    d = n1["distribution_nb_themes"]
    print(f"     {d['part_bi_theme']*100:.1f} % de sorties bi-thèmes · "
          f"{d['moyenne_themes_par_verbatim']} thèmes/verbatim")
    st = n1["second_theme"]
    print(f"     2e thème : précision {st['precision_second_theme']} · "
          f"faux 2e {st['taux_faux_second_theme']} · rappel {st['rappel_second_theme']} "
          f"(n bi-thèmes = {st['verbatims_bi_themes_annotes']})")
    h = rapport["hierarchie"]
    print(f"  Hiérarchie : P(niv1) {h['p_niv1_correct']} · P(couple) {h['p_couple_correct']}")
    print("\n  Apport des leviers de décision (cumulatif, n=%d) :" % n1["n"])
    print(f"     {'configuration':<26} {'F1-macro':>9} {'bi-th.':>8} {'prec.2e':>8} {'faux 2e':>8}")
    for l in rapport["apport_des_leviers"]:
        print(f"     {l['configuration']:<26} {l['f1_macro']:>9} "
              f"{l['part_bi_theme']:>8} {str(l['precision_second_theme']):>8} "
              f"{str(l['taux_faux_second_theme']):>8}")
    print(f"\n  Sentiment (n={g['n']}) : accuracy {g['accuracy']} · F1-macro {g['f1_macro']}")
    for lab, v in g["f1_par_classe"].items():
        print(f"     F1 {lab:8s} {v}")
    cr = rapport["criteres"]
    ev_, bt = cr["erreur_volume"], cr["part_bi_theme"]
    print(f"\n  Critères d'exploitation :")
    print(f"     erreur de volume (thème × sentiment) : {ev_['globale']} au global "
          f"(cible ≤ {ev_['cible']}, maille d'engagement : {ev_['maille_engagement']}) "
          f"-> {'conforme' if ev_['conforme'] else 'NON CONFORME'}")
    print(f"        suivi : {ev_['couples_significatifs_hors_cible']}"
          f"/{ev_['couples_significatifs']} couples ≥ "
          f"{ev_['seuil_de_significativite']} verbatims au-delà de la cible")
    print(f"     part bi-thèmes : {bt['emise']} émise pour {bt['annotee']} annotée "
          f"· bande {bt['bande']} -> {'dans la bande' if bt['dans_la_bande'] else 'HORS BANDE'}")
    print(f"     faux second thème : {cr['faux_second_theme']['mesure']} "
          f"(engagement ≤ {cr['faux_second_theme']['cible_resserree_proposee']})")
    ps = cr["precision_second_theme"]
    print(f"     précision 2e thème : {ps['mesure']} — {ps['statut_de_la_cible']}")
    print(f"\n  D-40 : {rapport['d40_routage_hors_perimetre']['verbatims_niv2_vide']} "
          f"verbatims à niv2 vide, tous en revue = "
          f"{rapport['d40_routage_hors_perimetre']['tous_en_revue']}")
    mo = rapport["confiance"]["monotonie"]
    sc = rapport["confiance"]["seuils_dans_la_cible"]
    print(f"\n  Seuil de revue (grille au pas de {rapport['confiance']['grille_fine']['pas']}) :")
    print(f"     plage d'exploitation {mo['plage_exploitation']} : saut maximal "
          f"{mo['saut_max_dans_la_plage']*100:.1f} pts entre "
          f"{mo['entre_dans_la_plage'][0]} et {mo['entre_dans_la_plage'][1]} "
          f"(autorisé ≤ {mo['saut_max_autorise']*100:.0f}) "
          f"-> {'conforme' if mo['conforme'] else 'NON CONFORME'}")
    print(f"     pour mémoire : {mo['saut_max_grille_entiere']*100:.1f} pts sur la "
          f"grille entière (à {mo['entre_grille_entiere'][1]}), "
          f"{mo['saut_max_grille_0_05']*100:.1f} pts au pas de 0,05")
    print(f"     charge de {sc['bande_visee'][0]*100:.0f}-{sc['bande_visee'][1]*100:.0f} % "
          f"atteinte pour un seuil de {sc['min']} à {sc['max']}"
          if sc["atteignable"] else "     charge visée INATTEIGNABLE sur la grille")
    print(f"  Débit : {rapport['debit']['verbatims_par_seconde']} verbatims/s")
    print(f"\n  => {chemin.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
