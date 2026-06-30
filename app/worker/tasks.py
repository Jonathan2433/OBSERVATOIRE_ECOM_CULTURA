"""Tâches exécutées par le worker RQ.

- ``process_batch_job`` : traite un lot Excel (anonymisation -> nettoyage ->
  inférence) et persiste les résultats avec progression incrémentale.
- ``sync_registry_job`` : (re)synchronise le registre des modèles.
- ``ping`` : diagnostic.
"""
from __future__ import annotations

import logging
import math
import os
import platform
import random
import time
from collections import Counter
from datetime import datetime, timezone

from common.db import SessionLocal
from common.models import (
    Batch, ComparisonRun, ENGINE_ROLE_COMPARE, ENGINE_ROLE_PROPOSER, ENGINE_ROLE_REFINER,
    EnginePrediction, JudgeVerdict, MODEL_KIND_LMSTUDIO, ModelVersion, Result,
)

from . import comparison as comparison_lib
from .classifiers import get_predictor
from .config_worker import build_worker_cfg
from .model_registry import get_active, sync_registry

logger = logging.getLogger("worker.tasks")

PROGRESS_CHUNK = 250  # nb de verbatims entre deux mises à jour de progression
# Moteur LM Studio : appels LLM lents (~1/verbatim) -> commits plus fréquents pour
# une progression visible et une annulation réactive.
LMSTUDIO_PROGRESS_CHUNK = 20


def ping() -> dict:
    return {"pong": True, "python": platform.python_version(), "arch": platform.machine(),
            "models_dir": os.environ.get("MODELS_DIR", "/data/models")}


def sync_registry_job() -> dict:
    cfg = build_worker_cfg()
    sync_registry(cfg)
    return {"status": "synced"}


def purge_old_data_job() -> dict:
    """Purge RGPD des lots au-delà de la rétention (lue dans app_config)."""
    from common.models import AppConfig
    from common.retention import purge_old_batches

    with SessionLocal() as db:
        cfg = db.get(AppConfig, "retention_months")
        months = int(float(cfg.value)) if cfg else 13
        return purge_old_batches(db, months, uploads_dir=os.environ.get("UPLOADS_DIR", "/data/uploads"))


def reconcile_orphan_batches() -> dict:
    """Au démarrage du worker : un lot resté 'running' = job interrompu (worker
    tombé). On le repasse en 'failed' avec un message clair. Les lots 'pending'
    restent en file (RQ les rejoue). Évite les lots « en cours » fantômes (§8)."""
    with SessionLocal() as db:
        orphans = db.query(Batch).filter(Batch.status == "running").all()
        for b in orphans:
            b.status = "failed"
            b.error_message = "Traitement interrompu (redémarrage du worker)."
            b.finished_at = _now()
        n = len(orphans)
        if n:
            db.commit()
        return {"reconciled": n}


def predict_one_job(text: str, satisfaction=None, model_id=None) -> dict:
    """Prédiction unitaire (test à la volée). Renvoie le dict de sortie.

    ``model_id`` (V5) : moteur explicite à utiliser (sélecteur du Test à la volée) ;
    None -> modèle actif. Permet de tester un moteur de comparaison (ex. Claude)
    sans changer le modèle de production. Un moteur indisponible retombe sur l'actif.
    """
    from common.models import ModelVersion

    cfg = build_worker_cfg()
    with SessionLocal() as db:
        chosen = None
        if model_id is not None:
            chosen = db.get(ModelVersion, int(model_id))
            if chosen is not None and not chosen.available:
                chosen = None                      # moteur indisponible -> repli sur l'actif
        if chosen is None:
            chosen = get_active(db)
        label = chosen.label if chosen else None
    predictor = get_predictor(chosen, cfg)
    masked, _ = predictor.anonymizer.anonymize(text or "")
    cleaned = predictor.cleaner.clean(masked)
    result = predictor.predict_cleaned_batch([cleaned], [satisfaction])[0]
    result["model_label"] = label
    return result


