import unittest

import numpy as np
import pandas as pd

from helpers import accounts, trained
from app.ml.profiling import infer_kind, profile_dataframe
from app.ml.quality import quality_report
from app.ml.synthetic import generate_accounts, make_quality_fixture
from app.ml.tasks import infer_task, suggest_targets
from app.ml.errors import UnsupportedTaskError


class SyntheticTests(unittest.TestCase):
    def test_generation_is_reproducible(self):
        a, ta = generate_accounts(200, seed=5)
        b, tb = generate_accounts(200, seed=5)
        c, _ = generate_accounts(200, seed=6)
        pd.testing.assert_frame_equal(a, b)
        pd.testing.assert_frame_equal(ta, tb)
        self.assertFalse(a.equals(c))

    def test_ground_truth_is_separate_from_features(self):
        df, truth = accounts()
        self.assertNotIn("is_injected_anomaly", df.columns)
        self.assertEqual(int(truth.is_injected_anomaly.sum()), round(0.02 * len(df)))

    def test_rejects_bad_arguments(self):
        with self.assertRaises(ValueError):
            generate_accounts(10)
        with self.assertRaises(ValueError):
            generate_accounts(100, anomaly_rate=0.9)


class ProfilingTests(unittest.TestCase):
    def test_kinds(self):
        df, _ = accounts()
        self.assertEqual(infer_kind(df["account_id"]), "identifier")
        self.assertEqual(infer_kind(df["region"]), "categorical")
        self.assertEqual(infer_kind(df["seats"]), "numeric")

    def test_profile_hides_rare_category_values(self):
        df = pd.DataFrame({"c": ["a"] * 50 + ["b"] * 40 + ["rare1", "rare2"], "x": range(92)})
        prof = profile_dataframe(df)
        col = next(c for c in prof["columns"] if c["name"] == "c")
        values = {v["value"] for v in col["top_values"]}
        self.assertEqual(values, {"a", "b"})


class QualityTests(unittest.TestCase):
    def test_fixture_problems_are_detected(self):
        df, _ = accounts()
        schema = trained("churned").bundle.schema
        report = quality_report(make_quality_fixture(df), schema)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("invalid_type", codes)
        self.assertIn("duplicate_rows", codes)
        self.assertIn("missing_values", codes)
        self.assertIn("unexpected_category", codes)
        self.assertGreaterEqual(report["duplicate_rows"], 15)
        invalid = next(i for i in report["issues"] if i["code"] == "invalid_type")
        self.assertEqual(invalid["column"], "monthly_usage_hours")
        self.assertEqual(invalid["count"], 10)
        self.assertTrue(any(u["column"] == "region" and "Atlantis" in u["values"] for u in report["unexpected_categories"]))

    def test_clean_data_has_no_errors(self):
        df, _ = accounts()
        report = quality_report(df)
        self.assertEqual(report["severity_counts"]["error"], 0)
        self.assertEqual(report["duplicate_rows"], 0)

    def test_empty_column_is_an_error(self):
        df = pd.DataFrame({"a": [np.nan] * 5, "b": range(5)})
        self.assertEqual(quality_report(df)["severity_counts"]["error"], 1)


class TaskInferenceTests(unittest.TestCase):
    def test_inferred_tasks(self):
        df, _ = accounts()
        self.assertEqual(infer_task(df["churned"])[0], "binary")
        self.assertEqual(infer_task(df["risk_tier"])[0], "multiclass")
        self.assertEqual(infer_task(df["monthly_spend"])[0], "regression")

    def test_overrides(self):
        s = pd.Series([0, 1, 2, 3, 2, 1] * 10)
        self.assertEqual(infer_task(s)[0], "multiclass")
        self.assertEqual(infer_task(s, "regression")[0], "regression")

    def test_unsupported_targets_fail_with_message(self):
        bad = {
            "constant": pd.Series(["a"] * 60),
            "identifier": pd.Series([f"id{i}" for i in range(60)]),
            "too_many_classes": pd.Series([f"k{i % 30}" for i in range(300)]),
        }
        for name, s in bad.items():
            with self.subTest(name), self.assertRaises(UnsupportedTaskError):
                infer_task(s)
        with self.assertRaises(UnsupportedTaskError):
            infer_task(pd.Series(["a", "b"] * 30), "regression")
        with self.assertRaises(UnsupportedTaskError):
            infer_task(pd.Series(["a", "b"] * 30), "banana")

    def test_target_suggestions_rank_outcomes_first(self):
        df, _ = accounts()
        top = [s["column"] for s in suggest_targets(df.drop(columns=["risk_tier"]))][:2]
        self.assertIn("churned", top)


if __name__ == "__main__":
    unittest.main()
