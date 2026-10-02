import unittest

from src.portfolio import load_portfolio, run_stress


class PortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.positions = load_portfolio()
        cls.signal = {
            "id": "sig_aster",
            "event_classification": "Credit Event",
            "impact_score": 10,
            "entity": "Aster Manufacturing",
            "title": "Aster Manufacturing warns of default",
            "text": "Aster Manufacturing misses a bond coupon and warns of default.",
        }

    def test_portfolio_mix_and_baseline(self):
        self.assertEqual(len(self.positions), 12)
        self.assertEqual(
            {kind: sum(row["asset_type"] == kind for row in self.positions)
             for kind in ("loan", "bond", "derivative")},
            {"loan": 5, "bond": 4, "derivative": 3},
        )
        self.assertAlmostEqual(sum(row["market_value_usd_m"] for row in self.positions), 797.0)

    def test_credit_event_is_concentrated_and_rate_swap_hedges(self):
        run = run_stress(self.signal, self.positions, triggered_at="2026-10-02T00:00:00Z")
        shocks = run["scenario"]["shocks"]
        self.assertEqual(shocks["credit_spreads_bps"], 55.0)
        self.assertEqual(shocks["sector_credit_spreads_bps"], 140.0)
        self.assertEqual(shocks["issuer_haircut_pct"], 25.0)
        self.assertEqual(run["scenario"]["affected_sector"], "Industrials")
        by_id = {row["id"]: row for row in run["positions"]}
        self.assertLess(by_id["L-01"]["pnl_usd_m"], by_id["L-03"]["pnl_usd_m"])
        self.assertGreater(by_id["D-02"]["pnl_usd_m"], 0)  # pay-fixed swap gains when rates rise
        self.assertEqual(run["before_value_usd_m"], 797.0)
        self.assertEqual(run["after_value_usd_m"], 739.04)
        self.assertEqual(run["loss_usd_m"], 57.96)
        self.assertEqual(run["loss_pct"], 7.27)

    def test_unheld_credit_event_has_only_market_spillover(self):
        signal = {**self.signal, "entity": "Unheld Borrower"}
        run = run_stress(signal, self.positions)
        self.assertIsNone(run["scenario"]["affected_sector"])
        self.assertEqual(run["scenario"]["shocks"]["issuer_haircut_pct"], 0)
        self.assertLess(run["loss_usd_m"], 57.96)

    def test_negated_default_does_not_activate_issuer_haircut(self):
        for wording in (
            "Aster Manufacturing avoided default after a debt extension.",
            "Aster Manufacturing reports no default on its loan.",
        ):
            with self.subTest(wording=wording):
                signal = {
                    **self.signal,
                    "impact_score": 7,
                    "title": wording,
                    "text": wording,
                    "sentiment_score": 0.8,
                }
                run = run_stress(signal, self.positions)
                self.assertEqual(run["scenario"]["shocks"]["issuer_haircut_pct"], 0)
                self.assertEqual(run["scenario"]["shocks"]["sector_credit_spreads_bps"], 0.0)

    def test_easing_default_risk_is_not_a_payment_failure(self):
        signal = {
            **self.signal,
            "impact_score": 8,
            "title": "Aster Manufacturing default risk eased after a strong profit recovery.",
            "text": "Aster Manufacturing default risk eased after a strong profit recovery.",
            "sentiment_score": 0.5,
        }
        run = run_stress(signal, self.positions)
        self.assertEqual(run["scenario"]["shocks"]["issuer_haircut_pct"], 0.0)
        self.assertEqual(run["scenario"]["shocks"]["sector_credit_spreads_bps"], 0.0)
        self.assertIn("what-if", run["scenario"]["rationale"])

    def test_totals_reconcile_to_position_values(self):
        run = run_stress(self.signal, self.positions)
        rows = run["positions"]
        self.assertAlmostEqual(sum(row["before_value_usd_m"] for row in rows), run["before_value_usd_m"])
        self.assertAlmostEqual(sum(row["after_value_usd_m"] for row in rows), run["after_value_usd_m"])
        self.assertAlmostEqual(sum(row["pnl_usd_m"] for row in rows), run["pnl_usd_m"])
        self.assertAlmostEqual(run["before_value_usd_m"] - run["after_value_usd_m"], run["loss_usd_m"])


if __name__ == "__main__":
    unittest.main()
