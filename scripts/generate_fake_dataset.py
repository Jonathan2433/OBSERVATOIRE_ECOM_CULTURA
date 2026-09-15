#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Génère le jeu de données factice de démonstration.

Implémente ``docs/SPEC_JEU_FACTICE.md``. Produit dans ``data/raw/fake/`` :

  - ``fake_labeled.xlsx``          jeu labellisé (entraînement + évaluation)
  - ``fake_MDTC-postachat-web.xlsx``   \\
  - ``fake_MDTC-postrecep-web.xlsx``    | fichiers d'entrée aux 4 formats exacts
  - ``fake_mopinion_desktop.xlsx``      | des maquettes reçues le 12/08/2026
  - ``fake_mopinion_mobilev2.xlsx``    /
  - ``fake_dataset_traps.json``    manifeste des cas pièges
  - ``fake_dataset_report.json``   contrôle des 8 invariants + statistiques

La génération **échoue** si un seul invariant n'est pas satisfait (SPEC §2).

ARTEFACT DE TEST — ne fait partie ni de la chaîne d'entraînement,
ni de la chaîne de production. Aucun fichier existant n'est modifié.

Usage :
    python scripts/generate_fake_dataset.py
    python scripts/generate_fake_dataset.py --taxonomy data/raw/taxo_cultura_v2.json -n 1500
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fake_textgen as tg  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
SENTIMENTS = ["Négatif", "Neutre", "Positif"]

# --------------------------------------------------------------------------- #
#  Schémas exacts des 4 maquettes reçues le 12/08/2026
# --------------------------------------------------------------------------- #
COLS_MDTC_ACHAT = ["Date d'achat", "Date de réponse", "Niveau de satisfaction", "score RECO",
                   "Justification du niveau de satisfaction", "Produits non trouvé",
                   "Suggestions d'amélioration", "Commande", "Ancienneté client"]
LIBRES_MDTC_ACHAT = ["Justification du niveau de satisfaction", "Produits non trouvé",
                     "Suggestions d'amélioration"]

COLS_MDTC_RECEP = ["Date d'achat", "Date de réponse", "Niveau de satisfaction", "score RECO",
                   "Justification du niveau de satisfaction", "Commande", "Ancienneté client"]
LIBRES_MDTC_RECEP = ["Justification du niveau de satisfaction"]

COLS_MOPI_DESK = [
    "id", "survey", "tags", "Quel problème avez-vous rencontré ?",
    "Quel est votre degré de satisfaction concernant Cultura ? ",
    "Une image vaut mille mots ! Partagez-nous une capture de votre écran :",
    "Selected screenshot HTML", "User Agent", "url", "Page title", "Viewport",
    "Form trigger", "Form completion percentage", "Datetime",
    "Pour identifier les problèmes, votre adresse email pourrait grandement nous aider 🙏 "
    "Vous pouvez également laisser cet emplacement vide.",
    "OS", "Browser", "Device", "Website data:window.tc_vars.page_type",
    "Contentsquare session recording",
    "Merci ! Avez vous tout de même une remarque ou un message pour nos équipes ?",
    "Décrivez nous votre problème ", "Quel est le problème que vous rencontrez ?",
    "Sur quel sujet porte votre question ?", "Website data:tc_vars. page_cat1_name"]
LIBRES_MOPI_DESK = ["Merci ! Avez vous tout de même une remarque ou un message pour nos équipes ?",
                    "Décrivez nous votre problème "]

COLS_MOPI_MOB = [
    "id", "survey", "tags", "Datetime", "User Agent", "url", "Page title",
    "Quel est votre degré de satisfaction concernant le site de Cultura ?",
    "Aidez-nous à améliorer l'expérience sur le site. Qu'est ce qui vous pose problème ?",
    "Avez-vous une remarque ou des idées à nous partager ? ",
    "Website data:window.tc_vars.page_type", "Ce n’est pas cela ? Décrivez-nous le problème. ",
    "Dites-nous en plus :", "Dites nous en plus :", "Viewport", "Form trigger",
    "Form completion percentage", "Contentsquare session recording", "Ending element",
    "OS", "Browser", "Device", "Décrivez-nous le problème. ",
    "Concernant votre commande déjà passée, quel est votre besoin ?",
    "Dites-nous en plus sur votre problème. "]