def _now():
    return datetime.now(timezone.utc)


def _jsonable(value):
    """Convertit une valeur pandas/numpy en type JSON-sérialisable."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value
    # Timestamps, numpy scalars, etc.
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    return str(value)


def _to_result(batch_id: int, gidx: int, source, pred: dict, original: dict) -> Result:
    def _s(key):
        v = pred.get(key)
        return v if v not in ("", None) else None

    return Result(
        batch_id=batch_id, row_index=int(gidx), source=source,
        verbatim_analyse=pred.get("verbatim_analysé", ""),
        nb_themes=int(pred.get("nb_themes", 0)),
        theme1_niv1=_s("theme1_niv1"), theme1_niv2=_s("theme1_niv2"),
        theme1_sentiment=_s("theme1_sentiment"),
        theme1_score=pred.get("theme1_score_confiance") or None,
        theme2_niv1=_s("theme2_niv1"), theme2_niv2=_s("theme2_niv2"),
        theme2_sentiment=_s("theme2_sentiment"),
        theme2_score=(pred.get("theme2_score_confiance") or None) if pred.get("theme2_score_confiance") not in ("", None) else None,
        signal_rupture=bool(pred.get("signal_rupture_client", False)),
        signal_churn=bool(pred.get("signal_churn", False)),
        signal_insatisfaction=bool(pred.get("signal_insatisfaction_forte", False)),
        confidence_globale=pred.get("confidence_globale"),
        revue_requise=bool(pred.get("revue_humaine_requise", False)),
        original_columns=original,
    )


def merge_cascade(proposal: dict, refined: dict) -> tuple[dict, bool]:
    """Cascade V5 : la sortie du raffineur FAIT FOI ; désaccord theme1_niv1 -> revue forcée.

    Renvoie (sortie_finale, désaccord). Fonction pure (cf. SPEC_V5 §6, V5-D5/D6) :
    le critère de désaccord est le grand thème ``theme1_niv1`` uniquement (V5-D6).
    """
    disagree = (proposal.get("theme1_niv1") or "") != (refined.get("theme1_niv1") or "")
    out = dict(refined)
    if disagree:
        out["revue_humaine_requise"] = True   # revue humaine forcée (le 2e moteur arbitre, l'humain tranche)
    return out, disagree


def _to_engine_pred(batch_id, result_id, row_index, engine_label, role, pred, latency_ms):
    """Construit une ligne engine_predictions à partir d'un dict de sortie (OUTPUT_COLUMNS)."""
    return EnginePrediction(
        batch_id=batch_id, result_id=result_id, row_index=int(row_index),
        engine_label=engine_label, role=role,
        theme1_niv1=pred.get("theme1_niv1") or None,
        theme1_niv2=pred.get("theme1_niv2") or None,
        theme1_sentiment=pred.get("theme1_sentiment") or None,
        confidence_globale=pred.get("confidence_globale"),
        signal_rupture=bool(pred.get("signal_rupture_client", False)),
        signal_churn=bool(pred.get("signal_churn", False)),
        signal_insatisfaction=bool(pred.get("signal_insatisfaction_forte", False)),
        latency_ms=latency_ms,
    )


