#!/usr/bin/env python3
"""Recette automatisée L1a — chargeur Cultura 2026.

Reprend, un par un, les tests d'acceptation de `docs/SPEC_CHARGEUR.md` §11.
Tourne **hors ligne**, sans torch : seuls pandas, openpyxl, pyyaml et (pour le
contrôle d'anonymisation) spaCy sont requis.

Usage :
    python app/tests/recette_l1a_chargeur.py        # depuis la racine du dépôt

Code de sortie : 0 si aucun ÉCHEC, 1 sinon. Les SKIP ne sont pas des échecs.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Tuple

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
for p in (str(ROOT),):
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd  # noqa: E402

from src.preprocessing.anonymizer import (  # noqa: E402
    AnonymisationIndisponibleError,
    Anonymizer,
    verifier_ner_disponible,
)
from src.preprocessing.column_norm import (  # noqa: E402
    ColumnCollisionError,
    assert_no_collision,
    normalize_column_name,
)
from src.preprocessing.cultura_loader import (  # noqa: E402
    ChargeurError,
    ColonneManquanteError,
    SchemaInconnuError,
    charger_cultura,
    read_table,
)
from src.utils.config import load_config  # noqa: E402

_RESULTS: List[Tuple[str, str, str]] = []


def section(label: str) -> None:
    _RESULTS.append(("--", label, ""))


def check(cond: bool, label: str, detail: str = "") -> bool:
    _RESULTS.append(("OK" if cond else "ÉCHEC", label, detail))
    return cond


def skip(label: str, detail: str = "") -> None:
    _RESULTS.append(("SKIP", label, detail))


# --------------------------------------------------------------------------- #
def main() -> int:
    cfg = load_config()
    cs = cfg["cultura_sources"]
    racine = ROOT / cs["data_dir"]

    if not racine.is_dir():
        print(f"Livraison Cultura introuvable : {racine}")
        return 1

    # ---------------------------------------------------------------- #
    section("Anonymisation (§10) — contrôlée avant tout chargement")
    # ---------------------------------------------------------------- #
    anon = Anonymizer(cfg)
    masque, cpt = anon.anonymize("ma commande P12345678 est perdue")
    check(cpt["ORDER_ID"] >= 1 and "P12345678" not in masque,
          "`P########` est effectivement masqué",
          f"obtenu : {masque!r}")

    masque, cpt = anon.anonymize("contactez ******@free.fr")
    check(cpt["EMAIL"] >= 1 and "free.fr" not in masque,
          "e-mail partiellement masqué par Cultura (`******@free.fr`) masqué",
          f"obtenu : {masque!r}")

    cfg_ko = load_config()
    cfg_ko["anonymization"]["spacy_model"] = "modele_inexistant_xx"
    try:
        verifier_ner_disponible(cfg_ko)
        check(False, "spaCy absent → échec explicite", "aucune exception levée")
    except AnonymisationIndisponibleError:
        check(True, "spaCy absent → échec explicite, pas de mode dégradé silencieux")

    spacy_present = True
    try:
        verifier_ner_disponible(cfg)
    except AnonymisationIndisponibleError:
        spacy_present = False

    if not spacy_present:
        skip("Chargement de la livraison réelle",
             "spaCy indisponible — installer `fr_core_news_sm`")
        return _bilan()

    # ---------------------------------------------------------------- #
    section("Normalisation des colonnes (§4) — les deux pièges mesurés")
    # ---------------------------------------------------------------- #
    check(normalize_column_name("Avez-vous une remarque ou des idées à nous partager ?\x0b")
          == normalize_column_name("Avez-vous une remarque ou des idées à nous partager ??"),
          "les libellés Mopinion mobile divergents convergent (`\\x0b` neutralisé)")

    check(normalize_column_name("Dites-nous en plus :")
          != normalize_column_name("Dites nous en plus :"),
          "`Dites-nous en plus :` et `Dites nous en plus :` restent distincts")

    try:
        assert_no_collision(["Dites-nous en plus :", "Dites-nous en plus :"], "test")
        check(False, "deux colonnes fusionnées → échec explicite", "aucune exception")
    except ColumnCollisionError:
        check(True, "deux colonnes fusionnées → échec explicite")

    # ---------------------------------------------------------------- #
    section("Chargement de la livraison réelle du 09/09 (D-29)")
    # ---------------------------------------------------------------- #
    df, rap = charger_cultura(cfg)

    check(rap["fichiers_lus"] == 9, "les 9 fichiers réels sont lus",
          f"lus : {rap['fichiers_lus']}")
    check(rap["lignes_lues"] == 26826, "26 826 lignes lues (audit §3)",
          f"lues : {rap['lignes_lues']}")

    schemas_attendus = {"MDTC-postachat": 4, "MDTC-postrecep": 2,
                        "Mopinion-desktop": 1, "Mopinion-mobile": 2}
    obtenus: dict = {}
    for d in rap["details_par_fichier"]:
        obtenus[d["schema"]] = obtenus.get(d["schema"], 0) + 1
    check(obtenus == schemas_attendus, "schéma correctement reconnu pour chaque fichier",
          f"obtenu : {obtenus}")

    mobile = [d for d in rap["details_par_fichier"] if d["schema"] == "Mopinion-mobile"]
    check(len(mobile) == 2 and all(d["verbatims_produits"] > 0 for d in mobile),
          "les deux exports Mopinion mobile sont lus malgré leurs libellés divergents",
          f"{[(d['fichier'], d['verbatims_produits']) for d in mobile]}")

    # ---------------------------------------------------------------- #
    section("Volumétrie (§11) et réconciliation")
    # ---------------------------------------------------------------- #
    rec = rap["reconciliation_spec_11"]
    check(rec["total_si_regle_1_non_appliquee"] == 7552,
          "7 501 verbatims + 51 textes non classables = 7 552 (§11)",
          f"{rec['verbatims_produits']} + {rec['textes_non_classables_ecartes']} "
          f"= {rec['total_si_regle_1_non_appliquee']}")

    attendu_schema = {"MDTC-postachat": 1928, "MDTC-postrecep": 3869,
                      "Mopinion-desktop": 537, "Mopinion-mobile": 1218}
    ecarts = []
    for nom, cible in attendu_schema.items():
        produit = rap["verbatims_par_schema"].get(nom, 0)
        # La règle 1 de §5.2 (ponctuation seule) retire des verbatims que le
        # total de §11 comptait : on contrôle donc la borne, pas l'égalité.
        if not (cible - 60 <= produit <= cible):
            ecarts.append(f"{nom}: {produit} vs {cible}")
    check(not ecarts, "volumétrie par source conforme à §11 (règle 1 appliquée)",
          "; ".join(ecarts))

    # ---------------------------------------------------------------- #
    section("Composition du verbatim (§5, D-30)")
    # ---------------------------------------------------------------- #
    postachat = df[df["__source__"] == "MDTC-postachat"]
    concatenes = postachat[postachat["__field__"].str.contains(r"\+", regex=True, na=False)]
    check(len(concatenes) > 0,
          "MDTC post-achat : Justification et Suggestion concaténées",
          f"{len(concatenes)} verbatims concaténés")

    exemple = concatenes["__text_raw__"].head(50).tolist()
    check(any(". " in t for t in exemple),
          "la concaténation utilise bien le séparateur `\". \"`")

    check("__produit_non_trouve__" in df.columns,
          "`Produits non trouvés` conservé en colonne de contexte")
    non_vides = int((df["__produit_non_trouve__"].fillna("").str.strip() != "").sum())
    check(not df["__field__"].str.contains("produits non trouvés", na=False).any(),
          "`Produits non trouvés` ne produit aucun verbatim (D-30)",
          f"{non_vides} valeurs rattachées à un verbatim")
    ctx = rap.get("champs_contexte", {}).get("__produit_non_trouve__", {})
    check(ctx.get("vus") == 104,
          "les 104 valeurs de `Produits non trouvés` sont vues et journalisées",
          f"vues : {ctx.get('vus')} · rattachées : {ctx.get('rattaches_a_un_verbatim')} "
          f"(l'écart = répondants n'ayant rempli que ce champ)")

    # ---------------------------------------------------------------- #
    section("Normalisation des labels (§8)")
    # ---------------------------------------------------------------- #
    syn = rap["synonymes_appliques"]
    attente = sum(v for k, v in syn.items() if "Attente commande" in k)
    themes_attente = set(df["theme1_niv1"].dropna()) | set(df["theme2_niv1"].dropna())
    check("Attente commande" not in themes_attente,
          "les deux graphies « Attente comm(m)ande » sont rattachées au canonique",
          f"{attente} occurrences normalisées ; graphies en sortie : "
          f"{sorted(t for t in themes_attente if 'ttente' in t)}")

    signaux = set(df["signal"].dropna())
    check(signaux <= {"insatisfaction", "churn", "rupture"},
          "les signaux produisent une seule valeur canonique par famille (§8.3)",
          f"valeurs : {sorted(signaux)}")
    fusion = sum(v for k, v in syn.items() if "Insatisfait" in k)
    check(fusion == 368,
          "les 368 « Insatisfait » sont fusionnés avec les 519 « Insatisfaction »",
          f"fusionnés : {fusion}")

    couples_t1 = sum(v for k, v in rap["couples_invalides"].items() if k.startswith("theme1"))
    check(len(rap["couples_invalides"]) > 0 and couples_t1 >= 16,
          "les couples (thème, sous-thème) invalides sont journalisés, non corrigés",
          f"thème 1 : {couples_t1} · total : {sum(rap['couples_invalides'].values())}")

    hp_t1 = sum(v for k, v in rap["sous_themes_hors_perimetre"].items() if k.startswith("theme1"))
    check(hp_t1 == 58, "58 lignes hors périmètre sur le thème 1 (D-32, §8.5)",
          f"obtenu : {hp_t1}")

    # ---------------------------------------------------------------- #
    section("Périmètre d'ingestion (D-18) — aucune PII ne doit passer")
    # ---------------------------------------------------------------- #
    interdites = [
        "user agent", "contentsquare session recording", "selected screenshot html",
        "viewport", "browser", "os", "form trigger", "form completion percentage",
        "page title", "ending element", "tags", "survey",
        "website data:tc_vars. page_cat1_name",
        "pour identifier les problèmes, votre adresse email pourrait grandement "
        "nous aider ?? vous pouvez également laisser cet emplacement vide",
        "une image vaut mille mots ! partagez-nous une capture de votre écran :",
    ]
    presentes = [c for c in df.columns if normalize_column_name(c) in set(interdites)]
    check(not presentes, "aucune colonne écartée par D-18 n'apparaît en sortie",
          f"colonnes fautives : {presentes}")

    attendues = {
        "__source__", "__fichier__", "__respondent_id__", "__field__", "__text_raw__",
        "__satisfaction__", "__satisfaction_raw__", "__date__", "__page_type__",
        "__url__", "__device__", "theme1_niv1", "theme1_niv2", "theme2_niv1",
        "theme2_niv2", "sentiment", "signal", "__anomalies__", "__produit_non_trouve__",
    }
    check(set(df.columns) == attendues,
          "la sortie ne contient QUE les colonnes déclarées (liste blanche)",
          f"inattendues : {sorted(set(df.columns) - attendues)}")

    # ---------------------------------------------------------------- #
    section("Échecs de structure (§9.1)")
    # ---------------------------------------------------------------- #
    tmp = Path(tempfile.mkdtemp(prefix="recette_l1a_"))
    src = racine / "mdtc_postachat" / "PostachatW32-TRANSMIS.csv"
    brut, enc = read_table(src, cs["encodages"], cs["separateur_csv"])

    # On retire une colonne requise mais ABSENTE de la signature (`Sentiment`),
    # afin d'exercer réellement le contrôle de colonnes attendues : retirer une
    # colonne de signature ferait échouer plus tôt, à la détection de schéma.
    ampute = brut.drop(columns=[c for c in brut.columns
                                if str(c).strip().lower() == "sentiment"])
    (tmp / "ampute").mkdir(parents=True, exist_ok=True)
    ampute.to_csv(tmp / "ampute" / "ampute.csv", sep=";", index=False, encoding="utf-8-sig")
    try:
        charger_cultura(cfg, data_dir=tmp / "ampute")
        check(False, "colonne attendue absente → échec explicite", "aucune exception")
    except ColonneManquanteError as exc:
        check(True, "colonne attendue absente → échec explicite",
              type(exc).__name__)
    except SchemaInconnuError as exc:
        check(False, "colonne attendue absente → échec explicite",
              f"échec à la détection de schéma, pas au contrôle de colonnes : {exc}")

    (tmp / "inconnu").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"colonne_a": ["x"], "colonne_b": ["y"]}).to_csv(
        tmp / "inconnu" / "cinquieme_schema.csv", sep=";", index=False, encoding="utf-8-sig")
    try:
        charger_cultura(cfg, data_dir=tmp / "inconnu")
        check(False, "cinquième schéma → échec explicite", "aucune exception")
    except (SchemaInconnuError, ChargeurError) as exc:
        check(True, "cinquième schéma → échec explicite", type(exc).__name__)

    # ---------------------------------------------------------------- #
    section("Rapport de chargement (§9.3)")
    # ---------------------------------------------------------------- #
    chemin_rapport = ROOT / "data" / "processed" / "rapport_chargement_l1a.json"
    check(chemin_rapport.is_file(), "le rapport de chargement est produit",
          str(chemin_rapport.relative_to(ROOT)))
    if chemin_rapport.is_file():
        contenu = json.loads(chemin_rapport.read_text(encoding="utf-8"))
        obligatoires = {"fichiers_lus", "lignes_lues", "verbatims_produits",
                        "anomalies_par_annotation", "synonymes_appliques",
                        "details_par_fichier", "candidats_synonymes"}
        check(obligatoires <= set(contenu),
              "le rapport porte fichiers, schémas, décomptes, anomalies et synonymes",
              f"manquant : {sorted(obligatoires - set(contenu))}")

    audit = {"SENTIMENT_ABSENT": 572, "ANNOTATION_RECOPIEE": 6, "SIGNAL_INCONNU": 0}
    ecarts = [f"{k}: {rap['anomalies_par_annotation'].get(k, 0)} vs {v}"
              for k, v in audit.items() if rap["anomalies_par_annotation"].get(k, 0) != v]
    check(not ecarts, "les décomptes d'anomalies correspondent à l'audit du 09/09",
          "; ".join(ecarts))

    # ---------------------------------------------------------------- #
    # ---------------------------------------------------------------- #
    section("Exports de production (CSV et XLSX) — ingestion sans annotation")
    # ---------------------------------------------------------------- #
    # Un export mensuel vient chercher une prédiction : il n'a ni thème ni
    # sentiment. Le chargeur doit l'accepter par le MÊME chemin que la livraison
    # annotée — même détection de schéma, même liste blanche, même composition.
    from src.preprocessing.loader import (  # noqa: E402
        COL_SATISFACTION, COL_SOURCE, COL_TEXT,
        detecter_schema_2026, load_cultura_2026,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # --- CSV, satisfaction en toutes lettres, colonne PII en prime --------
        csv = tmp / "export_mdtc.csv"
        csv.write_text(
            "Date d'achat;Date de réponse;Satisfaction;Recommandation;"
            "Justification niveau de satisfaction;Produits non trouvés;"
            "Suggestion d'amélioration;Commande\n"
            "2026-09-12;2026-09-14;Très satisfait(e);10;"
            "Livraison rapide et soignée, très bonne expérience;;Rien à redire;P90000001\n"
            "2026-09-12;2026-09-14;Pas du tout satisfait(e);0;"
            "Commande jamais reçue et personne ne répond au service client;;;P90000002\n",
            encoding="utf-8-sig")

        schema = detecter_schema_2026(csv, cfg)
        check(schema == "MDTC-postachat",
              "un export CSV de production est reconnu sur son jeu de colonnes",
              f"schéma détecté : {schema}")

        df = load_cultura_2026(csv, cfg)
        check(len(df) == 2, "le CSV produit bien ses verbatims", f"{len(df)} ligne(s)")
        check(list(df[COL_SOURCE].unique()) == ["MDTC-postachat"],
              "la source FINE est produite, pas seulement « MDTC »",
              str(list(df[COL_SOURCE].unique())))
        notes = sorted(x for x in df[COL_SATISFACTION] if x is not None)
        check(notes == [1, 4],
              "la satisfaction TEXTUELLE est convertie sur l'échelle 1-4",
              f"notes obtenues : {notes}")

        # D-18 : le numéro de commande ne doit apparaître NULLE PART en sortie.
        tout = " ".join(str(v) for v in df.to_dict("list").values())
        check("P90000001" not in tout and "P90000002" not in tout,
              "le numéro de commande n'atteint aucune colonne de sortie (D-18)",
              "liste blanche : seules les colonnes déclarées sont conservées")
        check("commande" not in [c.lower() for c in df.columns],
              "aucune colonne « Commande » dans la sortie",
              str(list(df.columns)))

        # --- XLSX au même format : même chemin, même résultat -----------------
        xlsx = tmp / "export_mdtc.xlsx"
        pd.read_csv(csv, sep=";", dtype=str, encoding="utf-8-sig").to_excel(xlsx, index=False)
        df_x = load_cultura_2026(xlsx, cfg)
        check(len(df_x) == len(df) and list(df_x[COL_SOURCE]) == list(df[COL_SOURCE]),
              "le même contenu en XLSX donne le même résultat qu'en CSV",
              f"csv {len(df)} · xlsx {len(df_x)}")

        # --- Un format inconnu ne doit PAS être capté par ce chemin -----------
        autre = tmp / "autre.csv"
        autre.write_text("colonne A;colonne B\n1;2\n", encoding="utf-8")
        check(detecter_schema_2026(autre, cfg) is None,
              "un fichier hors format Cultura 2026 n'est pas capté (repli V1)",
              "la détection renvoie None sans lever")

        # --- Le format historique reste prioritairement traité par le V1 ------
        v1 = tmp / "mdtc_v1.xlsx"
        pd.DataFrame({"Niveau de satisfaction général": [2],
                      "Verbatim justification": ["Colis abîmé à la livraison"],
                      "Date de commande": ["2026-09-01"]}).to_excel(v1, index=False)
        check(detecter_schema_2026(v1, cfg) is None,
              "un export au format POC V1 n'est pas confondu avec le format 2026")

    # ---------------------------------------------------------------- #
    section("Jeu factice (D-22) et non-régression applicative")
    # ---------------------------------------------------------------- #
    fake = ROOT / "data" / "raw" / "fake"
    if not fake.is_dir():
        skip("le jeu factice est lu par le même chargeur", "data/raw/fake absent")
    else:
        try:
            charger_cultura(cfg, data_dir=fake)
            check(True, "le jeu factice est lu par le même chargeur")
        except ChargeurError as exc:
            check(False, "le jeu factice est lu par le même chargeur",
                  f"{type(exc).__name__} — jeu factice construit sur les maquettes "
                  f"du 12/08, à régénérer sur les schémas réels")

    skip("recettes V1, V3, V4, V5, V6 au vert",
         "nécessitent l'environnement applicatif (base, API) — à rejouer en L9")

    return _bilan()


def _bilan() -> int:
    print("=" * 78)
    print("  RECETTE L1a — chargeur Cultura 2026 (docs/SPEC_CHARGEUR.md §11)")
    print("=" * 78)
    fails = oks = skips = 0
    for status, label, detail in _RESULTS:
        if status == "--":
            print(f"\n▸ {label}")
            continue
        icon = {"OK": "✅", "ÉCHEC": "❌", "SKIP": "⏭️ "}[status]
        line = f"  {icon} {label}"
        if detail and status in ("ÉCHEC", "SKIP"):
            line += f"  →  {detail}"
        elif detail:
            line += f"  ({detail})"
        print(line)
        oks += status == "OK"
        fails += status == "ÉCHEC"
        skips += status == "SKIP"
    print("\n" + "-" * 78)
    print(f"  Bilan : {oks} OK · {fails} ÉCHEC · {skips} SKIP")
    print("-" * 78)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