LIBRES_MOPI_MOB = ["Avez-vous une remarque ou des idées à nous partager ? ",
                   "Ce n’est pas cela ? Décrivez-nous le problème. ",
                   "Décrivez-nous le problème. ", "Dites-nous en plus sur votre problème. "]

SOURCES = {
    "MDTC-postachat":  {"fichier": "fake_MDTC-postachat-web.xlsx", "sheet": "myWorkSheet",
                        "cols": COLS_MDTC_ACHAT, "libres": LIBRES_MDTC_ACHAT, "part": 0.28},
    "MDTC-postrecep":  {"fichier": "fake_MDTC-postrecep-web.xlsx", "sheet": "myWorkSheet",
                        "cols": COLS_MDTC_RECEP, "libres": LIBRES_MDTC_RECEP, "part": 0.24},
    "Mopinion-desktop": {"fichier": "fake_mopinion_desktop.xlsx", "sheet": "Sheet1",
                         "cols": COLS_MOPI_DESK, "libres": LIBRES_MOPI_DESK, "part": 0.27},
    "Mopinion-mobile": {"fichier": "fake_mopinion_mobilev2.xlsx", "sheet": "Sheet1",
                        "cols": COLS_MOPI_MOB, "libres": LIBRES_MOPI_MOB, "part": 0.21},
}

# Échelles de satisfaction — trois échelles hétérogènes (cf. cadrage D-20).
SATIS_MDTC = ["Pas du tout satisfait€", "Plutôt pas satisfait(e)",
              "Plutôt satisfait(e)", "Très satisfait(e)"]           # 4 modalités, 1..4
PAGE_TYPES = ["account-page", "checkout-page", "cms-page", "product-page", "category-page",
              "search-page", "cart-page", "home-page", "order-page"]
DEVICES_DESK = ["Desktop"]
DEVICES_MOB = ["Mobile", "Tablet", "Desktop"]


# --------------------------------------------------------------------------- #
#  Taxonomie
# --------------------------------------------------------------------------- #
def charger_taxonomie(chemin: Path) -> list:
    """Charge la taxonomie. Tolère un libellé niv.2 partagé entre plusieurs parents
    (cas confirmé par Cultura, réponse B2) : c'est précisément ce que le jeu doit tester."""
    data = json.loads(chemin.read_text(encoding="utf-8"))
    couples = []
    for theme in data["themes"]:
        for n2 in theme["niv2"]:
            couples.append((theme["niv1"], n2))
    return couples


def poids_puissance(n: int, rng, exposant: float = 1.15) -> list:
    """Distribution en loi de puissance (SPEC §3, invariant I-5).

    Le prototype était quasi uniforme, ce qui n'arrive jamais en production
    et masque le comportement sur les classes rares.
    """
    ordre = list(range(n))
    rng.shuffle(ordre)
    brut = [1.0 / ((rang + 1) ** exposant) for rang in range(n)]
    poids = [0.0] * n
    for rang, idx in enumerate(ordre):
        poids[idx] = brut[rang]
    total = sum(poids)
    return [p / total for p in poids]


# --------------------------------------------------------------------------- #
#  Satisfaction — I-3 : le sentiment ne doit PAS être déductible de la note
# --------------------------------------------------------------------------- #
def note_pour(sentiment: str, rng, discordant: bool) -> int:
    """Note sur 10, cohérente avec le sentiment sauf si ``discordant``.

    Dans le prototype, note -> sentiment était exact sur 7 000 lignes sans une
    seule exception : un modèle entraîné là-dessus n'apprend rien du texte.
    """
    plages = {"Négatif": (1, 4), "Neutre": (5, 7), "Positif": (8, 10)}
    if not discordant:
        return rng.randint(*plages[sentiment])
    autres = [s for s in SENTIMENTS if s != sentiment]
    return rng.randint(*plages[rng.choice(autres)])


