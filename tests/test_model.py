import unittest

from src.model import RiskModel


class RiskModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = RiskModel(portfolio_entities=["Aster Manufacturing"])

    def test_distinct_financial_event_language(self):
        examples = {
            "Geopolitical": "Border conflict triggers sweeping sanctions and a trade embargo.",
            "Macroeconomic": "Central bank raises interest rates as inflation accelerates.",
            "Credit Event": "Aster Manufacturing misses a bond coupon and warns of default.",
            "Merger/Acquisition": "A holding company agrees to acquire its rival in a merger.",
            "Product Launch": "Solstice Systems launched a new analytics product for clients.",
            "Regulatory": "Regulator fines bank for compliance violations under new rules.",
            "Operational": "Cyberattack causes a systems outage and disrupts shipments.",
        }
        for expected, text in examples.items():
            with self.subTest(expected=expected):
                result = self.model.analyze(text)
                self.assertEqual(result["event_classification"], expected)
                self.assertTrue(-1 <= result["sentiment_score"] <= 1)
                self.assertTrue(1 <= result["impact_score"] <= 10)
                self.assertTrue(result["explanation"])
                self.assertTrue(result["evidence"])

    def test_generic_market_text_abstains(self):
        result = self.model.analyze("Investors are watching financial markets today.")
        self.assertEqual(result["event_classification"], "Other")
        self.assertEqual(result["sentiment_score"], 0.0)

    def test_past_tense_entity_and_polarity(self):
        launch = self.model.analyze(
            "Solstice Systems launched a new analytics product with strong demand."
        )
        default = self.model.analyze(
            "Aster Manufacturing defaulted on its bond after a missed payment."
        )
        self.assertEqual(launch["entity"], "Solstice Systems")
        self.assertGreater(launch["sentiment_score"], 0)
        self.assertLess(default["sentiment_score"], 0)
        self.assertGreater(default["impact_score"], 7)

    def test_negation_reduces_false_negative_sentiment(self):
        negated = self.model.analyze("Aster Manufacturing has not defaulted on its loan.")
        unnegated = self.model.analyze("Aster Manufacturing has defaulted on its loan.")
        self.assertGreater(negated["sentiment_score"], unnegated["sentiment_score"])
        self.assertLess(negated["impact_score"], unnegated["impact_score"])

    def test_event_clause_selects_the_right_issuer(self):
        model = RiskModel(portfolio_entities=["Aster Manufacturing", "Meridian Utilities"])
        text = (
            "Meridian Utilities missed a bond interest payment and warned of default. "
            "Aster Manufacturing reported strong demand."
        )
        inferred = model.analyze(text)
        explicit = model.analyze(text, entity="Aster Manufacturing")
        self.assertEqual(inferred["event_classification"], "Credit Event")
        self.assertEqual(inferred["entity"], "Meridian Utilities")
        self.assertEqual(explicit["entity"], "Aster Manufacturing")

    def test_easing_default_risk_is_not_a_high_impact_failure(self):
        result = self.model.analyze(
            "Aster Manufacturing default risk eased after a strong profit recovery."
        )
        self.assertEqual(result["event_classification"], "Credit Event")
        self.assertGreater(result["sentiment_score"], 0)
        self.assertLessEqual(result["impact_score"], 7)

    def test_oil_reserve_release_is_not_a_product_launch(self):
        result = self.model.analyze(
            "G7 countries agree to release oil from strategic reserves to lower diesel prices."
        )
        self.assertEqual(result["event_classification"], "Other")


if __name__ == "__main__":
    unittest.main()
