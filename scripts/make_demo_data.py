#!/usr/bin/env python
"""Génère un jeu de DÉMO synthétique (aucune donnée client réelle).

Produit deux fichiers Excel au schéma des sources de production :
  - MDTC      : « Niveau de satisfaction général », « Verbatim justification »,
                « Verbatim suggestion », « Date de commande »
  - Mopinion  : « Niveau de satisfaction général », « Description du bug »,
                « Suggestion », « Date du retour »

Les verbatims sont fabriqués à partir de gabarits couvrant les grands thèmes de la
taxonomie. Quelques PII FACTICES (e-mails, téléphones, n° de commande inventés)
sont insérées pour démontrer l'anonymisation — elles ne désignent personne.

Usage :
    python scripts/make_demo_data.py                 # -> data/demo/*.xlsx (120 lignes)
    python scripts/make_demo_data.py --n 300 --out data/demo
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import pandas as pd

SEED = 42

# (gabarit de verbatim, note de satisfaction indicative)
POSITIFS = [
    ("Site très facile à utiliser, commande passée en deux minutes, merci !", 9),
    ("Livraison rapide et colis nickel, je recommande.", 9),
    ("Super expérience, le retrait en magasin était prêt en avance.", 8),
    ("Application intuitive, j'ai trouvé mon produit tout de suite.", 8),
    ("Service client au top, problème réglé en un appel.", 9),
]
NEGATIFS = [
    ("Toujours pas reçu mon colis après deux semaines, aucune notification.", 2),
    ("Paiement refusé trois fois alors que ma carte fonctionne, très frustrant.", 2),
    ("Le code promo n'a pas fonctionné au moment de payer, déçu.", 3),
    ("Commande annulée sans explication, je ne comprends pas.", 1),
    ("Produit en rupture mais toujours affiché disponible sur le site.", 3),
    ("Site très lent, impossible de finaliser le panier sur mobile.", 2),
    ("Remboursement toujours pas reçu un mois après le retour.", 2),
    ("Impossible de me connecter à mon compte, mot de passe refusé.", 3),
    ("Trop d'emails promotionnels, je me suis désabonné.", 4),
    ("Qualité du produit décevante, pas conforme à la description.", 3),
]
NEUTRES = [
    ("Commande conforme, rien à signaler de particulier.", 6),
    ("Livraison dans les délais annoncés.", 6),
    ("Navigation correcte mais la recherche pourrait être améliorée.", 5),
]
# PII factices à insérer aléatoirement (anonymisation attendue).
PII_SNIPPETS = [
    " Vous pouvez me joindre à demo.client{n}@example.test.",
    " Mon numéro est le 06 00 00 {a} {b}.",
    " Référence commande CMD{n}{a}.",
    "",
    "",
    "",
]


def _verbatim(rng: random.Random, base: str) -> str:
    pii = rng.choice(PII_SNIPPETS).format(
        n=rng.randint(1000, 9999), a=rng.randint(10, 99), b=rng.randint(10, 99)
    )
    return (base + pii).strip()


def _date(rng: random.Random) -> str:
    return f"2026-{rng.randint(1, 6):02d}-{rng.randint(1, 28):02d}"


def build(n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(SEED)
    pool = [(t, s, "pos") for t, s in POSITIFS] + \
           [(t, s, "neg") for t, s in NEGATIFS] + \
           [(t, s, "neu") for t, s in NEUTRES]

    mdtc_rows, mop_rows = [], []
    for i in range(n):
        base, sat, _ = rng.choice(pool)
        text = _verbatim(rng, base)
        if i % 2 == 0:  # MDTC
            mdtc_rows.append({
                "Date de commande": _date(rng),
                "Niveau de satisfaction général": sat,
                "Verbatim justification": text,
                "Verbatim suggestion": "" if rng.random() < 0.7 else "Améliorez le suivi de livraison.",
            })
        else:  # Mopinion : bug si insatisfait, suggestion sinon
            insatisfait = sat <= 4
            mop_rows.append({
                "Date du retour": _date(rng),
                "Niveau de satisfaction général": sat,
                "Description du bug": text if insatisfait else "",
                "Suggestion": "" if insatisfait else text,
            })
    return pd.DataFrame(mdtc_rows), pd.DataFrame(mop_rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Génère un jeu de démo synthétique (sans PII réelle).")
    p.add_argument("--n", type=int, default=120, help="Nombre total de verbatims.")
    p.add_argument("--out", default="data/demo", help="Dossier de sortie.")
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    mdtc, mop = build(args.n)
    mdtc_path = out / "mdtc_demo.xlsx"
    mop_path = out / "mopinion_demo.xlsx"
    mdtc.to_excel(mdtc_path, index=False)
    mop.to_excel(mop_path, index=False)
    print(f"Jeu de démo généré ({len(mdtc)} MDTC + {len(mop)} Mopinion, sans PII réelle) :")
    print(f"  - {mdtc_path}")
    print(f"  - {mop_path}")


if __name__ == "__main__":
    main()
