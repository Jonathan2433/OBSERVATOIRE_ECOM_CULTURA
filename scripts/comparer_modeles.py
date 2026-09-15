#!/usr/bin/env python3
"""Comparaison ancien / nouveau modèle sur le jeu de recette gelé — lot L9.

Rapproche `baseline_modele_actuel.json` (modèle actif) et `eval_cultura_2026.json`
(modèle réentraîné). **Les deux mesures portent sur le même jeu de test gelé et
sont produites par les mêmes fonctions** : c'est la condition pour que l'écart
veuille dire quelque chose.

Ce qui est comparable et ce qui ne l'est pas
--------------------------------------------
* **Comparable** : le sentiment (mêmes 3 classes), la distribution du nombre de
  thèmes, la recopie du sentiment, le taux de revue, le débit.
* **Non comparable** : tout ce qui est thématique. Les référentiels partagent
  1 libellé de niveau 1 sur 20/11 et **0** sur 67/59 (D-36). Les métriques
  thématiques du nouveau modèle sont donc présentées **en valeur absolue**,
  sans « avant ».

Usage :
    python scripts/comparer_modeles.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]


def _lire(chemin: Path) -> Optional[Dict[str, Any]]:
    if not chemin.is_file():
        print(f"  absent : {chemin.relative_to(ROOT)}")
        return None
    return json.loads(chemin.read_text(encoding="utf-8"))


def _ligne(libelle: str, avant: Any, apres: Any, sens: str = "haut") -> str:
    """Formate une ligne de comparaison. `sens` = direction souhaitable."""
    def fmt(v):
        if v is None:
            return "     –"
        return f"{v:6.4f}" if isinstance(v, float) else f"{v:>6}"

    verdict = ""
    if isinstance(avant, (int, float)) and isinstance(apres, (int, float)):
        delta = apres - avant
        mieux = delta > 0 if sens == "haut" else delta < 0
        signe = "+" if delta >= 0 else "−"
        verdict = f"  {signe}{abs(delta):.4f}  {'✅' if mieux else '❌'}"
    return f"  {libelle:44s} {fmt(avant)}  ->  {fmt(apres)}{verdict}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--avant", default="data/processed/baseline_modele_actuel.json")
    ap.add_argument("--apres", default="data/processed/eval_cultura_2026.json")
    ap.add_argument("--sortie", default="data/processed/comparaison_ancien_nouveau.json")
    args = ap.parse_args()

    av = _lire(ROOT / args.avant)
    ap_ = _lire(ROOT / args.apres)
    if av is None or ap_ is None:
        print("\nComparaison impossible : les deux mesures doivent exister.")
        return 1

    if av["protocole"]["n_verbatims"] != ap_["protocole"]["n_verbatims"]:
        print(f"\n⚠️  Les deux mesures ne portent pas sur le même nombre de verbatims "
              f"({av['protocole']['n_verbatims']} vs {ap_['protocole']['n_verbatims']}) : "
              f"vérifier que le jeu de recette gelé a bien été utilisé des deux côtés.")

    print("=" * 86)
    print("  COMPARAISON ANCIEN / NOUVEAU — jeu de recette gelé "
          f"({ap_['protocole']['n_verbatims']} verbatims)")
    print("=" * 86)

    ga, gn = av["sentiment"]["global"], ap_["sentiment"]["global"]
    nt = av.get("non_trivialite_sentiment", {})
    print("\n▸ Sentiment — la seule tâche comparable entre les deux référentiels")
    print(_ligne("accuracy", ga["accuracy"], gn["accuracy"]))
    print(_ligne("F1-macro", ga["f1_macro"], gn["f1_macro"]))
    for lab in ("Négatif", "Neutre", "Positif"):
        print(_ligne(f"F1 {lab}", ga["f1_par_classe"].get(lab), gn["f1_par_classe"].get(lab)))

    print("\n▸ EF-3 — planchers de la règle `note → sentiment` (D-38, cumulatif)")
    pa, pf = nt.get("accuracy_regle"), nt.get("f1_macro_regle")
    for nom, plancher, obtenu in (("accuracy", pa, gn["accuracy"]),
                                  ("F1-macro", pf, gn["f1_macro"])):
        if plancher is None or obtenu is None:
            continue
        ok = obtenu > plancher
        print(f"  {nom:44s} plancher {plancher:.4f}  modèle {obtenu:.4f}  "
              f"{'✅ dépassé' if ok else '❌ NON dépassé'}")
    verdict_ef3 = (gn["accuracy"] > (pa or 1) and gn["f1_macro"] > (pf or 1))
    print(f"  {'EF-3 (les deux grandeurs)':44s} "
          f"{'✅ SATISFAITE' if verdict_ef3 else '❌ NON SATISFAITE'}")

    print("\n▸ Grief n°1 — comportement multi-thème")
    ma = av["multi_theme"]
    dn = ap_["niv1"]["distribution_nb_themes"]
    print(_ligne("part de sorties bi-thèmes", ma["part_bi_theme_predite"],
                 dn["part_bi_theme"], sens="bas"))
    print(f"  {'(référence : part annotée bi-thèmes)':44s} "
          f"{ma['part_bi_theme_annotee']:6.4f}")
    print(_ligne("thèmes par verbatim", ma["moyenne_themes_par_verbatim"],
                 dn["moyenne_themes_par_verbatim"], sens="bas"))
    st = ap_["niv1"]["second_theme"]
    print(f"\n  Second thème (nouveau modèle, absent de la baseline — D-36) :")
    # La cible ≥ 0,70 est une proposition eXalt jamais validée (Q-9), mesurée sur
    # 35 verbatims bi-thèmes. Son remplacement est proposé au PO
    # (docs/OPTIMISATION_SANS_CULTURA.md §4) ; tant qu'il n'a pas tranché, elle
    # reste affichée — mais avec son statut, jamais comme un engagement.
    print(f"     précision            {st['precision_second_theme']}   "
          f"cible ≥ 0,70 — proposition eXalt NON VALIDÉE (Q-9), suivi seulement")
    print(f"     taux de faux 2e      {st['taux_faux_second_theme']}   cible ≤ 0,15 (à valider)")
    print(f"     rappel               {st['rappel_second_theme']}   "
          f"(n bi-thèmes annotés = {st['verbatims_bi_themes_annotes']})")

    print("\n▸ Famille A — en valeur absolue, faute de baseline thématique (D-36)")
    n1 = ap_["niv1"]
    print(f"  {'F1-macro niveau 1':44s} {n1['f1_macro']:.4f}")
    print(f"  {'F1-micro niveau 1 (après plafond)':44s} {n1['f1_micro']:.4f}")
    print(f"  {'précision micro / rappel micro':44s} "
          f"{n1['precision_micro']:.4f} / {n1['recall_micro']:.4f}")
    h = ap_.get("hierarchie", {})
    print(f"  {'P(niv1 correct)':44s} {h.get('p_niv1_correct')}")
    print(f"  {'P(couple niv1+niv2 correct)':44s} {h.get('p_couple_correct')}")

    print("\n▸ Exploitation")
    da, dn_ = av["debit"]["verbatims_par_seconde"], ap_["debit"]["verbatims_par_seconde"]
    ecart = (dn_ - da) / max(da, 1e-9)
    print(f"  {'débit (verbatims/s)':44s} {da:6.2f}  ->  {dn_:6.2f}"
          f"  {ecart*100:+.1f} %  {'≈ inchangé' if abs(ecart) < 0.05 else ''}")

    # Le taux de revue ne s'apprécie pas par sa direction mais par rapport à la
    # cible D-9 (10 à 15 %) : trop bas, le métier ne relit pas assez ; trop haut,
    # il relit tout. Ce n'est donc ni un « mieux » ni un « moins bien ».
    print(f"\n  Taux de revue humaine — cible D-9 : 10 à 15 %")
    ra = av["confiance"]["taux_de_revue_par_seuil"]
    rn = ap_["confiance"]["taux_de_revue_par_seuil"]
    for seuil in sorted(set(ra) | set(rn)):
        va, vn = ra.get(seuil), rn.get(seuil)
        def _q(v):
            if v is None:
                return "    –"
            dans = 0.10 <= v <= 0.15
            return f"{v*100:5.1f} %{' ✅' if dans else '   '}"
        print(f"  {'seuil ' + seuil:44s} {_q(va)}  ->  {_q(vn)}")
    dans_cible = [s for s in rn if rn[s] is not None and 0.10 <= rn[s] <= 0.15]
    print(f"  {'seuil atteignant la cible (nouveau modèle)':44s} "
          f"{dans_cible if dans_cible else 'AUCUN parmi ceux testés — calibration L7 requise'}")

    d40 = ap_.get("d40_routage_hors_perimetre", {})
    print(f"\n▸ D-40 — sous-thèmes hors périmètre routés en revue")
    print(f"  {'verbatims à niv2 vide':44s} {d40.get('verbatims_niv2_vide')} "
          f"({(d40.get('part') or 0)*100:.1f} %) · tous en revue = {d40.get('tous_en_revue')}")

    resume = {
        "jeu": ap_["protocole"],
        "sentiment": {"avant": ga, "apres": gn},
        "ef3": {"plancher_accuracy": pa, "plancher_f1_macro": pf,
                "satisfaite": bool(verdict_ef3)},
        "multi_theme": {"avant": ma, "apres": dn, "second_theme": st},
        "famille_a_absolue": {k: n1[k] for k in
                              ("f1_macro", "f1_micro", "precision_micro", "recall_micro")},
        "hierarchie": h,
        "non_comparable": ("métriques thématiques : 1 libellé niv.1 commun sur 20/11, "
                           "0 sur 67/59 en niv.2 (D-36)"),
    }
    chemin = ROOT / args.sortie
    chemin.write_text(json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  => {chemin.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
