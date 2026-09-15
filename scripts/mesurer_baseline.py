#!/usr/bin/env python3
"""Baseline honnête du modèle ACTUEL sur les données réelles Cultura — lot L2.

Périmètre arbitré par le PO le 09/09/2026
-----------------------------------------
**Il n'y a pas de baseline thématique.** Les référentiels ancien et nouveau
partagent 1 libellé de niveau 1 (sur 20 / 11) et **0** de niveau 2 (sur 67 / 59) :
aucun F1 thématique n'est calculable entre les prédictions de l'ancien modèle et
les annotations Cultura. Aucune table de correspondance n'est construite — le
chiffre qu'elle produirait dépendrait entièrement d'elle.

Ce que ce script mesure :

* **Sentiment** — les 3 classes sont identiques dans les deux mondes. Mesuré
  globalement, **par source** (R-16) et **par tranche de longueur** (D-28).
* **Distribution du nombre de thèmes** (EF-4) — indépendante des libellés. C'est
  la mesure du grief n°1.
* **Recopie du sentiment** entre thème 1 et thème 2 — point de départ connu :
  0 divergence sur 52.
* **Taux de revue et distribution de confiance**.
* **Débit**, chronométré puis extrapolé au volume mensuel.

Le préfixe de satisfaction conserve le dénominateur ``/10`` des modèles actifs, et
la note Cultura 1-4 y est **rééchelonnée** (arbitrage PO) : injecter la note brute
ferait passer un 4/4 pour ``[SATISFACTION 4/10]``, que l'entraînement associe au
négatif. Un bras de contrôle **sans préfixe** est mesuré en parallèle.

Usage :
    python scripts/mesurer_baseline.py [--split test] [--limite N]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.preprocessing import Anonymizer, TextCleaner  # noqa: E402
from src.preprocessing.cultura_loader import charger_cultura  # noqa: E402
from src.training.split_sans_fuite import appliquer_split_gele  # noqa: E402
from src.utils.config import load_config, resolve_path  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("baseline")


# --------------------------------------------------------------------------- #
def reechelonner(note: Optional[float], table: Dict[Any, int]) -> Optional[int]:
    """Projette la note Cultura 1-4 sur l'échelle 1-10 des modèles actifs."""
    if note is None or (isinstance(note, float) and note != note):
        return None
    try:
        cle = int(round(float(note)))
    except (TypeError, ValueError):
        return None
    return table.get(cle, table.get(str(cle)))


def tranche_de(texte: str, tranches: List[List[Optional[int]]]) -> str:
    """Libellé de la tranche de longueur (en mots) à laquelle appartient un texte."""
    n = len([t for t in str(texte).split() if t])
    for borne in tranches:
        bas, haut = borne[0], borne[1]
        if n >= bas and (haut is None or n <= haut):
            return f"{bas}-{haut} mots" if haut is not None else f"{bas}+ mots"
    return "hors tranche"


def metriques_sentiment(vrais: List[str], predits: List[str],
                        labels: List[str]) -> Dict[str, Any]:
    """Accuracy, F1-macro et F1 par classe. ``None`` si l'échantillon est vide."""
    from sklearn.metrics import accuracy_score, f1_score

    if not vrais:
        return {"n": 0, "accuracy": None, "f1_macro": None, "f1_par_classe": {}}
    f1c = f1_score(vrais, predits, average=None, labels=labels, zero_division=0)
    return {
        "n": len(vrais),
        "accuracy": round(float(accuracy_score(vrais, predits)), 4),
        "f1_macro": round(float(f1_score(vrais, predits, average="macro",
                                         labels=labels, zero_division=0)), 4),
        "f1_par_classe": {lab: round(float(f1c[i]), 4) for i, lab in enumerate(labels)},
        "repartition_vraie": {lab: int(sum(1 for v in vrais if v == lab)) for lab in labels},
    }