def satisfaction_source(source: str, note10: int, rng):
    """Convertit une note /10 dans l'échelle native de la source."""
    if source.startswith("MDTC"):
        idx = min(3, max(0, (note10 - 1) * 4 // 10))
        return SATIS_MDTC[idx], max(0, min(10, note10 + rng.randint(-1, 1)))  # + score RECO
    return float(min(5, max(1, round(note10 / 2)))), None


# --------------------------------------------------------------------------- #
#  Cas pièges (SPEC §5)
# --------------------------------------------------------------------------- #
def construire_pieges(couples, rng) -> list:
    """Retourne une liste de dicts : texte + métadonnées + comportement attendu."""
    pieges = []

    def ajouter(cat, texte, attendu, couple=None, sentiment="Négatif"):
        pieges.append({"categorie": cat, "texte": texte, "comportement_attendu": attendu,
                       "couple": couple or rng.choice(couples), "sentiment": sentiment})

    # -- Texte vide ou dégénéré ------------------------------------------------
    for txt in ["", "   ", "...", "a", "???", "  "]:
        ajouter("texte_vide", txt, "nb_themes = 0, revue_humaine_requise = true, aucune exception")

    # -- Longueur extrême ------------------------------------------------------
    for _ in range(6):
        c = rng.choice(couples)
        ajouter("tres_long", tg.composer([(c[0], c[1], "Négatif")], rng, longueur="long"),
                "traite sans erreur, troncature a 512 tokens sans casse de la sortie", c)
    for _ in range(6):
        c = rng.choice(couples)
        ajouter("tres_court", tg.composer([(c[0], c[1], "Négatif")], rng, longueur="court"),
                "traite ; verbatim sous le seuil min_tokens = 5, doit etre signale", c)

    # -- Casse et ponctuation --------------------------------------------------
    for _ in range(5):
        c = rng.choice(couples)
        base = tg.composer([(c[0], c[1], "Négatif")], rng, bruit=False)
        ajouter("majuscules", base.upper(),
                "classe normalement ; permet de mesurer l'effet de cleaning.lowercase", c)
    for _ in range(4):
        c = rng.choice(couples)
        base = tg.composer([(c[0], c[1], "Négatif")], rng, bruit=False)
        ajouter("ponctuation", base.replace(".", "!!!!!") + " ?????",
                "nettoyage effectif, pas d'exception", c)

    # -- Emojis et Unicode -----------------------------------------------------
    for emo in ["😡😡😡", "👍", "🤬 ", "😐"]:
        c = rng.choice(couples)
        base = tg.composer([(c[0], c[1], "Négatif")], rng, bruit=False)
        ajouter("emoji", emo + " " + base + " " + emo,
                "emojis supprimes par le cleaner, texte conserve", c)
    ajouter("emoji_seul", "😡😡😡", "aucun texte apres nettoyage -> nb_themes = 0 + revue")
    ajouter("unicode", "l é c h e c   d u   p a i e m e n t !",
            "normalisation NFKC effective, pas d'exception")

    # -- PII (SPEC §5) ---------------------------------------------------------
    pii = [
        ("email", "contactez moi sur jean.dupont@example.com le paiement a echoue",
         "[EMAIL] masque avant tout stockage"),
        ("email", "mon adresse est m.durand93@exemple.fr, aucune reponse recue",
         "[EMAIL] masque avant tout stockage"),
        ("telephone", "rappelez moi au 06 12 34 56 78, la commande n'arrive pas",
         "[TEL] masque avant tout stockage"),
        ("telephone", "mon numero 01.42.85.96.31 ne recoit rien du tout",
         "[TEL] masque avant tout stockage"),
        ("commande_P", "ma commande P12345678 est bloquee depuis 10 jours",
         "REGRESSION A VERIFIER : le format P######## n'a jamais ete rencontre "
         "par le regex ORDER_ID (0 masquage sur les 7 000 du prototype)"),
        ("commande_P", "aucune nouvelle de P87654321 ni de P11223344",
         "les deux numeros au format P######## doivent etre masques"),
        ("nom_propre", "monsieur Lefebvre en magasin a ete tres desagreable",
         "[NOM] masque par spaCy ; echec silencieux si spaCy absent"),
        ("marque_a_ne_pas_masquer", "j'ai commande un Ravensburger chez Cultura, colis perdu",
         "les noms de marque ne doivent PAS etre masques (stoplist)"),
    ]
    for cat, txt, attendu in pii:
        ajouter(cat, txt, attendu)

    # -- Hors sujet ------------------------------------------------------------
    hors = [
        ("hors_sujet", "il fait beau aujourd'hui et mon chat va bien",
         "confiance basse + revue ; le repli argmax retourne malgre tout un theme, "
         "comportement a documenter (pas de sortie 'non classable' cote CamemBERT)"),
        ("hors_sujet", "1234567890 0987654321 1111", "idem"),
        ("hors_sujet", "https://www.cultura.com/livre/livres-scolaires.html", "idem"),
        ("hors_sujet", "azerty qsdfgh wxcvbn", "idem"),
        ("spam", "GAGNEZ 1000 EUROS CLIQUEZ ICI www.spam-exemple.tld", "idem"),
    ]
    for cat, txt, attendu in hors:
        ajouter(cat, txt, attendu)

    # -- Homonymie de sous-thèmes (réponse B2 de Cultura) ----------------------
    par_libelle = {}
    for n1, n2 in couples:
        par_libelle.setdefault(n2, []).append(n1)
    homonymes = {k: v for k, v in par_libelle.items() if len(v) > 1}
    for n2, parents in list(homonymes.items())[:8]:
        for n1 in parents[:2]:
            ajouter("homonymie_niv2",
                    tg.composer([(n1, n2, "Négatif")], rng, bruit=False),
                    f"CAS CRITIQUE : le libelle '{n2}' existe sous {len(parents)} parents. "
                    f"Le couple retourne doit rester coherent avec le parent retenu.",
                    (n1, n2))
    if not homonymes:
        ajouter("homonymie_niv2_absente", "referentiel sans libelle niv.2 partage",
                "AUCUN homonyme dans ce referentiel : le cas critique B2 n'est pas "
                "couvert. A regenerer des reception du referentiel Cultura definitif.")

    # -- Frontières poreuses ---------------------------------------------------
    poreuses = [
        "ma commande retiree en magasin avait 4 jours de retard, personne ne previent",
        "le produit etait en rupture au moment du retrait alors qu'il etait annonce dispo",
        "commande annulee par vos soins pour rupture, sans aucune explication",
        "le colis devait arriver en magasin, il est parti a mon domicile",
        "j'ai voulu retirer en magasin mais le stock affiche en ligne etait faux",
    ]
    for txt in poreuses:
        ajouter("frontiere_poreuse", txt,
                "cas ambigu entre themes voisins ; documente le comportement et alimente "
                "l'atelier de regles d'arbitrage (sollicitation B4)")

    # -- Trois sujets ou plus --------------------------------------------------
    for _ in range(4):
        trois = rng.sample(couples, 3)
        txt = " et ".join(tg.fragment(n1, n2, "Négatif", rng) for n1, n2 in trois)
        ajouter("trois_sujets", txt[0].upper() + txt[1:] + ".",
                "le plafond max_themes = 2 s'applique ; verifie qu'aucune information "
                "ne casse la sortie")

    # Unicité entre cas pièges : deux tirages courts (« top », « bof ») peuvent
    # coïncider et casser I-1. On écarte les doublons non vides.
    vus, retenus = set(), []
    for p in pieges:
        k = p["texte"].strip().lower()
        if k and k in vus:
            continue
        if k:
            vus.add(k)
        retenus.append(p)
    for i, p in enumerate(retenus, 1):
        p["trap_id"] = f"T-{i:03d}"
    return retenus


# --------------------------------------------------------------------------- #
#  Génération du corpus
# --------------------------------------------------------------------------- #
def generer(couples, n_cible, rng) -> list:
    """Produit la liste des verbatims labellisés, textes uniques garantis (I-1)."""
    poids = poids_puissance(len(couples), rng)
    vus = set()
    lignes = []

    pieges = construire_pieges(couples, rng)
    n_normaux = max(0, n_cible - len(pieges))
    n_bi = int(round(n_normaux * 0.20))
    n_bi_div = int(round(n_bi * 0.40))
    n_mono = n_normaux - n_bi

    def cle(txt):
        norm = unicodedata.normalize("NFKD", txt.lower()).strip()
        return "".join(c for c in norm if not unicodedata.combining(c))

    def ajouter(themes, texte, trap_id=""):
        k = cle(texte)
        if k in vus:
            return False
        vus.add(k)
        sent1 = themes[0][2]
        discordant = rng.random() < 0.28
        # Un verbatim bi-theme divergent ne peut pas etre explique par une note unique :
        # note intermediaire imposee (SPEC §4 regle 5).
        if len(themes) == 2 and themes[0][2] != themes[1][2] and "Neutre" not in \
                (themes[0][2], themes[1][2]):
            note = rng.randint(4, 7)
        else:
            note = note_pour(sent1, rng, discordant)
        lignes.append({
            "themes": themes, "texte": texte, "note10": note, "trap_id": trap_id,
        })
        return True

    # -- Cas pièges D'ABORD : ils réservent leurs textes ----------------------
    # Sinon un piège court (« top », « bof ») peut collisionner avec un verbatim
    # du corpus et être silencieusement écarté, ce qui casse I-8.
    for p in pieges:
        n1, n2 = p["couple"]
        vus.add(cle(p["texte"]))
        lignes.append({"themes": [(n1, n2, p["sentiment"])], "texte": p["texte"],
                       "note10": rng.randint(1, 10), "trap_id": p["trap_id"]})

    # -- Couverture obligatoire : chaque couple au moins 8 fois (I-7) ---------
    for n1, n2 in couples:
        obtenus = 0
        for _ in range(60):
            if obtenus >= 8:
                break
            s = rng.choices(SENTIMENTS, weights=[0.55, 0.25, 0.20])[0]
            if ajouter([(n1, n2, s)], tg.composer([(n1, n2, s)], rng)):
                obtenus += 1

    # -- Mono-thème, distribution en loi de puissance -------------------------
    essais = 0
    while sum(1 for x in lignes if len(x["themes"]) == 1) < n_mono and essais < n_mono * 40:
        essais += 1
        n1, n2 = rng.choices(couples, weights=poids)[0]
        s = rng.choices(SENTIMENTS, weights=[0.55, 0.25, 0.20])[0]
        longueur = "long" if rng.random() < 0.06 else None
        ajouter([(n1, n2, s)], tg.composer([(n1, n2, s)], rng, longueur=longueur))

    # -- Bi-thèmes, dont ≥ 40 % à sentiments opposés (I-6) --------------------
    faits_div = 0
    essais = 0
    while sum(1 for x in lignes if len(x["themes"]) == 2) < n_bi and essais < n_bi * 60:
        essais += 1
        (n1a, n2a), (n1b, n2b) = rng.sample(couples, 2)
        if n1a == n1b:
            continue  # SPEC §4 règle 1 : parents différents
        if faits_div < n_bi_div:
            sa, sb = rng.choice([("Négatif", "Positif"), ("Positif", "Négatif")])
        else:
            sa = rng.choices(SENTIMENTS, weights=[0.55, 0.25, 0.20])[0]
            sb = rng.choices(SENTIMENTS, weights=[0.55, 0.25, 0.20])[0]
        themes = [(n1a, n2a, sa), (n1b, n2b, sb)]
        if ajouter(themes, tg.composer(themes, rng)):
            if sa != sb and "Neutre" not in (sa, sb):
                faits_div += 1

    return lignes, pieges


def repartir_splits(lignes, rng):
    """Split 70/15/15 **par texte unique** et **stratifié par couple** (I-2, I-7).

    Aucune duplication n'existe (I-1) : la fuite est impossible par construction.
    La stratification garantit qu'aucun sous-thème n'est absent du test — un split
    purement aléatoire en laissait 6 de côté, les sous-thèmes rares de la loi de
    puissance n'ayant qu'une espérance de 1,2 exemple en test.
    """
    groupes = {}
    for i, li in enumerate(lignes):
        n1, n2, _ = li["themes"][0]
        groupes.setdefault((n1, n2), []).append(i)

    for _, idx in groupes.items():
        rng.shuffle(idx)
        n = len(idx)
        if n == 1:
            lignes[idx[0]]["split"] = "train"
            continue
        if n == 2:
            lignes[idx[0]]["split"] = "train"
            lignes[idx[1]]["split"] = "test"
            continue
        # >= 3 : au moins un exemplaire dans chaque split, reste au prorata 70/15/15
        lignes[idx[0]]["split"] = "test"
        lignes[idx[1]]["split"] = "val"
        reste = idx[2:]
        n_tr = max(1, int(round(len(reste) * 0.70 / 0.90)))
        for rang, i in enumerate(reste):
            if rang < n_tr:
                lignes[i]["split"] = "train"
            else:
                lignes[i]["split"] = "val" if rang % 2 else "test"


# --------------------------------------------------------------------------- #
#  Écriture des artefacts
# --------------------------------------------------------------------------- #
def construire_jeu_labellise(lignes, rng) -> pd.DataFrame:
    recs = []
    sources = list(SOURCES)
    parts = [SOURCES[s]["part"] for s in sources]
    base = dt.date(2026, 5, 1)
    for i, li in enumerate(lignes, 1):
        src = rng.choices(sources, weights=parts)[0]
        note = li["note10"]
        satis_raw, reco = satisfaction_source(src, note, rng)
        th = li["themes"]
        d = base + dt.timedelta(days=rng.randint(0, 100))
        rec = {
            "verbatim_id": f"V-{i:05d}",
            "source": src,
            "date": d.isoformat(),
            "verbatim_original": li["texte"],
            "satisfaction_raw": satis_raw,
            "satisfaction_norm": note,
            "score_reco": reco if reco is not None else "",
            "nb_themes": len(th),
            "theme1_niv1": th[0][0], "theme1_niv2": th[0][1], "theme1_sentiment": th[0][2],
            "theme2_niv1": th[1][0] if len(th) == 2 else "",
            "theme2_niv2": th[1][1] if len(th) == 2 else "",
            "theme2_sentiment": th[1][2] if len(th) == 2 else "",
            "split": li["split"],
            "trap_id": li["trap_id"],
        }
        neg = any(s == "Négatif" for *_, s in th)
        rec["signal_insatisfaction_forte"] = bool(neg and note <= 4)
        rec["signal_churn"] = bool(neg and note <= 3 and rng.random() < 0.55)
        rec["signal_rupture_client"] = bool(rec["signal_churn"] and rng.random() < 0.06)
        recs.append(rec)
    return pd.DataFrame(recs)


def construire_fichiers_entree(df: pd.DataFrame, rng) -> dict:
    """Applique D-17 : un verbatim par champ libre rempli.

    Un même répondant porte donc 1 à N verbatims répartis sur ses champs libres :
    il y a **moins de lignes de fichier que de verbatims**. C'est cette mécanique,
    nouvelle, que la démonstration doit prouver.
    """
    sorties = {}
    for src, spec in SOURCES.items():
        sous = df[df["source"] == src].reset_index(drop=True)
        libres = spec["libres"]
        lignes, i = [], 0
        while i < len(sous):
            k = rng.choices([1, 2, 3, 4], weights=[0.62, 0.24, 0.10, 0.04])[0]
            k = min(k, len(libres), len(sous) - i)
            groupe = sous.iloc[i:i + k]
            i += k
            ref = groupe.iloc[0]
            ligne = {c: "" for c in spec["cols"]}
            for pos, (_, v) in enumerate(groupe.iterrows()):
                ligne[libres[pos]] = v["verbatim_original"]
            _remplir_metadonnees(ligne, src, ref, rng)
            ligne["__verbatim_ids__"] = "|".join(groupe["verbatim_id"])
            lignes.append(ligne)
        cols = spec["cols"] + ["__verbatim_ids__"]
        sorties[src] = pd.DataFrame(lignes)[cols]
    return sorties


def _remplir_metadonnees(ligne, src, ref, rng):
    """Remplit les colonnes non libres, y compris celles écartées par D-18 :
    elles sont présentes dans le fichier pour que la démonstration soit réaliste,
    mais le chargeur ne doit pas les ingérer (contrôle de recette)."""
    d = dt.date.fromisoformat(ref["date"])
    if src.startswith("MDTC"):
        ligne["Date d'achat"] = d.isoformat()
        ligne["Date de réponse"] = (d + dt.timedelta(days=rng.randint(1, 6))).isoformat()
        ligne["Niveau de satisfaction"] = ref["satisfaction_raw"]
        ligne["score RECO"] = ref["score_reco"]
        ligne["Commande"] = f"P{rng.randint(10_000_000, 99_999_999)}"
        ligne["Ancienneté client"] = rng.choice(["Nouveau", "Ancien"])
        return

    mobile = src.endswith("mobile")
    ligne["id"] = float(rng.randint(10_000_000, 99_999_999))
    ligne["survey"] = "ONE - Conversation mobile V2" if mobile else "ONE - Form généraliste"
    ligne["tags"] = rng.choice(["", "", "a_traiter", "3- Connexion_création de compte"])
    ligne["Datetime"] = f"{d.isoformat()} {rng.randint(0,23):02d}:{rng.randint(0,59):02d}:00"
    ligne["url"] = rng.choice([
        "https://www.cultura.com/account", "https://www.cultura.com/checkout",
        "https://www.cultura.com/livre/livres-scolaires.html", "https://www.cultura.com/panier"])
    ligne["Page title"] = rng.choice(["Mon espace client Cultura | Cultura",
                                      "Panier | Cultura", "Livres Scolaire et Parascolaire"])
    ligne["Website data:window.tc_vars.page_type"] = rng.choice(PAGE_TYPES)  # rempli à 100 %
    ligne["Viewport"] = rng.choice(["820x1073", "1600x739", "390x844", "1920x1080"])
    ligne["Form trigger"] = "passive"
    ligne["Form completion percentage"] = float(rng.choice([40.0, 60.0, 100.0]))
    ligne["OS"] = rng.choice(["Windows 10", "OS X 10.15.7", "iOS 26.5.2", "Android 10"])
    ligne["Browser"] = rng.choice(["Chrome 150.0.0", "Safari 18.7.5", "Edge 150.0.0"])
    ligne["Device"] = rng.choice(DEVICES_MOB if mobile else DEVICES_DESK)
    # Colonnes écartées par D-18 — présentes, jamais ingérées.
    ligne["User Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    ligne["Contentsquare session recording"] = \
        f"https://app.contentsquare.com/quick-playback/index.html?pid=18&uu={rng.randint(10**9, 10**10)}"
    sat_col = ("Quel est votre degré de satisfaction concernant le site de Cultura ?" if mobile
               else "Quel est votre degré de satisfaction concernant Cultura ? ")
    ligne[sat_col] = ref["satisfaction_raw"]
    if not mobile:
        ligne["Selected screenshot HTML"] = "<div class='aem-Grid' data-mopinion='1'></div>"
        ligne["Une image vaut mille mots ! Partagez-nous une capture de votre écran :"] = \
            f"https://mopinion-visual-feedback.s3-eu-west-1.amazonaws.com/{rng.randint(10**7, 10**8)}"
        ligne["Website data:tc_vars. page_cat1_name"] = "{}"
    else:
        ligne["Ending element"] = ""


# --------------------------------------------------------------------------- #
#  Contrôle des invariants (SPEC §2) — bloquant
# --------------------------------------------------------------------------- #
def controler(df: pd.DataFrame, couples, pieges) -> dict:
    rap, ok = {}, True

    def check(cle, valeur, condition, detail=""):
        nonlocal ok
        rap[cle] = {"valeur": valeur, "conforme": bool(condition), "detail": detail}
        if not condition:
            ok = False

    textes = df["verbatim_original"].astype(str).str.strip().str.lower()
    non_vides = textes[textes != ""]
    check("I-1_zero_doublon", int(non_vides.duplicated().sum()),
          non_vides.duplicated().sum() == 0, "textes non vides strictement uniques")

    ens = {s: set(df[df.split == s]["verbatim_original"]) for s in ("train", "val", "test")}
    fuite = len(ens["train"] & ens["test"]) + len(ens["train"] & ens["val"])
    check("I-2_zero_fuite", fuite, fuite == 0, "intersection des textes entre splits")

    plages = {"Négatif": (1, 4), "Neutre": (5, 7), "Positif": (8, 10)}
    disc = sum(1 for _, r in df.iterrows()
               if not (plages[r.theme1_sentiment][0] <= r.satisfaction_norm
                       <= plages[r.theme1_sentiment][1]))
    taux = round(disc / len(df), 4)
    check("I-3_sentiment_non_deductible", taux, taux >= 0.25,
          "part de verbatims dont la note ne predit pas le sentiment (cible >= 0,25)")

    valides = set(couples)
    hors = sum(1 for _, r in df.iterrows()
               if (r.theme1_niv1, r.theme1_niv2) not in valides
               or (r.nb_themes == 2 and (r.theme2_niv1, r.theme2_niv2) not in valides))
    check("I-4_couples_valides", hors, hors == 0, "couples hors referentiel")

    vc = df["theme1_niv1"].value_counts()
    ratio = round(vc.max() / max(1, vc.min()), 2)
    check("I-5_desequilibre", ratio, ratio >= 4.0,
          "rapport entre le theme le plus et le moins frequent (cible >= 4)")

    bi = df[df.nb_themes == 2]
    div = bi[(bi.theme1_sentiment != bi.theme2_sentiment)
             & (bi.theme1_sentiment != "Neutre") & (bi.theme2_sentiment != "Neutre")]
    part = round(len(div) / max(1, len(bi)), 4)
    check("I-6_bitheme_divergent", f"{len(div)}/{len(bi)} = {part}", part >= 0.30,
          "part des bi-themes a sentiments opposes (cible >= 0,30)")

    couv_tr = {(r.theme1_niv1, r.theme1_niv2) for _, r in df[df.split == "train"].iterrows()}
    couv_te = {(r.theme1_niv1, r.theme1_niv2) for _, r in df[df.split == "test"].iterrows()}
    manque_tr, manque_te = set(couples) - couv_tr, set(couples) - couv_te
    check("I-7_couverture_train", len(manque_tr), not manque_tr,
          f"sous-themes absents du train : {sorted(manque_tr)[:5]}")
    check("I-7_couverture_test", len(manque_te), not manque_te,
          f"sous-themes absents du test : {sorted(manque_te)[:5]}")

    ids = set(df[df.trap_id != ""]["trap_id"])
    attendus = {p["trap_id"] for p in pieges}
    check("I-8_pieges_references", f"{len(ids)}/{len(attendus)}", ids == attendus,
          "chaque cas piege est present et reference au manifeste")

    rap["_conforme_global"] = ok
    return rap


def statistiques(df: pd.DataFrame) -> dict:
    lg = df["verbatim_original"].astype(str).str.len()
    return {
        "n_verbatims": len(df),
        "n_textes_uniques": int(df["verbatim_original"].nunique()),
        "split": df["split"].value_counts().to_dict(),
        "source": df["source"].value_counts().to_dict(),
        "nb_themes": df["nb_themes"].value_counts().to_dict(),
        "sentiment_theme1": df["theme1_sentiment"].value_counts().to_dict(),
        "longueur_caracteres": {k: round(float(v), 1) for k, v in
                                lg.describe(percentiles=[.25, .5, .75, .95]).items()},
        "distribution_niv1": df["theme1_niv1"].value_counts().to_dict(),
        "taux_signaux": {c: round(float(df[c].mean()), 4) for c in
                         ["signal_rupture_client", "signal_churn",
                          "signal_insatisfaction_forte"]},
        "n_cas_pieges": int((df["trap_id"] != "").sum()),
    }


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--taxonomy", default="data/raw/taxonomy_cultura_poc.json",
                    help="referentiel a utiliser (remplacer par celui de Cultura)")
    ap.add_argument("-n", "--nombre", type=int, default=1500, help="verbatims cibles")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/raw/fake")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    chemin_taxo = RACINE / args.taxonomy
    if not chemin_taxo.exists():
        print(f"ERREUR : referentiel introuvable : {chemin_taxo}", file=sys.stderr)
        return 2
    couples = charger_taxonomie(chemin_taxo)
    print(f"Referentiel : {chemin_taxo.name} — "
          f"{len({c[0] for c in couples})} themes, {len(couples)} sous-themes")

    lignes, pieges = generer(couples, args.nombre, rng)
    repartir_splits(lignes, rng)
    df = construire_jeu_labellise(lignes, rng)
    fichiers = construire_fichiers_entree(df, rng)

    sortie = RACINE / args.out
    sortie.mkdir(parents=True, exist_ok=True)
    df.to_excel(sortie / "fake_labeled.xlsx", index=False)
    for src, sous in fichiers.items():
        spec = SOURCES[src]
        sous.to_excel(sortie / spec["fichier"], sheet_name=spec["sheet"], index=False)

    manifeste = [{k: v for k, v in p.items() if k != "couple"} | {"couple": list(p["couple"])}
                 for p in pieges]
    (sortie / "fake_dataset_traps.json").write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=1), encoding="utf-8")

    rapport = {"genere_le": dt.datetime.now().isoformat(timespec="seconds"),
               "referentiel": str(args.taxonomy), "seed": args.seed,
               "invariants": controler(df, couples, pieges),
               "statistiques": statistiques(df)}
    (sortie / "fake_dataset_report.json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=1), encoding="utf-8")

    inv = rapport["invariants"]
    print("\n--- Invariants (SPEC §2) ---")
    for cle, val in inv.items():
        if cle.startswith("_"):
            continue
        print(f"  {'OK ' if val['conforme'] else 'ECHEC'}  {cle:32s} {val['valeur']}")
    st = rapport["statistiques"]
    print(f"\n{st['n_verbatims']} verbatims, {st['n_textes_uniques']} textes uniques")
    print(f"lignes de fichier : " +
          ", ".join(f"{s}={len(d)}" for s, d in fichiers.items()))
    print(f"artefacts dans {sortie}")

    if not inv["_conforme_global"]:
        print("\nGENERATION NON CONFORME — voir fake_dataset_report.json", file=sys.stderr)
        return 1
    print("\nGENERATION CONFORME")
    return 0


if __name__ == "__main__":
    sys.exit(main())
