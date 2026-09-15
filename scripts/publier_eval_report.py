#!/usr/bin/env python3
"""Produit `eval_report.json` au format attendu par l'application — lot L9.

Pourquoi ce script existe
-------------------------
`app/worker/model_registry.py → _summary_metrics()` lit quatre valeurs dans
`data/processed/eval_report.json` et les expose aux tableaux de bord :

    niv1.f1_macro · niv2.f1_macro · sentiment.accuracy · signals.rupture.recall

Ce fichier contient aujourd'hui les métriques du 18/06/2026, **invalides** : elles
ont été mesurées sur un découpage où 99,6 % des lignes de test avaient leur texte
dans le train. Activer le nouveau modèle sans régénérer ce fichier ferait afficher
les chiffres de la fuite comme s'ils étaient les siens.

Le fichier produit porte en plus un bloc `provenance` : protocole, jeu, versions
de modèles, seuil. Sans lui, rien ne distingue un rapport honnête d'un rapport
invalide — c'est précisément ce qui a permis au défaut du prototype de survivre
deux mois.

Usage :
    python scripts/publier_eval_report.py --source data/processed/eval_iter3_s0.85.json
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/processed/eval_leviers_test.json")
    ap.add_argument("--baseline", default="data/processed/baseline_modele_actuel.json")
    ap.add_argument("--sortie", default="data/processed/eval_report_cultura_2026.json")
    args = ap.parse_args()

    ev: Dict[str, Any] = json.loads((ROOT / args.source).read_text(encoding="utf-8"))
    base_path = ROOT / args.baseline
    base = json.loads(base_path.read_text(encoding="utf-8")) if base_path.is_file() else {}

    sent = ev["sentiment"]["global"]
    n1 = ev["niv1"]
    hier = ev.get("hierarchie", {})

    rapport: Dict[str, Any] = {
        # --- contrat lu par model_registry._summary_metrics ------------------
        "niv1": {
            "f1_macro": n1["f1_macro"],
            "f1_micro": n1["f1_micro"],
            "precision_micro": n1["precision_micro"],
            "recall_micro": n1["recall_micro"],
            "seuil": ev["protocole"].get("seuil_multi_label"),
            "max_themes": 2,
            "distribution_nb_themes": n1["distribution_nb_themes"],
            "second_theme": n1["second_theme"],
            "f1_par_theme": n1.get("f1_par_theme", {}),
        },
        # Le F1-macro de niveau 2 n'est pas mesuré isolément : la grandeur qui
        # compte pour l'usage est le couple, et c'est elle qui est publiée.
        "niv2": {
            "f1_macro": None,
            "commentaire": ("non mesuré isolément — la grandeur d'usage est "
                            "`hierarchical.p_joint_correct`, le couple complet"),
        },
        "hierarchical": {
            "p_niv1_correct": hier.get("p_niv1_correct"),
            "p_joint_correct": hier.get("p_couple_correct"),
        },
        "sentiment": {
            "accuracy": sent["accuracy"],
            "f1_macro": sent["f1_macro"],
            "f1_par_classe": sent["f1_par_classe"],
            "par_source": {k: {"accuracy": v["accuracy"], "f1_macro": v["f1_macro"],
                               "n": v["n"]}
                           for k, v in ev["sentiment"].get("par_source", {}).items()},
            "par_tranche_de_longueur": {
                k: {"accuracy": v["accuracy"], "f1_macro": v["f1_macro"], "n": v["n"]}
                for k, v in ev["sentiment"].get("par_tranche_de_longueur", {}).items()},
        },
        # D-41 : seul `insatisfaction` a un modèle. `rupture` et `churn` n'en ont
        # pas — la clé est volontairement absente plutôt que remplie d'un zéro,
        # pour que le tableau de bord n'affiche pas une performance inventée.
        "signals": {
            "insatisfaction": {"commentaire": "métriques en validation, cf. bilan d'entraînement"},
            "_non_entraines": {
                "churn": "64 positifs au corpus — non évaluable (D-41)",
                "rupture": "32 positifs au corpus — non évaluable (D-41)",
            },
        },
        "human_review": ev.get("confiance", {}).get("taux_de_revue_par_seuil", {}),
    }

    # Les leviers de la couche de décision déplacent le thème 1 : le rapport doit
    # dire lesquels étaient actifs et ce que chacun apporte, sinon le chiffre
    # publié n'est pas reproductible.
    if ev.get("apport_des_leviers"):
        rapport["couche_de_decision"] = {
            "politique": ev["protocole"].get("decision"),
            "apport_cumulatif": ev["apport_des_leviers"],
            "reference": "docs/OPTIMISATION_SANS_CULTURA.md",
        }

    rapport["provenance"] = {
        "date": date.today().isoformat(),
        "modele": "cultura_2026",
        "protocole": ev["protocole"],
        "jeu": "test du découpage gelé, jamais vu à l'entraînement ni au réglage des seuils",
        "remplace": ("data/processed/eval_report.json du 18/06/2026, INVALIDE "
                     "(99,6 % des lignes de test avaient leur texte dans le train)"),
        "comparaison_ancien_modele": {
            "sentiment_accuracy": base.get("sentiment", {}).get("global", {}).get("accuracy"),
            "sentiment_f1_macro": base.get("sentiment", {}).get("global", {}).get("f1_macro"),
            "note": ("aucune comparaison thématique possible : 1 libellé de niveau 1 "
                     "commun sur 20/11, 0 sur 67/59 en niveau 2 (D-36)"),
        },
        "planchers_ef3": {
            "accuracy_regle": base.get("non_trivialite_sentiment", {}).get("accuracy_regle"),
            "f1_macro_regle": base.get("non_trivialite_sentiment", {}).get("f1_macro_regle"),
        },
    }

    chemin = ROOT / args.sortie
    chemin.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Rapport d'évaluation au format applicatif")
    print(f"  niv1.f1_macro        {rapport['niv1']['f1_macro']}")
    print(f"  niv2.f1_macro        {rapport['niv2']['f1_macro']}  (voir commentaire)")
    print(f"  hierarchical.p_joint {rapport['hierarchical']['p_joint_correct']}")
    print(f"  sentiment.accuracy   {rapport['sentiment']['accuracy']}")
    print(f"  signals.rupture      absent — non entraîné (D-41)")
    if "couche_de_decision" in rapport:
        ap_ = rapport["couche_de_decision"]["apport_cumulatif"]
        print(f"  couche de décision   {ap_[0]['f1_macro']} -> {ap_[-1]['f1_macro']} "
              f"F1-macro ({len(ap_) - 1} leviers)")
    print(f"\n  => {chemin.relative_to(ROOT)}")
    print("  ⚠️ NON copié sur `eval_report.json` : cette copie fait partie de la "
          "procédure d'activation, pas de sa préparation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