# --------------------------------------------------------------------------- #
#: Seuil multi-label en vigueur quand la baseline V1 a été mesurée. Voir main().
SEUIL_NIV1_BASELINE = 0.35
DATE_MESURE_BASELINE = "09/09/2026"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["train", "val", "test"])
    ap.add_argument("--limite", type=int, default=None,
                    help="limiter le nombre de verbatims (mise au point)")
    ap.add_argument("--sortie", default="data/processed/baseline_modele_actuel.json")
    args = ap.parse_args()

    cfg = load_config()
    conf = cfg["baseline"]

    # ------------------------------------------------------------------ #
    #  Reproductibilité de la baseline (D-36).
    #  La baseline décrit le modèle V1 TEL QU'IL TOURNAIT : seuil 0,35 et aucun
    #  levier de décision. `config.yaml` porte désormais le seuil du modèle
    #  réentraîné (0,85) et les trois leviers du 11/09/2026 — les appliquer ici
    #  changerait un chiffre déjà publié et rendrait la comparaison
    #  ancien/nouveau fausse dans les deux sens.
    #
    #  Ces valeurs sont donc FIGÉES dans le script, avec la date de la mesure.
    #  Ce n'est pas un nombre magique : c'est la description d'un état passé.
    # ------------------------------------------------------------------ #
    cfg["thresholds"]["classification_niv1"] = SEUIL_NIV1_BASELINE
    cfg["decision"] = {}
    print(f"Baseline figée : seuil niv.1 {SEUIL_NIV1_BASELINE}, aucun levier de "
          f"décision (état du modèle V1 au {DATE_MESURE_BASELINE}).")

    print("Chargement de la livraison Cultura…")
    df, _ = charger_cultura(cfg)
    # Le découpage est LU dans le jeu gelé, jamais recalculé : la baseline et le
    # modèle réentraîné doivent être mesurés sur exactement le même jeu de test.
    chemin_gel = resolve_path(cfg, cfg["dataset"]["split_gele"])
    if not chemin_gel.is_file():
        raise SystemExit(
            f"Jeu de recette gelé introuvable : {chemin_gel}. Le produire d'abord "
            "avec `python -c \"from src.training.preparer_cultura import preparer; ...\"` "
            "ou `scripts/entrainer_cultura.py`, sinon les mesures ne seront pas "
            "comparables entre elles.")
    df = appliquer_split_gele(df, chemin_gel)
    jeu = df[df["split"] == args.split].reset_index(drop=True)
    if args.limite:
        jeu = jeu.head(args.limite).copy()
    print(f"  jeu « {args.split} » : {len(jeu)} verbatims")

    # --- Préparation identique à la chaîne de production ---------------------
    anonymizer = Anonymizer(cfg)
    cleaner = TextCleaner(cfg)
    print("Anonymisation et nettoyage…")
    pii = 0
    masques: List[str] = []
    t0 = time.time()
    for brut in jeu["__text_raw__"].tolist():
        masque, compte = anonymizer.anonymize(brut)
        pii += sum(compte.values())
        masques.append(masque)
    t_anon = time.time() - t0
    t0 = time.time()
    nettoyes = [cleaner.clean(m) for m in masques]
    t_clean = time.time() - t0
    jeu["text_clean"] = nettoyes
    print(f"  {pii} entités PII masquées · anonymisation {t_anon:.1f}s "
          f"({len(jeu)/max(t_anon,1e-9):.0f}/s) · nettoyage {t_clean:.1f}s")

    notes = [reechelonner(n, conf["reechelonnage_satisfaction"])
             for n in jeu["__satisfaction__"].tolist()]

    # --- Inférence -----------------------------------------------------------
    from src.inference.predictor import VerbatimPredictor

    print("Chargement des modèles actifs…")
    t0 = time.time()
    predictor = VerbatimPredictor(cfg)
    t_charge = time.time() - t0
    print(f"  chargés en {t_charge:.1f}s")

    print(f"Inférence sur {len(jeu)} verbatims…")
    t0 = time.time()
    sorties = predictor.predict_cleaned_batch(nettoyes, notes)
    t_infer = time.time() - t0
    debit = len(jeu) / max(t_infer, 1e-9)
    print(f"  {t_infer:.1f}s  ->  {debit:.1f} verbatims/s")

    res = pd.DataFrame(sorties)
    labels = cfg["sentiment"]["labels"]

    # --- 1. Sentiment (bras principal, préfixe rééchelonné) ------------------
    annotes = jeu["sentiment"].notna() & (jeu["sentiment"] != "")
    vrais = jeu.loc[annotes, "sentiment"].tolist()
    predits = res.loc[annotes.values, "theme1_sentiment"].tolist()

    rapport: Dict[str, Any] = {
        "protocole": {
            "jeu": args.split,
            "n_verbatims": int(len(jeu)),
            "n_annotes_sentiment": int(annotes.sum()),
            "split": "par texte unique, sans fuite (contrôle bloquant)",
            "prefixe_satisfaction": (
                f"[SATISFACTION x/{cfg['sentiment']['satisfaction_scale_max']}], "
                f"note Cultura 1-4 rééchelonnée "
                f"{conf['reechelonnage_satisfaction']} (arbitrage PO 09/09)"
            ),
            "modeles": {
                "niv1": "classifier_niv1 CURRENT",
                "niv2": "classifier_niv2 CURRENT",
                "sentiment": "sentiment CURRENT",
                "signals": "signals CURRENT",
            },
            "hors_perimetre": (
                "F1 thématique : non calculable — 1 libellé niv.1 commun sur 20/11, "
                "0 sur 67/59 en niv.2 (arbitrage PO : pas de table de correspondance)"
            ),
        },
        "sentiment": {"global": metriques_sentiment(vrais, predits, labels)},
    }

    if conf.get("par_source", True):
        par_source = {}
        for src in sorted(jeu["__source__"].unique()):
            m = annotes & (jeu["__source__"] == src)
            par_source[src] = metriques_sentiment(
                jeu.loc[m, "sentiment"].tolist(),
                res.loc[m.values, "theme1_sentiment"].tolist(), labels)
        rapport["sentiment"]["par_source"] = par_source

    # --- 2. Bras de contrôle : sans préfixe ----------------------------------
    if conf.get("mesurer_sans_prefixe", True):
        print("Bras de contrôle sans préfixe de satisfaction…")
        t0 = time.time()
        probs = predictor.clf_sentiment.predict_proba(nettoyes, predictor.batch_size)
        sans = [labels[int(i)] for i in probs.argmax(axis=1)]
        sans_annotes = [s for s, a in zip(sans, annotes) if a]
        rapport["sentiment"]["sans_prefixe"] = metriques_sentiment(vrais, sans_annotes, labels)
        rapport["sentiment"]["sans_prefixe"]["duree_s"] = round(time.time() - t0, 1)
        jeu["__sans_prefixe__"] = sans

    tranches = conf["tranches_longueur_mots"]
    jeu["__tranche__"] = [tranche_de(t, tranches) for t in jeu["text_clean"]]
    par_tranche = {}
    for tr in [f"{b[0]}-{b[1]} mots" if b[1] is not None else f"{b[0]}+ mots"
               for b in tranches]:
        m = annotes & (jeu["__tranche__"] == tr)
        bloc = metriques_sentiment(
            jeu.loc[m, "sentiment"].tolist(),
            res.loc[m.values, "theme1_sentiment"].tolist(), labels)
        # Apport réel du préfixe, tranche par tranche. Hypothèse à trancher :
        # sur les verbatims très courts (médiane 6 mots), la performance
        # viendrait de la note de satisfaction, pas du texte.
        if "__sans_prefixe__" in jeu.columns:
            sp = metriques_sentiment(
                jeu.loc[m, "sentiment"].tolist(),
                jeu.loc[m, "__sans_prefixe__"].tolist(), labels)
            bloc["sans_prefixe"] = {"accuracy": sp["accuracy"], "f1_macro": sp["f1_macro"]}
            if bloc["accuracy"] is not None and sp["accuracy"] is not None:
                bloc["apport_du_prefixe_accuracy"] = round(bloc["accuracy"] - sp["accuracy"], 4)
        par_tranche[tr] = bloc
    rapport["sentiment"]["par_tranche_de_longueur"] = par_tranche

    # --- 2 bis. Non-trivialité du sentiment (EF-3) ---------------------------
    # « La règle note -> sentiment doit avoir une précision strictement
    # inférieure à celle du modèle. » On construit la MEILLEURE règle possible
    # sur ce jeu — la classe majoritaire par note — ce qui la surestime
    # délibérément : si le modèle la bat quand même, EF-3 est satisfaite sans
    # discussion. Comparaison ajoutée : la règle triviale « tout positif ».
    from collections import Counter, defaultdict

    # La règle est APPRISE SUR LE TRAIN et évaluée sur le test, comme le modèle :
    # la dériver sur le test lui-même la surestimerait, et la comparaison ne
    # vaudrait rien. On publie les deux pour rendre l'écart visible.
    entrainement = df[df["split"] == "train"]
    ann_tr = entrainement["sentiment"].notna() & (entrainement["sentiment"] != "")

    def _regle(notes, sentiments):
        par_note = defaultdict(Counter)
        for note, vrai in zip(notes, sentiments):
            if note is not None and note == note:
                par_note[int(note)][vrai] += 1
        return {n: c.most_common(1)[0][0] for n, c in par_note.items()}

    regle_train = _regle(entrainement.loc[ann_tr, "__satisfaction__"].tolist(),
                         entrainement.loc[ann_tr, "sentiment"].tolist())
    notes_test = jeu.loc[annotes, "__satisfaction__"].tolist()
    regle_test = _regle(notes_test, vrais)

    def _applique(regle_):
        return [regle_.get(int(n)) if (n is not None and n == n) else None
                for n in notes_test]

    def _acc(pred):
        couples = [(v, p) for v, p in zip(vrais, pred) if p is not None]
        return (round(sum(1 for v, p in couples if v == p) / len(couples), 4)
                if couples else None), len(couples)

    pred_tr = _applique(regle_train)
    acc_tr, n_tr = _acc(pred_tr)
    acc_te, _ = _acc(_applique(regle_test))

    # F1-macro de la règle : elle ne peut jamais prédire `Neutre`, qui n'est
    # majoritaire pour aucune note. L'accuracy l'avantage, le F1-macro non.
    couples_tr = [(v, p) for v, p in zip(vrais, pred_tr) if p is not None]
    m_regle = metriques_sentiment([v for v, _ in couples_tr],
                                  [p for _, p in couples_tr], labels)

    majoritaire = Counter(vrais).most_common(1)[0]
    acc_modele = rapport["sentiment"]["global"]["accuracy"]
    f1_modele = rapport["sentiment"]["global"]["f1_macro"]
    rapport["non_trivialite_sentiment"] = {
        "exigence": "EF-3 — le sentiment ne doit pas être déductible de la seule note",
        "protocole": ("règle apprise sur le split train (classe majoritaire par "
                      "note), évaluée sur le test — même jeu que le modèle"),
        "regle_apprise_sur_train": {str(k): v for k, v in sorted(regle_train.items())},
        "regle_ajustee_sur_test": {str(k): v for k, v in sorted(regle_test.items())},
        "accuracy_regle": acc_tr,
        "accuracy_regle_ajustee_sur_test": acc_te,
        "f1_macro_regle": m_regle["f1_macro"],
        "f1_par_classe_regle": m_regle["f1_par_classe"],
        "accuracy_classe_majoritaire": round(majoritaire[1] / max(len(vrais), 1), 4),
        "classe_majoritaire": majoritaire[0],
        "accuracy_modele": acc_modele,
        "f1_macro_modele": f1_modele,
        "n_compares": n_tr,
        "verdict_accuracy": (
            "modèle > règle" if acc_tr is not None and acc_modele > acc_tr
            else "RÈGLE >= MODÈLE — EF-3 non satisfaite sur l'accuracy"),
        "verdict_f1_macro": (
            "modèle > règle" if f1_modele > (m_regle["f1_macro"] or 0)
            else "RÈGLE >= MODÈLE — EF-3 non satisfaite sur le F1-macro"),
    }

    # --- 3. Comportement multi-thème (EF-4) ----------------------------------
    nb = res["nb_themes"].astype(int)
    bi = res[nb >= 2]
    divergents = int((bi["theme1_sentiment"] != bi["theme2_sentiment"]).sum()) if len(bi) else 0
    annot_bi = int((jeu["theme2_niv1"].notna() & (jeu["theme2_niv1"] != "")).sum())
    rapport["multi_theme"] = {
        "distribution_nb_themes": {str(k): int(v) for k, v in nb.value_counts().sort_index().items()},
        "part_bi_theme_predite": round(float((nb >= 2).mean()), 4),
        "part_bi_theme_annotee": round(annot_bi / max(len(jeu), 1), 4),
        "moyenne_themes_par_verbatim": round(float(nb.mean()), 4),
        "sorties_bi_themes": int(len(bi)),
        "sentiments_divergents_entre_themes": divergents,
        "commentaire": (
            "EF-2/D-26 : le sentiment est unique par verbatim et recopié sur le "
            "thème 2 par construction (build_output, l. 77-93). Une valeur non "
            "nulle ici signalerait un changement de comportement du code."
        ),
    }

    # --- 4. Confiance et revue humaine ---------------------------------------
    conf_g = res["confidence_globale"].astype(float)
    rapport["confiance"] = {
        "moyenne": round(float(conf_g.mean()), 4),
        "min": round(float(conf_g.min()), 4),
        "max": round(float(conf_g.max()), 4),
        "taux_de_revue_par_seuil": {
            f"{s:.2f}": round(float((conf_g < s).mean()), 4)
            for s in (0.50, 0.60, 0.65, 0.70, 0.75, 0.80)
        },
    }

    # --- 5. Débit -------------------------------------------------------------
    cible = int(conf.get("volume_cible_debit", 11000))
    total_chaine = t_anon + t_clean + t_infer
    rapport["debit"] = {
        "n_mesure": int(len(jeu)),
        "duree_anonymisation_s": round(t_anon, 1),
        "duree_nettoyage_s": round(t_clean, 1),
        "duree_inference_s": round(t_infer, 1),
        "duree_chaine_complete_s": round(total_chaine, 1),
        "part_anonymisation": round(t_anon / max(total_chaine, 1e-9), 4),
        "extrapolation_heures_chaine_complete": round(
            cible / max(len(jeu) / max(total_chaine, 1e-9), 1e-9) / 3600, 2),
        "verbatims_par_seconde": round(debit, 2),
        "duree_chargement_modeles_s": round(t_charge, 1),
        "extrapolation_heures_pour_cible": round(cible / max(debit, 1e-9) / 3600, 2),
        "volume_cible": cible,
        "avertissement": (
            "Extrapolation linéaire depuis un lot de "
            f"{len(jeu)} verbatims, hors entrées/sorties base et export. "
            "Ne remplace PAS la mesure de bout en bout du lot L8 sur 11 000."
        ),
    }

    chemin = ROOT / args.sortie
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- Affichage ------------------------------------------------------------
    g = rapport["sentiment"]["global"]
    print("\n" + "=" * 74)
    print(f"  BASELINE DU MODÈLE ACTUEL — jeu « {args.split} », {len(jeu)} verbatims")
    print("=" * 74)
    print(f"\n  Sentiment (n={g['n']}) : accuracy {g['accuracy']} · F1-macro {g['f1_macro']}")
    for lab, v in g["f1_par_classe"].items():
        print(f"     F1 {lab:8s} {v}   (n={g['repartition_vraie'][lab]})")
    if "sans_prefixe" in rapport["sentiment"]:
        sp = rapport["sentiment"]["sans_prefixe"]
        print(f"  Sans préfixe          : accuracy {sp['accuracy']} · F1-macro {sp['f1_macro']}")
    print("\n  Par source :")
    for src, m in rapport["sentiment"].get("par_source", {}).items():
        print(f"     {src:20s} n={m['n']:5d}  accuracy {m['accuracy']}  F1-macro {m['f1_macro']}")
    print("\n  Par tranche de longueur (D-28) — et apport réel du préfixe :")
    for tr, m in rapport["sentiment"]["par_tranche_de_longueur"].items():
        ap = m.get("apport_du_prefixe_accuracy")
        sp = m.get("sans_prefixe", {}).get("accuracy")
        extra = (f"  | sans préfixe {sp}  (apport {ap:+.4f})"
                 if ap is not None else "")
        print(f"     {tr:14s} n={m['n']:5d}  accuracy {m['accuracy']}  "
              f"F1-macro {m['f1_macro']}{extra}")
    nt = rapport["non_trivialite_sentiment"]
    print(f"\n  Non-trivialité du sentiment (EF-3) — règle apprise sur train, "
          f"évaluée sur test :")
    print(f"     règle          : {nt['regle_apprise_sur_train']}")
    print(f"     accuracy       : modèle {nt['accuracy_modele']} · "
          f"règle {nt['accuracy_regle']} · classe majoritaire "
          f"{nt['accuracy_classe_majoritaire']}   -> {nt['verdict_accuracy']}")
    print(f"     F1-macro       : modèle {nt['f1_macro_modele']} · "
          f"règle {nt['f1_macro_regle']}   -> {nt['verdict_f1_macro']}")
    print(f"     F1 par classe de la règle : {nt['f1_par_classe_regle']}")
    mt = rapport["multi_theme"]
    print(f"\n  Multi-thème : {mt['part_bi_theme_predite']*100:.1f} % de sorties bi-thèmes "
          f"contre {mt['part_bi_theme_annotee']*100:.1f} % d'annotations bi-thèmes")
    print(f"                {mt['moyenne_themes_par_verbatim']} thèmes/verbatim · "
          f"{mt['sentiments_divergents_entre_themes']} sentiment(s) divergent(s) "
          f"sur {mt['sorties_bi_themes']} sorties bi-thèmes")
    d = rapport["debit"]
    print(f"\n  Débit inférence seule : {d['verbatims_par_seconde']} verbatims/s -> "
          f"{d['extrapolation_heures_pour_cible']} h pour {d['volume_cible']}")
    print(f"  Chaîne complète       : anonymisation {d['duree_anonymisation_s']}s "
          f"({d['part_anonymisation']*100:.0f} % du temps) + nettoyage "
          f"{d['duree_nettoyage_s']}s + inférence {d['duree_inference_s']}s "
          f"-> {d['extrapolation_heures_chaine_complete']} h pour {d['volume_cible']}")
    print(f"\n  Taux de revue : " + " · ".join(
        f"{s} -> {v*100:.1f} %" for s, v in rapport["confiance"]["taux_de_revue_par_seuil"].items()))
    print(f"\n  => {chemin.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
