"""Rapport d'évaluation complet du pipeline sur le jeu de TEST.

Métriques produites :
  - Classification niv.1 (multi-label) : F1 macro / micro / weighted + F1 par thème.
  - Classification niv.2 (à niv.1 connu) : F1 macro + F1 par sous-thème.
  - Précision hiérarchique : P(niv1 correct), P(niv2 | niv1 correct), jointe.
  - Matrice de confusion niv.1 (heatmap ASCII).
  - Sentiment : accuracy + F1 par classe.
  - Signaux : précision / rappel / F1 / AUC-ROC par signal.
  - Taux de revue humaine selon le seuil de confiance.

Le rapport est imprimé ET sauvegardé dans data/processed/eval_report.json.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import numpy as np

from ..inference.predictor import build_output, VerbatimPredictor
from ..training.prepare_dataset import ProcessedDataset
from ..utils import load_config, resolve_path, sentiment_input

logger = logging.getLogger(__name__)

_HEAT_CHARS = " .:-=+*#%@"


def ascii_heatmap(cm: np.ndarray, labels: List[str], normalize: bool = True) -> str:
    """Rend une matrice de confusion en heatmap ASCII compacte (lignes = vérité)."""
    cm = np.asarray(cm, dtype=float)
    n = cm.shape[0]
    disp = cm.copy()
    if normalize:
        row_sums = disp.sum(axis=1, keepdims=True)
        disp = np.divide(disp, np.clip(row_sums, 1, None))
    lines = ["    " + "".join(f"{j%10}" for j in range(n)) + "   (colonnes = prédit)"]
    for i in range(n):
        cells = []
        for j in range(n):
            v = disp[i, j]
            idx = min(len(_HEAT_CHARS) - 1, int(v * (len(_HEAT_CHARS) - 1) + 0.5))
            cells.append(_HEAT_CHARS[idx])
        lines.append(f"{i:>2} |" + "".join(cells) + f"| {labels[i][:30]}")
    lines.append("Intensité: '" + _HEAT_CHARS + "' (faible -> fort, normalisé par ligne)")
    return "\n".join(lines)


def evaluate(cfg: Dict[str, Any], predictor: Optional[VerbatimPredictor] = None) -> Dict[str, Any]:
    """Calcule toutes les métriques sur le test set et sauvegarde le rapport."""
    from sklearn.metrics import (
        accuracy_score, confusion_matrix, f1_score, precision_score,
        recall_score, roc_auc_score,
    )

    data = ProcessedDataset.load(cfg)
    test = data.split("test")
    tax = (predictor.taxonomy if predictor else None)
    if predictor is None:
        predictor = VerbatimPredictor(cfg)
        tax = predictor.taxonomy
    bs = cfg["model"]["batch_size_inference"]

    texts = test["text_clean"].tolist()
    sat_col = "__satisfaction__"
    sats = test[sat_col].tolist() if sat_col in test.columns else [None] * len(test)

    logger.info("Inférence d'évaluation sur %d verbatims de test...", len(test))
    niv1_probs = predictor.clf_niv1.predict_proba(texts, bs)
    niv2_probs = predictor.clf_niv2.predict_proba(texts, bs)
    sent_texts = [sentiment_input(t, s, cfg) for t, s in zip(texts, sats)]
    sent_probs = predictor.clf_sentiment.predict_proba(sent_texts, bs)
    signal_probs = predictor._signal_probs(texts)

    report: Dict[str, Any] = {}

    # --- 1. Classification niv.1 (multi-label) --------------------------------
    thr1 = cfg["thresholds"]["classification_niv1"]
    y1_true = data.niv1_matrix(test).astype(int)
    y1_pred = (niv1_probs >= thr1).astype(int)
    report["niv1"] = {
        "f1_macro": float(f1_score(y1_true, y1_pred, average="macro", zero_division=0)),
        "f1_micro": float(f1_score(y1_true, y1_pred, average="micro", zero_division=0)),
        "f1_weighted": float(f1_score(y1_true, y1_pred, average="weighted", zero_division=0)),
        "per_theme_f1": {},
    }
    f1_per = f1_score(y1_true, y1_pred, average=None, zero_division=0)
    report["niv1"]["per_theme_f1"] = {
        tax.niv1_labels[i]: round(float(f1_per[i]), 4) for i in range(tax.n_niv1)
    }

    # --- 2. Confusion niv.1 (top-1) + accuracy --------------------------------
    top1 = niv1_probs.argmax(axis=1)
    true_t1 = np.array([tax.niv1_to_idx[x] for x in test["theme1_niv1"]])
    cm = confusion_matrix(true_t1, top1, labels=list(range(tax.n_niv1)))
    report["niv1"]["top1_accuracy"] = float(accuracy_score(true_t1, top1))
    report["niv1"]["confusion_matrix"] = cm.tolist()

    # --- 3. niv.2 à niv.1 connu (qualité intrinsèque de la tête niv.2) --------
    gold_niv2 = np.array([tax.niv2_to_idx[x] for x in test["theme1_niv2"]])
    pred_niv2_gold = np.array([
        tax.niv2_to_idx[tax.best_niv2_for_niv1(test["theme1_niv1"].iloc[i], niv2_probs[i])[0]]
        for i in range(len(test))
    ])
    report["niv2"] = {
        "f1_macro": float(f1_score(gold_niv2, pred_niv2_gold, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(gold_niv2, pred_niv2_gold, average="weighted", zero_division=0)),
        "accuracy_given_gold_niv1": float(accuracy_score(gold_niv2, pred_niv2_gold)),
    }
    f1_n2 = f1_score(gold_niv2, pred_niv2_gold, average=None,
                     labels=list(range(tax.n_niv2)), zero_division=0)
    report["niv2"]["per_subtheme_f1"] = {
        tax.niv2_labels[i]: round(float(f1_n2[i]), 4) for i in range(tax.n_niv2)
    }

    # --- 4. Précision hiérarchique (end-to-end top-1) -------------------------
    pred_niv2_e2e = np.array([
        tax.niv2_to_idx[tax.best_niv2_for_niv1(tax.idx_to_niv1[int(top1[i])], niv2_probs[i])[0]]
        for i in range(len(test))
    ])
    niv1_correct = top1 == true_t1
    n_niv1_correct = int(niv1_correct.sum())
    niv2_correct_given_niv1 = (pred_niv2_e2e[niv1_correct] == gold_niv2[niv1_correct])
    report["hierarchical"] = {
        "p_niv1_correct": float(niv1_correct.mean()),
        "p_niv2_correct_given_niv1_correct": float(niv2_correct_given_niv1.mean()) if n_niv1_correct else 0.0,
        "p_niv1_correct_niv2_wrong": float((~niv2_correct_given_niv1).mean()) if n_niv1_correct else 0.0,
        "p_joint_correct": float(((top1 == true_t1) & (pred_niv2_e2e == gold_niv2)).mean()),
    }

    # --- 5. Sentiment ---------------------------------------------------------
    sent_pred = sent_probs.argmax(axis=1)
    sent_true = data.sentiment_targets(test)
    report["sentiment"] = {
        "accuracy": float(accuracy_score(sent_true, sent_pred)),
        "f1_macro": float(f1_score(sent_true, sent_pred, average="macro", zero_division=0)),
        "per_class_f1": {
            data.sentiment_labels[i]: round(float(x), 4)
            for i, x in enumerate(f1_score(sent_true, sent_pred, average=None,
                                           labels=list(range(len(data.sentiment_labels))),
                                           zero_division=0))
        },
    }

    # --- 6. Signaux -----------------------------------------------------------
    report["signals"] = {}
    for label_col, short in [("signal_rupture_client", "rupture"),
                             ("signal_churn", "churn"),
                             ("signal_insatisfaction_forte", "insatisfaction")]:
        y = data.signal_targets(test, label_col)
        proba = signal_probs[short]
        thr = predictor.signal_thresholds[short]
        preds = (proba >= thr).astype(int)
        entry = {
            "threshold": float(thr),
            "precision": float(precision_score(y, preds, zero_division=0)),
            "recall": float(recall_score(y, preds, zero_division=0)),
            "f1": float(f1_score(y, preds, zero_division=0)),
            "n_positives": int(y.sum()),
        }
        if len(np.unique(y)) > 1:
            entry["auc_roc"] = float(roc_auc_score(y, proba))
        report["signals"][short] = entry

    # --- 7. Taux de revue humaine par seuil -----------------------------------
    results = [
        build_output(
            texts[i], niv1_probs[i], niv2_probs[i], sent_probs[i],
            {s: float(signal_probs[s][i]) for s in signal_probs},
            sats[i], tax, cfg, predictor.signal_thresholds, data.sentiment_labels,
        )
        for i in range(len(test))
    ]
    conf = np.array([r["confidence_globale"] for r in results])
    report["human_review"] = {
        f"threshold_{t:.2f}": float((conf < t).mean()) for t in [0.5, 0.6, 0.65, 0.7, 0.75, 0.8]
    }

    # --- Sauvegarde + impression ----------------------------------------------
    out_path = resolve_path(cfg, cfg["paths"]["eval_report"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print_report(report, tax.niv1_labels, np.array(report["niv1"]["confusion_matrix"]))
    logger.info("Rapport d'évaluation sauvegardé : %s", out_path)
    return report


def print_report(report: Dict[str, Any], niv1_labels: List[str], cm: np.ndarray) -> None:
    """Affiche un rapport lisible en console."""
    line = "=" * 70
    print(f"\n{line}\n  RAPPORT D'ÉVALUATION — jeu de test\n{line}")
    n = report["niv1"]
    print(f"\n[NIVEAU 1 — classification thématique (multi-label)]")
    print(f"  F1-macro    : {n['f1_macro']:.4f}    F1-micro : {n['f1_micro']:.4f}    "
          f"F1-weighted : {n['f1_weighted']:.4f}")
    print(f"  Top-1 accuracy : {n['top1_accuracy']:.4f}")
    worst = sorted(n["per_theme_f1"].items(), key=lambda x: x[1])[:5]
    print("  5 thèmes les plus difficiles :")
    for label, f1 in worst:
        print(f"     {f1:.3f}  {label}")

    n2 = report["niv2"]
    print(f"\n[NIVEAU 2 — sous-thèmes (à niv.1 connu)]")
    print(f"  F1-macro : {n2['f1_macro']:.4f}    Accuracy : {n2['accuracy_given_gold_niv1']:.4f}")

    h = report["hierarchical"]
    print(f"\n[HIÉRARCHIE — end-to-end]")
    print(f"  P(niv1 correct)                : {h['p_niv1_correct']:.4f}")
    print(f"  P(niv2 correct | niv1 correct) : {h['p_niv2_correct_given_niv1_correct']:.4f}")
    print(f"  P(niv1 correct mais niv2 faux) : {h['p_niv1_correct_niv2_wrong']:.4f}")
    print(f"  P(niv1 ET niv2 corrects)       : {h['p_joint_correct']:.4f}")

    s = report["sentiment"]
    print(f"\n[SENTIMENT]")
    print(f"  Accuracy : {s['accuracy']:.4f}    F1-macro : {s['f1_macro']:.4f}")
    print(f"  Par classe : " + "  ".join(f"{k}={v:.3f}" for k, v in s["per_class_f1"].items()))

    print(f"\n[SIGNAUX]")
    for short, e in report["signals"].items():
        auc = f"  AUC={e['auc_roc']:.3f}" if "auc_roc" in e else ""
        print(f"  {short:14s} P={e['precision']:.3f}  R={e['recall']:.3f}  "
              f"F1={e['f1']:.3f}  (seuil={e['threshold']:.2f}, n+={e['n_positives']}){auc}")

    print(f"\n[TAUX DE REVUE HUMAINE selon le seuil de confiance]")
    for k, v in report["human_review"].items():
        print(f"  {k.replace('threshold_','seuil ')} -> {v*100:5.1f} %")

    print(f"\n[MATRICE DE CONFUSION niv.1 (heatmap, lignes = vérité)]")
    print(ascii_heatmap(cm, niv1_labels))
    print(line)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    evaluate(load_config())