def process_batch_job(batch_id: int) -> dict:
    """Traite un lot complet et persiste les résultats. Renvoie un résumé."""
    from src.preprocessing.loader import COL_SATISFACTION, COL_SOURCE, COL_TEXT, load_for_batch

    cfg = build_worker_cfg()
    with SessionLocal() as db:
        batch = db.get(Batch, batch_id)
        if batch is None:
            logger.error("Lot %s introuvable.", batch_id)
            return {"status": "missing"}
        if batch.status == "canceled":  # annulé avant la prise en charge
            logger.info("Lot %s annulé avant démarrage — ignoré.", batch_id)
            return {"status": "canceled"}

        active = get_active(db)
        cfg["thresholds"]["revue_humaine"] = batch.seuil_revue
        started = _now()
        batch.status = "running"
        batch.started_at = started
        batch.model_label = active.label if active else None
        db.commit()
        logger.info("Lot %s : démarrage (modèle=%s)", batch_id, batch.model_label)

        try:
            predictor = get_predictor(active, cfg)

            # --- Cascade V5 (opt-in) : résolution du raffineur (2e moteur LLM) -----
            # refiner_label = NULL -> pipeline V4 strictement inchangé (branche else plus bas).
            refiner_predictor = None
            refiner_label = batch.refiner_label
            if refiner_label:
                refiner_model = db.query(ModelVersion).filter_by(label=refiner_label).one_or_none()
                # Garde-fou (défense en profondeur, déjà validé à la création) : le raffineur
                # DOIT être un moteur LLM local. Claude (offline strict) et real/stub (pas de
                # refine_cleaned_batch) sont exclus -> échec propre du lot.
                if refiner_model is None or not refiner_model.available or refiner_model.kind != MODEL_KIND_LMSTUDIO:
                    raise RuntimeError(
                        f"Raffineur invalide ({refiner_label}) : un moteur LLM local (LM Studio) "
                        "disponible est requis (Claude et CamemBERT/stub sont exclus de la cascade).")
                refiner_predictor = get_predictor(refiner_model, cfg)
                batch.model_label = f"{batch.model_label} ▶ {refiner_model.label}"
                batch.chain_disagreements = 0
                db.commit()
                logger.info("Lot %s : cascade %s ▶ %s", batch_id, active.label if active else "?", refiner_label)

            # Granularité de progression : LLM (proposeur OU raffineur) = commits fréquents.
            llm_in_chain = (active is not None and active.kind == "lmstudio") or (refiner_predictor is not None)
            chunk = LMSTUDIO_PROGRESS_CHUNK if llm_in_chain else PROGRESS_CHUNK
            files = batch.source_files or {}
            df = load_for_batch(files.get("mdtc"), files.get("mopinion"), cfg)
            total = len(df)
            batch.n_total = total
            db.commit()

            texts = df[COL_TEXT].tolist() if COL_TEXT in df.columns else [""] * total
            sats = df[COL_SATISFACTION].tolist() if COL_SATISFACTION in df.columns else [None] * total
            orig_cols = [c for c in df.columns if not str(c).startswith("__")]

            pii = Counter()
            n_review = 0
            n_err = 0

            for start in range(0, total, chunk):
                # Annulation coopérative : l'API a pu passer le lot en 'canceled'
                # (requête fraîche, hors cache de session).
                if db.query(Batch.status).filter(Batch.id == batch_id).scalar() == "canceled":
                    batch.status = "canceled"
                    batch.n_processed = start
                    batch.n_review = n_review
                    batch.n_errors = n_err
                    batch.pii_masked = dict(pii)
                    batch.finished_at = _now()
                    db.commit()
                    logger.info("Lot %s annulé en cours (%d/%d traités).", batch_id, start, total)
                    return {"status": "canceled", "n_processed": start}
                rows = df.iloc[start:start + chunk]
                raw_chunk = texts[start:start + chunk]
                sat_chunk = sats[start:start + chunk]

                cleaned = []
                for raw in raw_chunk:
                    try:
                        masked, counts = predictor.anonymizer.anonymize(raw)
                        pii.update(counts)
                        cleaned.append(predictor.cleaner.clean(masked))
                    except Exception as exc:  # un verbatim défaillant n'arrête pas le lot
                        logger.warning("Prétraitement KO (lot %s, ligne %s) : %s", batch_id, start, exc)
                        cleaned.append("")
                        n_err += 1

                if refiner_predictor is None:
                    # --- Pipeline V4 (mono-moteur) : INCHANGÉ ------------------------
                    preds = predictor.predict_cleaned_batch(cleaned, sat_chunk)
                    for i, pred in enumerate(preds):
                        gidx = start + i
                        row = rows.iloc[i]
                        original = {c: _jsonable(row[c]) for c in orig_cols}
                        db.add(_to_result(batch_id, gidx, _jsonable(row.get(COL_SOURCE)), pred, original))
                        if pred.get("revue_humaine_requise"):
                            n_review += 1
                else:
                    # --- Cascade V5 : proposeur -> raffineur (sortie raffineur = foi) -
                    t0 = time.monotonic()
                    proposals = predictor.predict_cleaned_batch(cleaned, sat_chunk)
                    prop_ms = (time.monotonic() - t0) * 1000 / max(1, len(cleaned))
                    t1 = time.monotonic()
                    refined = refiner_predictor.refine_cleaned_batch(cleaned, sat_chunk, proposals)
                    ref_ms = (time.monotonic() - t1) * 1000 / max(1, len(cleaned))

                    proposer_label = (batch.model_label or "").split(" ▶ ")[0]
                    chunk_meta = []   # (result, proposal, refiner_pred, gidx)
                    for i, prop in enumerate(proposals):
                        gidx = start + i
                        row = rows.iloc[i]
                        original = {c: _jsonable(row[c]) for c in orig_cols}
                        final, disagree = merge_cascade(prop, refined[i])
                        if disagree:
                            batch.chain_disagreements = (batch.chain_disagreements or 0) + 1
                        result = _to_result(batch_id, gidx, _jsonable(row.get(COL_SOURCE)), final, original)
                        db.add(result)
                        if final.get("revue_humaine_requise"):
                            n_review += 1
                        chunk_meta.append((result, prop, refined[i], gidx))
                    db.flush()   # assigne les result.id pour rattacher les engine_predictions
                    for result, prop, ref_pred, gidx in chunk_meta:
                        db.add(_to_engine_pred(batch_id, result.id, gidx, proposer_label,
                                               ENGINE_ROLE_PROPOSER, prop, prop_ms))
                        db.add(_to_engine_pred(batch_id, result.id, gidx, refiner_label,
                                               ENGINE_ROLE_REFINER, ref_pred, ref_ms))

                batch.n_processed = min(start + chunk, total)
                db.commit()

            finished = _now()
            batch.status = "done"
            batch.finished_at = finished
            batch.n_review = n_review
            batch.n_errors = n_err
            batch.pii_masked = dict(pii)
            batch.duration_s = (finished - started).total_seconds()
            db.commit()
            logger.info("Lot %s terminé : %d traités, %d en revue, %d erreurs.", batch_id, total, n_review, n_err)
            return {"status": "done", "n_total": total, "n_review": n_review, "n_errors": n_err}

        except Exception as exc:
            logger.exception("Lot %s en échec : %s", batch_id, exc)
            db.rollback()
            batch = db.get(Batch, batch_id)
            if batch:
                batch.status = "failed"
                batch.error_message = str(exc)[:1000]
                batch.finished_at = _now()
                db.commit()
            return {"status": "failed", "error": str(exc)}


