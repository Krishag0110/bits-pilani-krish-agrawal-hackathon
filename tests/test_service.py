from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.service import RiskApplication
from src.sources import SourceBatch, SourceError


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.db = Path(self.temp.name) / "signals.db"
        self.app = RiskApplication(db_path=self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_seeded_demo_is_explicit_and_persistent(self):
        state = self.app.state()
        self.assertEqual(state["metrics"]["demo_signals"], 7)
        self.assertEqual(state["metrics"]["live_signals"], 0)
        self.assertEqual(len(state["runs"]), 3)
        self.assertEqual(state["latest_run"]["entity"], "Aster Manufacturing")
        self.assertEqual(state["latest_run"]["loss_usd_m"], 57.96)
        self.assertTrue(all(row["provenance"] == "demo" for row in state["signals"]))
        restarted = RiskApplication(db_path=self.db)
        self.assertEqual(restarted.state()["metrics"]["total_signals"], 7)

    def test_manual_analysis_autotriggers_and_deduplicates(self):
        item = {
            "source": "news", "entity": "Aster Manufacturing",
            "text": "Aster Manufacturing missed a bond interest payment and faces a credit downgrade after lenders warned of a possible default.",
        }
        first = self.app.analyze(item)
        second = self.app.analyze(item)
        self.assertEqual(first["signal"]["id"], second["signal"]["id"])
        self.assertEqual(first["run"]["id"], second["run"]["id"])
        self.assertEqual(first["signal"]["provenance"], "manual")
        self.assertEqual(first["run"]["loss_usd_m"], 57.96)
        self.assertEqual(first["state"]["metrics"]["manual_signals"], 1)
        self.assertEqual(first["state"]["metrics"]["total_signals"], 8)

    def test_refresh_two_sources_dedup_and_partial_failure(self):
        news = SourceBatch([{
            "source": "news", "title": "A bank faces a rating downgrade",
            "text": "A bank faces a rating downgrade.", "url": "https://example.org/a",
            "published_at": "2026-10-02T12:00:00Z", "timestamp_basis": "gdelt_first_seen",
        }], endpoint="https://example.org/news")
        social = SourceBatch([{
            "source": "social", "title": "Bank loans face losses",
            "text": "Bank loans face losses after a default.", "url": "https://bsky.app/profile/example/post/a",
            "published_at": "2026-10-02T12:05:00Z", "timestamp_basis": "post_created_at",
        }], endpoint="https://example.org/social")
        with patch("src.service.fetch_news", return_value=news), patch(
            "src.service.fetch_bluesky", return_value=social
        ):
            first = self.app.refresh(limit=2)
            second = self.app.refresh(limit=2)
        self.assertEqual(len(first["added"]), 2)
        self.assertEqual(len(second["added"]), 0)
        self.assertEqual(second["state"]["metrics"]["live_signals"], 2)
        self.assertEqual(second["source_status"]["news"]["state"], "ok")
        self.assertEqual(second["source_status"]["social"]["state"], "ok")
        self.assertTrue(all(item["provenance"] == "live" for item in first["added"]))
        with patch("src.service.fetch_news", side_effect=SourceError("GDELT unavailable")), patch(
            "src.service.fetch_bluesky", return_value=social
        ):
            partial = self.app.refresh(limit=2)
        self.assertEqual(partial["source_status"]["news"]["state"], "error")
        self.assertIn("unavailable", partial["source_status"]["news"]["error"])
        self.assertEqual(partial["state"]["metrics"]["live_signals"], 2)

    def test_reset_restores_demo_and_clears_manual_record(self):
        self.app.analyze({"source": "social", "text": "Analysts are watching the market."})
        self.assertEqual(self.app.state()["metrics"]["manual_signals"], 1)
        state = self.app.reset_demo()
        self.assertEqual(state["metrics"]["manual_signals"], 0)
        self.assertEqual(state["metrics"]["total_signals"], 7)
        self.assertEqual(state["source_status"]["news"]["state"], "idle")

    def test_manual_stress_can_run_lower_impact_signal(self):
        signal = next(row for row in self.app.state()["signals"] if row["entity"] == "Meridian Utilities")
        self.assertEqual(signal["impact_score"], 3)
        previous = len(self.app.state()["runs"])
        result = self.app.stress(signal["id"])
        self.assertEqual(len(result["state"]["runs"]), previous + 1)
        self.assertEqual(result["run"]["impact_score"], 3)

    def test_mixed_company_text_stresses_event_issuer(self):
        text = (
            "Meridian Utilities missed a bond interest payment and warned of default. "
            "Aster Manufacturing reported strong demand."
        )
        result = self.app.analyze({"source": "news", "text": text})
        self.assertEqual(result["signal"]["entity"], "Meridian Utilities")
        self.assertIsNotNone(result["run"])
        self.assertEqual(result["run"]["scenario"]["affected_obligor"], "Meridian Utilities")


if __name__ == "__main__":
    unittest.main()
