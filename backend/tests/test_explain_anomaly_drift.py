import unittest

from sklearn.metrics import roc_auc_score

from helpers import accounts, trained
from app.ml.anomaly import anomaly_table, detect_anomalies
from app.ml.drift import DriftConfig, analyze_drift, benjamini_hochberg, psi_from_counts
from app.ml.errors import DataValidationError, PredictionInputError
from app.ml.explain import explain_instance, global_importance
from app.ml.report import render_html_report
from app.ml.synthetic import make_drift_fixture


class ExplainTests(unittest.TestCase):
    def setUp(self):
        self.df, _ = accounts()
        self.bundle = trained("churned").bundle
        self.record = self.df.iloc[3][self.bundle.schema.feature_names].to_dict()

    def test_contributions_are_additive(self):
        out = explain_instance(self.bundle, self.record, n_permutations=10, seed=1)
        self.assertAlmostEqual(out["base_value"] + out["sum_of_contributions"], out["model_output"], places=6)

    def test_explanation_is_deterministic_for_a_seed(self):
        a = explain_instance(self.bundle, self.record, n_permutations=8, seed=5)
        b = explain_instance(self.bundle, self.record, n_permutations=8, seed=5)
        self.assertEqual(a["contributions"], b["contributions"])

    def test_known_risk_factor_pushes_probability_up(self):
        low = dict(self.record, support_tickets_90d=0, late_payments_12m=0, avg_satisfaction=4.8)
        high = dict(self.record, support_tickets_90d=9, late_payments_12m=6, avg_satisfaction=1.5)
        p_low = explain_instance(self.bundle, low, target_class="1", n_permutations=5)["model_output"]
        p_high = explain_instance(self.bundle, high, target_class="1", n_permutations=5)["model_output"]
        self.assertGreater(p_high, p_low)

    def test_caveats_and_validation(self):
        out = explain_instance(self.bundle, self.record, n_permutations=3)
        self.assertTrue(any("cause" in c.lower() for c in out["caveats"]))
        with self.assertRaises(PredictionInputError):
            explain_instance(self.bundle, self.record, target_class="nope")
        with self.assertRaises(PredictionInputError):
            explain_instance(self.bundle, {})
        with self.assertRaises(PredictionInputError):
            explain_instance(self.bundle, self.record, n_permutations=0)

    def test_regression_explanation(self):
        res = trained("monthly_spend")
        rec = self.df.iloc[0][res.bundle.schema.feature_names].to_dict()
        out = explain_instance(res.bundle, rec, n_permutations=5)
        self.assertAlmostEqual(out["base_value"] + out["sum_of_contributions"], out["model_output"], places=4)

    def test_global_importance_payload(self):
        g = global_importance(self.bundle, trained("churned").summary)
        self.assertIn("not a causal", g["interpretation"].lower())
        self.assertTrue(g["importance"][0]["importance"] >= g["importance"][-1]["importance"])