# --------------------------------------------------------------------------- #
#  Comparaison de moteurs (V5, lot C4) — replay objectif d'un échantillon
# --------------------------------------------------------------------------- #
def _satisfaction_from_original(original) -> "float | None":
    """Best-effort : récupère la satisfaction depuis original_columns (clé ~ 'satisf').

    La satisfaction n'est pas stockée en colonne dédiée (SPEC_V5 §14) : on tente une
    clé d'origine contenant « satisf », sinon None (n'affecte pas la prod).
    """
    if not isinstance(original, dict):
        return None
    for k, v in original.items():
        if "satisf" in str(k).lower():
            return v
    return None


def _to_engine_pred_compare(run_id, result_id, row_index, engine_label, pred, latency_ms):
    """Ligne engine_predictions pour un run de comparaison (rôle 'compare')."""
    ep = _to_engine_pred(None, result_id, row_index, engine_label, ENGINE_ROLE_COMPARE, pred, latency_ms)
    ep.comparison_run_id = run_id
    return ep


def _classif_str(niv1, niv2, sentiment) -> str:
    """Libellé lisible d'une classification, pour le prompt du juge et l'affichage."""
    n1 = niv1 or "(non classé)"
    n2 = f" / {niv2}" if niv2 else ""
    s = f" (sentiment {sentiment})" if sentiment else ""
    return f"{n1}{n2}{s}"


