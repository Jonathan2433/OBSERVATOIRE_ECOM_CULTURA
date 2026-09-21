"""Non-régression de la satisfaction à la maille répondant."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "app" / "api"), str(ROOT / "app"), str(ROOT)]
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'satisfaction.db'}"

from common.db import Base, SessionLocal, engine  # noqa: E402
from common.models import Batch, Result, SurveyResponse  # noqa: E402
from app.api.routes_kpi import (  # noqa: E402
    _classification_evolution, _comparison, _default_reference_batch,
    _satisfaction, batch_kpi,
)
from worker.tasks import _persist_survey_responses  # noqa: E402
from src.preprocessing.cultura_loader import (  # noqa: E402
    lire_satisfaction, normaliser_statut_client, opaque_respondent_key,
)
import pandas as pd  # noqa: E402


class SatisfactionRespondentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(engine)

    def setUp(self) -> None:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

    def test_native_scales_deduplication_segments_and_completed_scope(self) -> None:
        with SessionLocal() as db:
            done = Batch(label="terminé", status="done", n_total=7, n_processed=7)
            running = Batch(label="en cours", status="running", n_total=1, n_processed=0)
            old = Batch(label="historique", status="done", n_total=1, n_processed=1)
            db.add_all([done, running, old])
            db.flush()

            def response(source, key, native, scale, status="non_renseigne", invalid=False,
                         batch_id=None):
                row = SurveyResponse(
                    batch_id=batch_id or done.id, source_type=source,
                    source_file=f"{source}.csv", respondent_key=key,
                    satisfaction_native=native, satisfaction_scale_max=scale,
                    satisfaction_normalized=native if scale == 4 else ({1: 1, 2: 2, 3: 2, 4: 3, 5: 4}.get(native)),
                    rating_invalid=invalid, client_status=status,
                )
                db.add(row)
                db.flush()
                return row

            mdtc_achat = response("MDTC-postachat", "a", 3, 4, "ancien")
            response("MDTC-postrecep", "b", None, 4, "nouveau")
            mopinion = response("Mopinion-desktop", "c", 3, 5)
            response("Mopinion-mobile", "d", 9, 5, invalid=True)
            response("Mopinion-mobile", "e", None, 5)
            # Ce répondant ne doit jamais entrer dans le KPI global tant que son lot
            # n'est pas terminé.
            response("Mopinion-desktop", "running", 5, 5, batch_id=running.id)

            common = dict(verbatim_analyse="x", nb_themes=1, source="Mopinion-desktop")
            db.add_all([
                Result(batch_id=done.id, survey_response_id=mopinion.id, row_index=i, **common)
                for i in range(3)
            ])
            db.add(Result(batch_id=done.id, survey_response_id=mdtc_achat.id,
                          row_index=3, source="MDTC-postachat", verbatim_analyse="x"))
            # Ancien lot : la valeur normalisée ne permet pas de reconstruire la
            # note native Mopinion ni le répondant.
            db.add(Result(batch_id=old.id, row_index=0, source="MDTC",
                          satisfaction=2, verbatim_analyse="historique"))
            db.commit()

            batch_kpi = _satisfaction(db, done.id)
            sources = {s["source_type"]: s for s in batch_kpi["by_source"]}

            self.assertEqual(batch_kpi["unit"], "respondent")
            self.assertEqual(batch_kpi["display_scale_max"], 10)
            self.assertEqual(sources["Mopinion-desktop"]["respondent_count"], 1)
            self.assertEqual(sources["Mopinion-desktop"]["rated_respondent_count"], 1)
            self.assertEqual(sources["Mopinion-desktop"]["mean_on_10"], 6.0)
            self.assertEqual(sources["MDTC-postachat"]["mean_on_10"], 7.5)
            self.assertEqual(sources["Mopinion-mobile"]["invalid_rating_count"], 1)
            self.assertEqual(sources["Mopinion-mobile"]["unrated_respondent_count"], 1)
            self.assertIsNone(sources["Mopinion-mobile"]["mean_on_10"])

            for source in sources.values():
                if source["respondent_count"] is not None:
                    self.assertEqual(
                        sum(s["respondent_count"] for s in source["by_client_status"]),
                        source["respondent_count"],
                    )

            global_kpi = _satisfaction(db, None)
            global_sources = {s["source_type"]: s for s in global_kpi["by_source"]}
            self.assertTrue({
                "MDTC-postachat", "MDTC-postrecep", "Mopinion-desktop", "Mopinion-mobile",
            }.issubset(global_sources))
            self.assertEqual(global_kpi["global"]["rated_respondent_count"], 2)
            self.assertEqual(global_kpi["global"]["mean_on_10"], 6.75)
            self.assertEqual(global_sources["Mopinion-desktop"]["respondent_count"], 1)
            self.assertFalse(global_sources["MDTC"]["native_detail_available"])
            self.assertIsNone(global_sources["MDTC"]["mean_on_10"])
            self.assertTrue(global_kpi["historical_data_unavailable"])

    def test_worker_creates_one_response_for_three_verbatims(self) -> None:
        with SessionLocal() as db:
            batch = Batch(label="multi-verbatim", status="running")
            db.add(batch)
            db.flush()
            common = {
                "__source__": "Mopinion-desktop",
                "__fichier__": "mopinion.csv",
                "__respondent_id__": "opaque-key",
                "__satisfaction_native__": 3,
                "__satisfaction_scale_max__": 5,
                "__satisfaction__": 2,
                "__satisfaction_invalid__": False,
                "__satisfaction_raw__": "3",
                "__client_status__": "non_renseigne",
                "__date__": "2026-09-12T10:30:00",
            }
            frame = pd.DataFrame([
                {**common, "__text_raw__": "premier champ"},
                {**common, "__text_raw__": "deuxième champ"},
                {**common, "__text_raw__": "troisième champ"},
            ])
            response_ids = _persist_survey_responses(db, batch.id, frame)
            self.assertEqual(len(set(response_ids.values())), 1)
            self.assertEqual(db.query(SurveyResponse).count(), 1)
            row = db.query(SurveyResponse).one()
            self.assertEqual((row.satisfaction_native, row.satisfaction_scale_max), (3, 5))
            self.assertEqual(row.response_date, date(2026, 9, 12))

    def test_worker_keeps_legacy_dataframe_without_respondent_contract(self) -> None:
        with SessionLocal() as db:
            batch = Batch(label="import historique", status="running")
            db.add(batch)
            db.flush()
            frame = pd.DataFrame({
                "__text_raw__": ["colis cassé", "site lent"],
                "__source__": ["MDTC", "Mopinion"],
                "__satisfaction__": [2, 4],
            })

            response_ids = _persist_survey_responses(db, batch.id, frame)

            self.assertEqual(response_ids, {})
            self.assertEqual(db.query(SurveyResponse).count(), 0)

    def test_loader_keeps_native_rating_and_never_infers_client_status(self) -> None:
        scale = {"valeurs_attendues": [1, 2, 3, 4, 5],
                 "conversion": {1: 1, 2: 2, 3: 2, 4: 3, 5: 4}}
        self.assertEqual(lire_satisfaction("3", scale), (3, 2, "3", False))
        self.assertEqual(lire_satisfaction("", scale), (None, None, "", False))
        self.assertEqual(lire_satisfaction("9", scale), (None, None, "9", True))
        mappings = {"ancien": ["ancien"], "nouveau": ["nouveau"]}
        self.assertEqual(normaliser_statut_client("Ancien", mappings), "ancien")
        self.assertEqual(normaliser_statut_client("VIP", mappings), "non_renseigne")
        key = opaque_respondent_key("Mopinion-mobile", "a.csv", "source-id-42")
        self.assertNotIn("source-id-42", key)
        self.assertNotEqual(key, opaque_respondent_key("Mopinion-mobile", "b.csv", "source-id-42"))

    def test_contradictory_native_ratings_are_invalid_even_if_ml_value_matches(self) -> None:
        with SessionLocal() as db:
            batch = Batch(label="contradiction", status="running")
            db.add(batch)
            db.flush()
            common = {
                "__source__": "Mopinion-mobile", "__fichier__": "mobile.csv",
                "__respondent_id__": "same-source-id", "__satisfaction_scale_max__": 5,
                "__satisfaction__": 2, "__satisfaction_invalid__": False,
                "__client_status__": "non_renseigne",
            }
            frame = pd.DataFrame([
                {**common, "__satisfaction_native__": 2},
                {**common, "__satisfaction_native__": 3},
            ])
            _persist_survey_responses(db, batch.id, frame)
            response = db.query(SurveyResponse).one()
            self.assertTrue(response.rating_invalid)
            self.assertIsNone(response.satisfaction_native)
            self.assertIsNone(response.satisfaction_normalized)

    def test_comparison_uses_business_period_and_returns_delta_on_ten(self) -> None:
        with SessionLocal() as db:
            reference = Batch(
                label="août 2026", status="done", n_total=1, n_processed=1,
                model_label="cultura_2026", seuil_revue=0.7,
            )
            current = Batch(
                label="septembre 2026", status="done", n_total=1, n_processed=1,
                model_label="cultura_2026", seuil_revue=0.7,
            )
            # Ce retraitement chevauche septembre et ne doit pas devenir la
            # référence automatique, même s'il a un id plus récent.
            overlap = Batch(
                label="retraitement septembre", status="done", n_total=1, n_processed=1,
                model_label="cultura_2026", seuil_revue=0.7,
            )
            db.add_all([reference, current, overlap])
            db.flush()

            db.add_all([
                SurveyResponse(
                    batch_id=reference.id, source_type="MDTC-postrecep", source_file="a.csv",
                    respondent_key="ref", response_date=date(2026, 8, 15),
                    satisfaction_native=3, satisfaction_scale_max=4,
                    satisfaction_normalized=3, client_status="ancien",
                ),
                SurveyResponse(
                    batch_id=current.id, source_type="MDTC-postrecep", source_file="b.csv",
                    respondent_key="cur", response_date=date(2026, 9, 15),
                    satisfaction_native=4, satisfaction_scale_max=4,
                    satisfaction_normalized=4, client_status="ancien",
                ),
                SurveyResponse(
                    batch_id=overlap.id, source_type="MDTC-postrecep", source_file="c.csv",
                    respondent_key="overlap", response_date=date(2026, 9, 15),
                    satisfaction_native=2, satisfaction_scale_max=4,
                    satisfaction_normalized=2, client_status="ancien",
                ),
            ])
            for batch in (reference, current, overlap):
                db.add(Result(
                    batch_id=batch.id, row_index=0, source="MDTC-postrecep",
                    verbatim_analyse="x", nb_themes=1, theme1_niv1="Général",
                ))
            db.commit()

            automatic = _default_reference_batch(db, current)
            self.assertIsNotNone(automatic)
            self.assertEqual(automatic.id, reference.id)

            comparison = _comparison(db, current, reference)
            source = next(
                item for item in comparison["satisfaction"]["by_source"]
                if item["source_type"] == "MDTC-postrecep"
            )
            self.assertTrue(source["comparable"])
            self.assertEqual(source["current_mean_on_10"], 10.0)
            self.assertEqual(source["reference_mean_on_10"], 7.5)
            self.assertEqual(source["delta_on_10"], 2.5)
            self.assertEqual(source["current_period"]["start"], "2026-09-15")
            self.assertEqual(source["reference_period"]["end"], "2026-08-15")
            self.assertTrue(comparison["lot_metrics"]["review_rate"]["comparable"])

            payload = batch_kpi(current.id, reference.id, db)
            self.assertEqual(payload["comparison"]["reference_mode"], "explicit")
            self.assertEqual(payload["comparison"]["reference_batch"]["id"], reference.id)

    def test_bi_theme_comparison_uses_classified_results_as_denominator(self) -> None:
        with SessionLocal() as db:
            reference = Batch(
                label="référence", status="done", n_total=2, n_processed=2,
                model_label="cultura_2026",
            )
            current = Batch(
                label="courant", status="done", n_total=2, n_processed=2,
                model_label="cultura_2026",
            )
            db.add_all([reference, current])
            db.flush()
            db.add_all([
                # Un résultat classé sur deux dans chaque lot : le second est
                # volontairement hors dénominateur métier.
                Result(
                    batch_id=reference.id, row_index=0, source="MDTC-postrecep",
                    verbatim_analyse="x", theme1_niv1="Général",
                ),
                Result(
                    batch_id=reference.id, row_index=1, source="MDTC-postrecep",
                    verbatim_analyse="vide",
                ),
                Result(
                    batch_id=current.id, row_index=0, source="MDTC-postrecep",
                    verbatim_analyse="x", theme1_niv1="Général",
                    theme2_niv1="Livraison",
                ),
                Result(
                    batch_id=current.id, row_index=1, source="MDTC-postrecep",
                    verbatim_analyse="vide",
                ),
            ])
            db.commit()

            metric = _comparison(db, current, reference)["lot_metrics"]["bi_theme_rate"]
            self.assertEqual(metric["current"], 1.0)
            self.assertEqual(metric["reference"], 0.0)
            self.assertEqual(metric["delta"], 1.0)
            self.assertEqual(batch_kpi(current.id, reference.id, db)["taux_bi_themes"], 1.0)

    def test_comparison_without_source_date_is_explicitly_unavailable(self) -> None:
        with SessionLocal() as db:
            reference = Batch(label="référence", status="done", n_total=1, n_processed=1)
            current = Batch(label="courant", status="done", n_total=1, n_processed=1)
            db.add_all([reference, current])
            db.flush()
            for batch, key, native in ((reference, "r", 3), (current, "c", 4)):
                db.add(SurveyResponse(
                    batch_id=batch.id, source_type="MDTC-postachat", source_file="x.csv",
                    respondent_key=key, response_date=None,
                    satisfaction_native=native, satisfaction_scale_max=4,
                    satisfaction_normalized=native, client_status="non_renseigne",
                ))
            db.commit()

            source = next(
                item for item in _comparison(db, current, reference)["satisfaction"]["by_source"]
                if item["source_type"] == "MDTC-postachat"
            )
            self.assertFalse(source["comparable"])
            self.assertIn("Période métier indisponible", source["reason"])
            self.assertIsNone(_default_reference_batch(db, current))

    def test_classification_evolution_counts_verbatims_shares_and_ranks(self) -> None:
        with SessionLocal() as db:
            reference = Batch(
                label="août", status="done", n_total=3, n_processed=3,
                model_label="cultura_2026",
            )
            current = Batch(
                label="septembre", status="done", n_total=5, n_processed=5,
                model_label="cultura_2026",
            )
            db.add_all([reference, current])
            db.flush()

            def result(batch, index, theme1, sub1, theme2=None, sub2=None):
                return Result(
                    batch_id=batch.id, row_index=index, source="MDTC-postachat",
                    verbatim_analyse="x", theme1_niv1=theme1, theme1_niv2=sub1,
                    theme2_niv1=theme2, theme2_niv2=sub2,
                )

            db.add_all([
                result(reference, 0, "Commande", "Paiement"),
                result(reference, 1, "Commande", "Paiement"),
                result(reference, 2, "Livraison", "Délai"),
                result(current, 0, "Livraison", "Délai"),
                result(current, 1, "Livraison", "Délai", "Commande", "Paiement"),
                result(current, 2, "Livraison", "Délai", "Livraison", "Délai"),
                result(current, 3, "Produit", "État produit"),
                Result(
                    batch_id=current.id, row_index=4, source="Mopinion-mobile",
                    verbatim_analyse="x", theme1_niv1="Commande", theme1_niv2="Paiement",
                ),
            ])
            db.commit()

            evolution = _classification_evolution(db, current, reference)
            self.assertTrue(evolution["comparable"])
            source = evolution["levels"]["niv2"][0]
            self.assertEqual(source["current_verbatim_count"], 4)
            self.assertEqual(source["reference_verbatim_count"], 3)
            items = {item["label"]: item for item in source["items"]}

            # Le même sous-thème en positions 1 et 2 ne double-compte pas le
            # verbatim ; Délai est donc présent sur 3 verbatims sur 4.
            self.assertEqual(items["Délai"]["current_count"], 3)
            self.assertEqual(items["Délai"]["current_share"], 0.75)
            self.assertEqual(items["Délai"]["reference_rank"], 2)
            self.assertEqual(items["Délai"]["rank_delta"], 1)
            self.assertEqual(items["Paiement"]["count_delta"], -1)
            self.assertAlmostEqual(items["Paiement"]["share_delta"], -0.416667)

            mopinion = next(
                row for row in evolution["levels"]["niv2"]
                if row["source_type"] == "Mopinion-mobile"
            )
            self.assertFalse(mopinion["comparable"])
            self.assertIn("Source absente", mopinion["reason"])
            self.assertIsNone(mopinion["items"][0]["share_delta"])

            payload = batch_kpi(current.id, reference.id, db)
            self.assertEqual(payload["classification_evolution"]["unit"], "verbatim")
            self.assertEqual(payload["classification_evolution"]["top_n"], 5)

            reference.model_label = "autre_modele"
            db.commit()
            incompatible = _classification_evolution(db, current, reference)
            self.assertFalse(incompatible["comparable"])
            self.assertIn("référentiel diffère", incompatible["reason"])
            self.assertIsNone(
                incompatible["levels"]["niv2"][0]["items"][0]["share_delta"])

    def test_missing_sources_and_zero_client_segments_remain_visible(self) -> None:
        with SessionLocal() as db:
            batch = Batch(
                label="lot incomplet", status="done", n_total=1, n_processed=1,
                model_label="cultura_2026",
            )
            db.add(batch)
            db.flush()
            response = SurveyResponse(
                batch_id=batch.id, source_type="MDTC-postachat",
                source_file="postachat-anciens.csv", respondent_key="ancien-1",
                response_date=date(2026, 9, 15), satisfaction_native=3,
                satisfaction_scale_max=4, satisfaction_normalized=3,
                client_status="ancien",
            )
            db.add(response)
            db.flush()
            db.add(Result(
                batch_id=batch.id, survey_response_id=response.id, row_index=0,
                source="MDTC-postachat", verbatim_analyse="x",
                theme1_niv1="Commande", theme1_niv2="Paiement",
            ))
            db.commit()

            satisfaction = _satisfaction(db, batch.id)
            sources = {item["source_type"]: item for item in satisfaction["by_source"]}
            self.assertEqual(set(satisfaction["expected_source_types"]), {
                "MDTC-postachat", "MDTC-postrecep",
                "Mopinion-desktop", "Mopinion-mobile",
            })
            self.assertEqual(sources["MDTC-postachat"]["availability_status"], "available")
            segments = {
                item["client_status"]: item
                for item in sources["MDTC-postachat"]["by_client_status"]
            }
            self.assertEqual(segments["ancien"]["respondent_count"], 1)
            self.assertEqual(segments["nouveau"]["respondent_count"], 0)
            self.assertEqual(segments["non_renseigne"]["respondent_count"], 0)

            mobile = sources["Mopinion-mobile"]
            self.assertEqual(mobile["availability_status"], "source_not_provided")
            self.assertEqual(mobile["respondent_count"], 0)
            self.assertIsNone(mobile["mean_on_10"])
            self.assertIn("Aucune donnée reçue", mobile["availability_message"])

            evolution = _classification_evolution(db, batch, None)
            mobile_evolution = next(
                item for item in evolution["levels"]["niv2"]
                if item["source_type"] == "Mopinion-mobile"
            )
            self.assertEqual(mobile_evolution["availability_status"], "source_not_provided")
            self.assertEqual(mobile_evolution["current_verbatim_count"], 0)
            self.assertEqual(mobile_evolution["items"], [])
            self.assertIn("lot courant", mobile_evolution["reason"])


if __name__ == "__main__":
    unittest.main()
