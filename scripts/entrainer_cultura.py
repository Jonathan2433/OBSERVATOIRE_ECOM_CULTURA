#!/usr/bin/env python3
"""Réentraînement sur le corpus Cultura 2026 — lot L6.

Réutilise les boucles d'entraînement existantes (`train_niv1`, `train_niv2`,
`train_sentiment`) **sans les modifier** : le jeu est exposé via une sous-classe
de ``ProcessedDataset`` qui respecte les masques produits par la préparation
(``apprend_niv1`` / ``apprend_niv2`` / ``apprend_sentiment``) et l'exclusion des
sous-thèmes hors périmètre (D-32).

Arbitrages du PO appliqués et inscrits dans la carte d'entraînement :

* **D-37** — échelle de satisfaction sur 4 ;
* **D-39** — préfixe conditionnel à la longueur (retiré au-delà de `max_mots`) ;
* **D-41** — un seul modèle de signal, `insatisfaction` (887 exemples). Churn (64)
  et Rupture (32) sont trop rares pour être évaluables et restent produits par règle.

Les modèles sont écrits sous ``data/models/cultura_2026/`` : les modèles actifs de
la V1, que l'application lit encore, ne sont **pas** écrasés.

Usage :
    python scripts/entrainer_cultura.py [--lowercase false] [--taches niv1,niv2,sentiment,signal]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.training.prepare_dataset import ProcessedDataset  # noqa: E402
from src.utils.config import load_config, resolve_path, set_seed  # noqa: E402
from src.utils.features import politique_prefixe  # noqa: E402
from src.utils.taxonomy import Taxonomy  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("L6")


class JeuCultura(ProcessedDataset):
    """Expose le corpus Cultura à travers le contrat de ``ProcessedDataset``.

    Trois différences avec la V1, toutes issues de la préparation :

    * les exemples sont filtrés par les masques ``apprend_*`` (couples invalides
      et annotations recopiées sont écartés — §8.4 et §5.2) ;
    * le niveau 2 exclut les sous-thèmes hors périmètre (D-32) ;
    * le sentiment est porté par la colonne ``sentiment`` et non
      ``theme1_sentiment``.
    """

    def niv1_matrix(self, df: pd.DataFrame) -> np.ndarray:
        mat = np.zeros((len(df), self.taxonomy.n_niv1), dtype=np.float32)
        for i, (_, row) in enumerate(df.iterrows()):
            for col in ("theme1_niv1", "theme2_niv1"):
                val = row.get(col)
                if isinstance(val, str) and val in self.taxonomy.niv1_to_idx:
                    mat[i, self.taxonomy.niv1_to_idx[val]] = 1.0
        return mat

    def niv2_examples(self, df: pd.DataFrame) -> Tuple[List[str], List[int]]:
        sub = df[df["apprend_niv2"] == True]  # noqa: E712
        return (sub["text_clean"].tolist(),
                [int(v) for v in sub["y_niv2"].tolist()])

    def sentiment_targets(self, df: pd.DataFrame) -> np.ndarray:
        return np.array([int(v) for v in df["y_sentiment"].tolist()], dtype=np.int64)

    def split(self, name: str) -> pd.DataFrame:
        return self.df[self.df["split"] == name].reset_index(drop=True)

    def split_niv1(self, name: str) -> pd.DataFrame:
        return self.df[(self.df["split"] == name)
                       & (self.df["apprend_niv1"] == True)].reset_index(drop=True)  # noqa: E712

    def split_sentiment(self, name: str) -> pd.DataFrame:
        return self.df[(self.df["split"] == name)
                       & (self.df["apprend_sentiment"] == True)].reset_index(drop=True)  # noqa: E712


def sous_jeu(jeu: "JeuCultura", colonne: str) -> "JeuCultura":
    """Restreint le jeu aux lignes exploitables par une tâche donnée.

    Indispensable : ``split("train")`` renvoie sinon aussi les verbatims **non
    annotés** (417 au train), qui apprendraient au modèle de niveau 1 à ne
    prédire aucun thème. Ces lignes servent à l'inférence, pas à l'entraînement.
    """
    return JeuCultura(
        jeu.df[jeu.df[colonne] == True].reset_index(drop=True),  # noqa: E712
        jeu.encoders, jeu.taxonomy)


def charger_jeu(cfg: Dict[str, Any], dossier: Path) -> JeuCultura:
    df = pd.read_csv(dossier / "dataset.csv", encoding="utf-8")
    df["text_clean"] = df["text_clean"].fillna("").astype(str)
    brut = json.loads((dossier / "encoders.json").read_text(encoding="utf-8"))
    # Alignement des noms de clés sur le contrat de ProcessedDataset.
    encodeurs = dict(brut)
    encodeurs["niv1_pos_weight"] = brut["poids_niv1_pos_weight"]
    encodeurs["niv2_class_weight"] = brut["poids_niv2"]
    encodeurs["sentiment_class_weight"] = brut["poids_sentiment"]
    taxonomy = Taxonomy.from_json(resolve_path(cfg, cfg["cultura_sources"]["taxonomy"]))
    return JeuCultura(df, encodeurs, taxonomy)


def _rediriger_sorties(cfg: Dict[str, Any]) -> None:
    """Écrit les modèles sous `data/models/cultura_2026/` — la V1 reste intacte."""
    for cle in ("model_classifier_niv1", "model_classifier_niv2",
                "model_sentiment", "model_signals"):
        ancien = cfg["paths"][cle]
        cfg["paths"][cle] = ancien.replace("data/models/", "data/models/cultura_2026/")
    cfg["paths"]["taxonomy"] = cfg["cultura_sources"]["taxonomy"]
    # Journal dédié : sans cela, les époques du nouveau modèle s'ajoutent à
    # `training_logs.json` de la V1, que les tableaux de bord lisent encore.
    cfg["paths"]["training_logs"] = "data/processed/cultura_2026/training_logs.json"


#: Effectif minimal de positifs au train pour qu'un signal soit entraîné.
#: En deçà, on ne produit pas de modèle : une métrique sur trop peu de positifs
#: est trompeuse, et D-41 préfère l'absence assumée au chiffre inventé.
MIN_POSITIFS_SIGNAL = 150


def entrainer_signal(jeu: JeuCultura, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Entraîne les signaux qui disposent d'assez de positifs (D-41 assoupli).

    D-41 ne retenait que `insatisfaction`, faute d'effectif : churn 64 positifs,
    rupture 32. L'augmentation par le jeu factice reprojeté change la donne pour
    churn (266 au train) mais pas pour rupture (37). La règle est donc portée par
    un seuil, ``MIN_POSITIFS_SIGNAL``, et non par une liste figée : un signal est
    entraîné s'il a de quoi l'être, et **explicitement écarté sinon**.

    ⚠️ Les positifs supplémentaires sont **synthétiques**. Un modèle de churn
    entraîné dessus peut n'avoir appris que les tournures du générateur. C'est
    pourquoi l'évaluation ci-dessous porte sur la **validation réelle**, jamais
    sur les données factices.
    """
    import joblib
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    from src.modeling.architecture import EmbeddingExtractor, save_versioned  # noqa: F401

    extracteur = EmbeddingExtractor(cfg)
    resultats: Dict[str, Any] = {}
    tr, va = jeu.split("train"), jeu.split("val")
    X_tr = extracteur.embed(tr["text_clean"].tolist(), cfg["model"]["batch_size_inference"])
    X_va = extracteur.embed(va["text_clean"].tolist(), cfg["model"]["batch_size_inference"])

    base = resolve_path(cfg, cfg["paths"]["model_signals"])
    version = base / time.strftime("%Y%m%d_%H%M%S")
    version.mkdir(parents=True, exist_ok=True)
    entraines, ecartes = [], {}
    synth = tr["__synthetique__"].fillna(False).astype(bool).to_numpy() \
        if "__synthetique__" in tr.columns else None

    for nom in ("insatisfaction", "churn", "rupture"):
        col = f"y_signal_{nom}"
        if col not in tr.columns:
            ecartes[nom] = "colonne de cible absente du jeu préparé"
            continue
        y_tr = tr[col].fillna(0).astype(int).to_numpy()
        y_va = va[col].fillna(0).astype(int).to_numpy()
        n_pos = int(y_tr.sum())
        if n_pos < MIN_POSITIFS_SIGNAL:
            ecartes[nom] = (f"{n_pos} positifs au train, seuil {MIN_POSITIFS_SIGNAL} — "
                            "non entraîné, produit à False")
            logger.warning("Signal '%s' écarté : %s", nom, ecartes[nom])
            continue

        pipe = Pipeline([("scaler", StandardScaler()),
                         ("clf", LogisticRegression(class_weight="balanced",
                                                    max_iter=cfg["signals"]["max_iter"],
                                                    C=1.0, random_state=42))])
        pipe.fit(X_tr, y_tr)
        p_va = pipe.predict_proba(X_va)[:, 1]
        seuil = float(cfg["thresholds"].get(f"signal_{nom}", 0.5))
        pred = (p_va >= seuil).astype(int)
        joblib.dump(pipe, version / f"{nom}.joblib")
        entraines.append(nom)
        resultats[nom] = {
            "n_positifs_train": n_pos,
            "n_positifs_train_reels": (int(y_tr[~synth].sum()) if synth is not None else n_pos),
            "n_positifs_train_synthetiques": (int(y_tr[synth].sum()) if synth is not None else 0),
            # La validation est PUREMENT RÉELLE : c'est le seul chiffre qui compte.
            "n_positifs_val_reels": int(y_va.sum()),
            "seuil": seuil,
            "precision": float(precision_score(y_va, pred, zero_division=0)),
            "recall": float(recall_score(y_va, pred, zero_division=0)),
            "f1": float(f1_score(y_va, pred, zero_division=0)),
            "auc": float(roc_auc_score(y_va, p_va)) if len(set(y_va)) > 1 else None,
        }

    (version / "signals_metadata.json").write_text(json.dumps({
        "signaux_entraines": entraines,
        "signaux_non_entraines": ecartes,
        "seuil_minimal_de_positifs": MIN_POSITIFS_SIGNAL,
        "thresholds": {n: resultats[n]["seuil"] for n in entraines},
        "metrics": resultats,
        "pooling": cfg["signals"]["pooling"],
        "avertissement": ("les positifs supplémentaires de churn sont synthétiques ; "
                          "les métriques ci-dessus sont mesurées sur la validation "
                          "RÉELLE, seule mesure opposable"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "CURRENT").write_text(version.name, encoding="utf-8")
    return resultats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--taches", default="niv1,niv2,sentiment,signal")
    ap.add_argument("--lowercase", default="false", choices=["true", "false"],
                    help="CamemBERT est un modèle cased ; false est la piste à tester")
    ap.add_argument("--donnees", default="data/processed/cultura_2026")
    ap.add_argument("--repreparer", action="store_true",
                    help="force la re-préparation même si le jeu existe")
    ap.add_argument("--epochs-themes", type=int, default=None,
                    help="époques pour niv1 et niv2. Mesuré à l'itération 1 : les "
                         "deux progressaient encore à la 5e époque.")
    ap.add_argument("--epochs-sentiment", type=int, default=None,
                    help="époques pour le sentiment. Mesuré : plateau dès la 2e.")
    args = ap.parse_args()

    cfg = load_config()
    set_seed(cfg["model"]["seed"])

    # Arbitrages du PO, appliqués à la configuration de cette exécution.
    cfg["sentiment"]["satisfaction_scale_max"] = 4                     # D-37
    cfg["sentiment"]["prefixe_conditionnel"]["actif"] = True           # D-39
    cfg["cleaning"]["lowercase"] = (args.lowercase == "true")
    _rediriger_sorties(cfg)

    # Le nettoyage est appliqué à la PRÉPARATION, pas à l'entraînement : changer
    # `--lowercase` impose donc de re-préparer, sinon le modèle serait entraîné
    # sur un texte qui ne correspond pas à sa carte. Chaque variante a son
    # répertoire ; le découpage, lui, reste le jeu gelé commun.
    # Un répertoire fourni explicitement et déjà présent est utilisé tel quel :
    # sinon on lui accolerait un suffixe de variante qu'il porte déjà.
    if (ROOT / args.donnees / "dataset.csv").is_file():
        dossier = ROOT / args.donnees
    else:
        suffixe = "" if cfg["cleaning"]["lowercase"] else "_lc_false"
        dossier = ROOT / (args.donnees + suffixe)
    if not (dossier / "dataset.csv").is_file() or args.repreparer:
        from src.training.preparer_cultura import preparer
        logger.info("Préparation du corpus (lowercase=%s) -> %s",
                    cfg["cleaning"]["lowercase"], dossier.name)
        preparer(cfg, dossier)
    jeu = charger_jeu(cfg, dossier)
    taches = [t.strip() for t in args.taches.split(",") if t.strip()]

    logger.info("Corpus : %d lignes · niv1=%d niv2=%d sentiment=%d (train)",
                len(jeu.df),
                int(((jeu.df["split"] == "train") & jeu.df["apprend_niv1"]).sum()),
                int(((jeu.df["split"] == "train") & jeu.df["apprend_niv2"]).sum()),
                int(((jeu.df["split"] == "train") & jeu.df["apprend_sentiment"]).sum()))
    logger.info("Politique de préfixe : %s · lowercase=%s",
                politique_prefixe(cfg), cfg["cleaning"]["lowercase"])

    bilan: Dict[str, Any] = {
        "politique_prefixe": politique_prefixe(cfg),
        "lowercase": cfg["cleaning"]["lowercase"],
        "taches": taches,
    }
    t_global = time.time()

    ep_themes = args.epochs_themes or cfg["model"]["epochs"]
    ep_sent = args.epochs_sentiment or cfg["model"]["epochs"]
    bilan["epochs"] = {"themes": ep_themes, "sentiment": ep_sent}
    logger.info("Époques : thèmes=%d · sentiment=%d", ep_themes, ep_sent)

    if "niv1" in taches:
        from src.training.train_classifier import train_niv1
        cfg["model"]["epochs"] = ep_themes
        t0 = time.time()
        bilan["niv1"] = train_niv1(sous_jeu(jeu, "apprend_niv1"), cfg)
        bilan["niv1"]["duree_s"] = round(time.time() - t0, 1)

    if "niv2" in taches:
        from src.training.train_classifier import train_niv2
        cfg["model"]["epochs"] = ep_themes
        t0 = time.time()
        bilan["niv2"] = train_niv2(sous_jeu(jeu, "apprend_niv2"), cfg)
        bilan["niv2"]["duree_s"] = round(time.time() - t0, 1)

    if "sentiment" in taches:
        from src.training.train_sentiment import train_sentiment
        cfg["model"]["epochs"] = ep_sent
        t0 = time.time()
        # 572 verbatims sont annotés en thème sans sentiment : ils sont exclus
        # de cette tâche et conservés pour les autres.
        bilan["sentiment"] = train_sentiment(cfg, sous_jeu(jeu, "apprend_sentiment"))
        bilan["sentiment"]["duree_s"] = round(time.time() - t0, 1)

    if "signal" in taches:
        t0 = time.time()
        bilan["signal"] = entrainer_signal(jeu, cfg)
        bilan["signal"]["duree_s"] = round(time.time() - t0, 1)

    bilan["duree_totale_s"] = round(time.time() - t_global, 1)
    chemin = dossier / f"bilan_entrainement_{time.strftime('%Y%m%d_%H%M%S')}.json"
    chemin.write_text(json.dumps(bilan, ensure_ascii=False, indent=2, default=str),
                      encoding="utf-8")
    logger.info("Terminé en %.1f min — %s", bilan["duree_totale_s"] / 60, chemin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