_MAX_JUDGE_CALLS = 200   # garde-fou coût : plafond dur d'appels au juge par run


def _run_judge_phase(db, run, sample, texts, engines, theme_by, niv2_by, sent_by, cfg) -> dict:
    """Juge Claude (C5) sur les divergences : aveuglé + ordre A/B permuté (V5-D11).

    Pour chaque verbatim où ≥2 moteurs divergent sur ``theme1_niv1``, fait juger chaque
    paire en désaccord par Claude (A/B anonymes). Le mapping A/B -> moteur réel est
    reconstruit ici (la permutation est connue du worker, pas du juge). Agrège un
    win-rate par moteur. Échec propre (ClaudeError) -> remonte et fait échouer le run.
    """
    from .claude_predictor import ClaudePredictor

    judge = ClaudePredictor(cfg)
    rng = random.Random((run.seed or 0) + 1)   # permutation reproductible mais décorrélée du tirage
    div = comparison_lib.divergent_indices(theme_by)
    wins = {e: 0 for e in engines}
    duels = {e: 0 for e in engines}
    n_judged, n_ties = 0, 0
    capped = False

    for k in div:
        if n_judged >= _MAX_JUDGE_CALLS:
            capped = True
            break
        if db.query(ComparisonRun.status).filter(ComparisonRun.id == run.id).scalar() == "canceled":
            break
        for i in range(len(engines)):
            for j in range(i + 1, len(engines)):
                ea, eb = engines[i], engines[j]
                if (theme_by[ea][k] or "") == (theme_by[eb][k] or ""):
                    continue   # ces deux moteurs sont d'accord sur ce verbatim
                if n_judged >= _MAX_JUDGE_CALLS:
                    capped = True
                    break
                ca = _classif_str(theme_by[ea][k], niv2_by[ea][k], sent_by[ea][k])
                cb = _classif_str(theme_by[eb][k], niv2_by[eb][k], sent_by[eb][k])
                # Aveuglement + permutation aléatoire de l'ordre A/B (V5-D11).
                if rng.random() < 0.5:
                    a_eng, b_eng, a_c, b_c = ea, eb, ca, cb
                else:
                    a_eng, b_eng, a_c, b_c = eb, ea, cb, ca
                verdict = judge.judge_pairwise(texts[k], a_c, b_c)   # {winner: A|B|tie, rationale}
                w = verdict["winner"]
                winner_db = "a" if w == "A" else "b" if w == "B" else "tie"
                db.add(JudgeVerdict(
                    comparison_run_id=run.id, result_id=sample[k].id, row_index=sample[k].row_index,
                    engine_a=a_eng, engine_b=b_eng, classif_a=a_c[:200], classif_b=b_c[:200],
                    winner=winner_db, rationale=verdict["rationale"]))
                duels[a_eng] += 1
                duels[b_eng] += 1
                if w == "A":
                    wins[a_eng] += 1
                elif w == "B":
                    wins[b_eng] += 1
                else:
                    n_ties += 1
                n_judged += 1
        db.commit()

    if capped:
        logger.warning("Comparaison %s : juge plafonné à %d duels (divergences non toutes jugées).",
                       run.id, _MAX_JUDGE_CALLS)
    win_rate = {e: round(wins[e] / duels[e], 4) if duels[e] else 0.0 for e in engines}
    return {"win_rate": win_rate, "wins": wins, "n_judged": n_judged, "n_ties": n_ties, "capped": capped}