class AnomalyTests(unittest.TestCase):
    def setUp(self):
        self.df, self.truth = accounts()
        self.features = self.df.drop(columns=["churned", "risk_tier"])

    def test_injected_anomalies_score_higher(self):
        res = detect_anomalies(self.features, sensitivity="medium", seed=1)
        auc = roc_auc_score(self.truth["is_injected_anomaly"], res["scores"])
        self.assertGreater(auc, 0.8)

    def test_sensitivity_controls_number_flagged(self):
        n = {s: detect_anomalies(self.features, sensitivity=s, seed=1)["n_flagged"] for s in ("low", "medium", "high")}
        self.assertLess(n["low"], n["medium"])
        self.assertLess(n["medium"], n["high"])
        self.assertAlmostEqual(n["medium"] / len(self.features), 0.03, delta=0.01)

    def test_result_shape_and_warning(self):
        res = detect_anomalies(self.features, sensitivity=0.05, seed=2)
        self.assertEqual(len(res["scores"]), len(self.features))
        self.assertTrue(all(0 <= s <= 1 for s in res["scores"]))
        self.assertIn("not mean fraud", res["warning"])
        self.assertEqual(res["row_id_column"], "account_id")
        top = res["flagged"][0]
        self.assertEqual(set(top), {"row_index", "row_id", "score", "reasons"})
        table = anomaly_table(self.features, res)
        self.assertEqual(len(table), res["n_flagged"])
        self.assertTrue(table["anomaly_score"].is_monotonic_decreasing)

    def test_deterministic_and_validated(self):
        a = detect_anomalies(self.features, seed=3)
        b = detect_anomalies(self.features, seed=3)
        self.assertEqual(a["flagged_indices"], b["flagged_indices"])
        for bad in ("extreme", 0.9, 0):
            with self.subTest(bad), self.assertRaises(DataValidationError):
                detect_anomalies(self.features, sensitivity=bad)
        with self.assertRaises(DataValidationError):
            detect_anomalies(self.features.head(5))


class DriftTests(unittest.TestCase):
    def setUp(self):
        self.df, _ = accounts()

    def test_shifted_columns_are_flagged_and_stable_ones_are_not(self):
        res = analyze_drift(self.df, make_drift_fixture(self.df))
        by = {c["column"]: c for c in res["columns"]}
        for col in ("monthly_usage_hours", "support_tickets_90d", "plan", "region"):
            self.assertEqual(by[col]["level"], "significant", col)
        for col in ("seats", "tenure_months", "industry"):
            self.assertEqual(by[col]["level"], "stable", col)
        self.assertTrue(res["dataset_drift"])
        self.assertTrue(any(u["value"] == "Overseas" for u in by["region"]["unseen_categories"]))

    def test_same_distribution_shows_no_drift(self):
        res = analyze_drift(self.df, self.df.sample(500, random_state=9))
        self.assertFalse(res["dataset_drift"])
        self.assertEqual(res["columns_drifted"], 0)

    def test_thresholds_are_configurable(self):
        shifted = make_drift_fixture(self.df)
        strict = analyze_drift(self.df, shifted, DriftConfig(psi_warn=0.001, psi_alert=0.002))
        lax = analyze_drift(self.df, shifted, DriftConfig(psi_warn=5, psi_alert=10, dataset_share=1.0))
        self.assertGreater(strict["columns_drifted"], lax["columns_drifted"])
        with self.assertRaises(ValueError):
            analyze_drift(self.df, shifted, DriftConfig(psi_warn=0.3, psi_alert=0.1))

    def test_small_samples_are_reported_as_insufficient(self):
        res = analyze_drift(self.df, self.df.head(10))
        self.assertTrue(all(c["level"] == "insufficient_data" for c in res["columns"]))
        self.assertFalse(res["dataset_drift"])

    def test_psi_and_bh_helpers(self):
        self.assertAlmostEqual(psi_from_counts([10, 20, 30], [10, 20, 30]), 0.0, places=9)
        self.assertGreater(psi_from_counts([90, 10], [10, 90]), 1.0)
        adj = benjamini_hochberg([0.01, 0.04, 0.03, 0.5])
        self.assertTrue(all(a >= p for a, p in zip(adj, [0.01, 0.04, 0.03, 0.5])))
        self.assertTrue(all(0 <= a <= 1 for a in adj))


class ReportTests(unittest.TestCase):
    def test_report_contains_key_sections_and_escapes_html(self):
        summary = trained("churned").summary
        html = render_html_report({"id": "exp_<script>x</script>"}, summary, dataset_name="<b>evil</b>")
        for fragment in ("Model comparison", "Limitations", "Held-out test metrics", summary["selected_model"]):
            self.assertIn(fragment, html)
        self.assertNotIn("<script>x</script>", html)
        self.assertNotIn("<b>evil</b>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