def run_comparison_job(run_id: int) -> dict:
    """Rejoue un échantillon d'un lot à travers 2-3 moteurs et calcule les métriques.

    Objectif uniquement (accord/confiance/latence) ; le juge Claude est ajouté en C5.
    Asynchrone, annulation coopérative (comme un lot). Rejoue ``verbatim_analyse``
    (déjà anonymisé + nettoyé) -> aucune nouvelle anonymisation.
    """
    cfg = build_worker_cfg()
    with SessionLocal() as db:
        run = db.get(ComparisonRun, run_id)
        if run is None:
            logger.error("Run de comparaison %s introuvable.", run_id)
            return {"status": "missing"}
        if run.status == "canceled":
            return {"status": "canceled"}
        run.status = "running"
        db.commit()
        engines = list(run.engine_labels or [])
        logger.info("Comparaison %s : lot=%s moteurs=%s n=%s", run_id, run.batch_id, engines, run.sample_size)

        try:
            results = (db.query(Result).filter_by(batch_id=run.batch_id)
                       .order_by(Result.row_index).all())
            if not results:
                raise RuntimeError("Lot sans résultats à comparer.")
            idx = comparison_lib.sample_indices(len(results), run.sample_size, run.seed)
            sample = [results[i] for i in idx]
            texts = [r.verbatim_analyse or "" for r in sample]
            sats = [_satisfaction_from_original(r.original_columns) for r in sample]

            theme_by, niv2_by, conf_by, sent_by, lat_by = {}, {}, {}, {}, {}
            for label in engines:
                if db.query(ComparisonRun.status).filter(ComparisonRun.id == run_id).scalar() == "canceled":
                    run.status = "canceled"
                    db.commit()
                    logger.info("Comparaison %s annulée en cours.", run_id)
                    return {"status": "canceled"}
                model = db.query(ModelVersion).filter_by(label=label).one_or_none()
                if model is None or not model.available:
                    raise RuntimeError(f"Moteur indisponible pour la comparaison : {label}")
                predictor = get_predictor(model, cfg)
                t0 = time.monotonic()
                preds = predictor.predict_cleaned_batch(texts, sats)
                lat_by[label] = (time.monotonic() - t0) * 1000 / max(1, len(texts))
                theme_by[label] = [p.get("theme1_niv1") or "" for p in preds]
                niv2_by[label] = [p.get("theme1_niv2") or "" for p in preds]
                conf_by[label] = [p.get("confidence_globale") for p in preds]
                sent_by[label] = [p.get("theme1_sentiment") or "" for p in preds]
                for i, p in enumerate(preds):
                    db.add(_to_engine_pred_compare(run_id, sample[i].id, sample[i].row_index, label, p, lat_by[label]))
                db.commit()

            metrics = comparison_lib.build_metrics(theme_by, conf_by, sent_by, lat_by, len(sample))

            # --- Juge Claude (C5) : seulement si demandé ET clé présente (sinon mode dégradé)
            if run.judge_enabled and (cfg.get("claude", {}) or {}).get("api_key_present"):
                metrics["judge"] = _run_judge_phase(db, run, sample, texts, engines, theme_by, niv2_by, sent_by, cfg)
            elif run.judge_enabled:
                logger.info("Comparaison %s : juge demandé mais clé Claude absente -> mode dégradé.", run_id)

            run.metrics = metrics
            run.status = "done"
            db.commit()
            logger.info("Comparaison %s terminée (%d verbatims, %d moteurs, juge=%s).",
                        run_id, len(sample), len(engines), bool(metrics.get("judge")))
            return {"status": "done", "sample": len(sample), "engines": engines}

        except Exception as exc:
            logger.exception("Comparaison %s en échec : %s", run_id, exc)
            db.rollback()
            run = db.get(ComparisonRun, run_id)
            if run:
                run.status = "failed"
                run.error_message = str(exc)[:1000]
                db.commit()
            return {"status": "failed", "error": str(exc)}
