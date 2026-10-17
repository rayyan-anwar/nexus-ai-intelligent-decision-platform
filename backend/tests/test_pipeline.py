import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

from helpers import accounts, churn_frame, spend_frame, trained
from app.ml import pipeline as P
from app.ml.errors import ArtifactError, DataValidationError, PredictionInputError, UnsupportedTaskError
from app.ml.pipeline import TrainConfig, predict_records, predictions_frame, train_experiment
from app.ml.tracking import dataset_fingerprint, load_bundle, save_bundle


class TrainingTests(unittest.TestCase):
    def test_all_task_types_train_and_report_expected_metrics(self):
        expected = {
            "churned": ("binary", {"accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc", "confusion_matrix"}),
            "risk_tier": ("multiclass", {"accuracy", "f1_macro", "roc_auc", "confusion_matrix", "per_class"}),
            "monthly_spend": ("regression", {"mae", "rmse", "r2", "residuals"}),
        }
        for target, (task, keys) in expected.items():
            with self.subTest(target):
                s = trained(target).summary
                self.assertEqual(s["task"], task)
                self.assertTrue(keys <= set(s["test_metrics"]), keys - set(s["test_metrics"]))
                self.assertEqual(len(s["candidates"]), 3)
                self.assertIn("baseline", s)

    def test_reproducible_with_same_seed(self):
        df = churn_frame()
        a = train_experiment(df, TrainConfig(target="churned", seed=3, model_names=["logistic_regression"]))
        b = train_experiment(df, TrainConfig(target="churned", seed=3, model_names=["logistic_regression"]))
        self.assertEqual(a.summary["test_metrics"], b.summary["test_metrics"])
        self.assertEqual(a.summary["importance"], b.summary["importance"])

    def test_selection_picks_best_validation_score_for_every_task(self):
        for target in ("churned", "risk_tier", "monthly_spend"):
            with self.subTest(target):
                s = trained(target).summary
                spec = s["primary_metric"]
                scores = {c["name"]: c["validation"][spec["name"]] for c in s["candidates"]}
                pick = min if spec["direction"] == "lower" else max
                self.assertEqual(s["selected_model"], pick(scores, key=scores.get), scores)
                self.assertEqual(s["split"]["selection_split"], "validation")

    def test_primary_metric_rules(self):
        self.assertEqual(trained("monthly_spend").summary["primary_metric"], {"name": "rmse", "direction": "lower"})
        self.assertEqual(trained("risk_tier").summary["primary_metric"]["name"], "f1_macro")
        balanced = pd.Series([0, 1] * 50)
        skewed = pd.Series([0] * 90 + [1] * 10)
        self.assertEqual(P.primary_metric_spec("binary", balanced)["name"], "roc_auc")
        self.assertEqual(P.primary_metric_spec("binary", skewed)["name"], "pr_auc")

    def test_test_split_is_evaluated_only_after_selection(self):
        calls = []
        real = P.evaluate

        def spy(pipe, X, y, *a, **k):
            calls.append(len(X))
            return real(pipe, X, y, *a, **k)

        cfg = TrainConfig(target="churned", val_size=0.25, test_size=0.15, seed=1)
        with mock.patch.object(P, "evaluate", spy):
            res = train_experiment(churn_frame(), cfg)
        n_val, n_test = res.summary["split"]["n_validation"], res.summary["split"]["n_test"]
        self.assertNotEqual(n_val, n_test)
        first_test_call = calls.index(n_test)
        self.assertTrue(all(c == n_val for c in calls[:first_test_call]))
        self.assertEqual(first_test_call, 3 + 1)  # 3 candidates + baseline validation
        self.assertEqual(calls.count(n_test), 2)  # baseline + selected only

    def test_preprocessing_is_fitted_on_training_rows_only(self):
        df = churn_frame()
        cfg = TrainConfig(target="churned", seed=42, model_names=["logistic_regression"])
        res = train_experiment(df, cfg)
        tr, _, _ = P.split_indices(df["churned"].astype(str), "binary", cfg.seed, cfg.test_size, cfg.val_size)
        numeric = [f.name for f in res.bundle.schema.features if f.kind == "numeric"]
        imputer = res.bundle.pipeline.named_steps["prep"].named_transformers_["num"].named_steps["impute"]
        train_medians = df.iloc[tr][numeric].median().to_numpy()
        all_medians = df[numeric].median().to_numpy()
        np.testing.assert_allclose(imputer.statistics_, train_medians)
        self.assertFalse(np.allclose(train_medians, all_medians))

    def test_no_signal_gives_chance_level_test_score(self):
        df = churn_frame().copy()
        df["churned"] = np.random.default_rng(0).permutation(df["churned"].to_numpy())
        res = train_experiment(df, TrainConfig(target="churned", seed=2))
        auc = res.summary["test_metrics"]["roc_auc"]
        self.assertTrue(0.35 < auc < 0.65, auc)

    def test_model_beats_baseline_on_signal(self):
        s = trained("monthly_spend").summary
        self.assertLess(s["test_metrics"]["rmse"], s["baseline"]["test"]["rmse"])

    def test_leakage_is_flagged(self):
        df = churn_frame().copy()
        df["leak"] = df["churned"] * 1.0
        res = train_experiment(df, TrainConfig(target="churned", model_names=["logistic_regression"]))
        self.assertTrue(any("leakage" in w.lower() for w in res.summary["warnings"]))

    def test_unsupported_and_invalid_inputs_fail_gracefully(self):
        df = churn_frame()
        with self.assertRaises(DataValidationError):
            train_experiment(df, TrainConfig(target="nope"))
        with self.assertRaises(UnsupportedTaskError):
            train_experiment(df.assign(const=1), TrainConfig(target="const"))
        with self.assertRaises(UnsupportedTaskError):
            train_experiment(df, TrainConfig(target="account_id"))
        with self.assertRaises(DataValidationError):
            train_experiment(df.head(20), TrainConfig(target="churned"))
        with self.assertRaises(DataValidationError):
            train_experiment(df, TrainConfig(target="churned", model_names=["magic"]))
        with self.assertRaises(DataValidationError):
            TrainConfig(target="churned", test_size=0.7).validate()
        rare = df.copy()
        rare["churned"] = rare["churned"].astype(str)
        rare.loc[rare.index[:2], "churned"] = "rare"
        with self.assertRaises(UnsupportedTaskError) as ctx:
            train_experiment(rare, TrainConfig(target="churned"))
        self.assertIn("rare", ctx.exception.message)

    def test_missing_target_rows_are_dropped_with_warning(self):
        df = spend_frame().copy()
        df.loc[df.index[:30], "monthly_spend"] = np.nan
        res = train_experiment(df, TrainConfig(target="monthly_spend", model_names=["linear_regression"]))
        self.assertEqual(res.summary["rows_dropped_missing_target"], 30)

    def test_summary_is_json_serialisable(self):
        import json

        json.dumps(trained("risk_tier").summary)

    def test_progress_callback_is_monotonic(self):
        seen = []
        train_experiment(spend_frame(), TrainConfig(target="monthly_spend", model_names=["linear_regression"]), progress=lambda s, f: seen.append(f))
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(seen[-1], 1.0)


class InferenceTests(unittest.TestCase):
    def setUp(self):
        self.df, _ = accounts()
        self.record = self.df.iloc[0].drop(["churned", "risk_tier", "monthly_spend"]).to_dict()

    def test_classification_output_schema(self):
        bundle = trained("churned").bundle
        out = predict_records(bundle, [self.record])
        p = out["predictions"][0]
        self.assertEqual(set(p), {"prediction", "confidence", "low_confidence", "probabilities"})
        self.assertAlmostEqual(sum(p["probabilities"].values()), 1.0, places=2)
        self.assertIn(p["prediction"], bundle.metadata["classes"])
        self.assertIn("uncertainty_note", out)

    def test_regression_interval_contains_prediction(self):
        bundle = trained("monthly_spend").bundle
        p = predict_records(bundle, [self.record])["predictions"][0]
        self.assertLess(p["interval_low"], p["prediction"])
        self.assertGreater(p["interval_high"], p["prediction"])

    def test_prediction_matches_training_pipeline_and_is_batch_consistent(self):
        bundle = trained("churned").bundle
        feats = bundle.schema.feature_names
        rows = self.df.iloc[:25][feats]
        direct = bundle.pipeline.predict_proba(bundle.schema.coerce(rows)[0])
        batch = predict_records(bundle, rows.to_dict("records"))["predictions"]
        single = [predict_records(bundle, [r])["predictions"][0] for r in rows.to_dict("records")]
        classes = [str(c) for c in bundle.pipeline.classes_]
        for i in range(25):
            self.assertEqual(batch[i]["prediction"], single[i]["prediction"])
            for j, c in enumerate(classes):
                self.assertAlmostEqual(batch[i]["probabilities"][c], single[i]["probabilities"][c], places=3)
                self.assertAlmostEqual(batch[i]["probabilities"][c], direct[i, j], places=3)

    def test_input_problems_are_reported_not_hidden(self):
        bundle = trained("churned").bundle
        bad = dict(self.record, region="Atlantis", seats="many", mystery=1)
        del bad["plan"]
        out = predict_records(bundle, [bad])
        text = " ".join(out["issues"])
        for fragment in ("Atlantis", "'seats'", "'plan'", "unrecognised"):
            self.assertIn(fragment, text)
        out = predict_records(bundle, [dict(self.record, seats=10_000)])
        self.assertIn("outside the training range", " ".join(out["issues"]))

    def test_invalid_requests_rejected(self):
        bundle = trained("churned").bundle
        for bad in ([], "x", [1, 2], [{}]):
            with self.subTest(bad), self.assertRaises(PredictionInputError):
                predict_records(bundle, bad)
        with self.assertRaises(PredictionInputError):
            predict_records(bundle, [self.record] * 3, max_records=2)

    def test_predictions_frame_for_export(self):
        bundle = trained("churned").bundle
        out = predictions_frame(bundle, self.df.head(5)[bundle.schema.feature_names])
        self.assertEqual(len(out), 5)
        self.assertTrue({"prediction", "confidence", "low_confidence"} <= set(out.columns))


class ArtifactTests(unittest.TestCase):
    def test_save_load_roundtrip_gives_identical_predictions(self):
        res = trained("churned")
        df, _ = accounts()
        rows = df.head(10)[res.bundle.schema.feature_names].to_dict("records")
        with tempfile.TemporaryDirectory() as d:
            path, digest = save_bundle(res.bundle, d, "mdl_test")
            loaded = load_bundle(path, digest)
        self.assertEqual(predict_records(res.bundle, rows), predict_records(loaded, rows))

    def test_tampered_or_missing_artifacts_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, digest = save_bundle(trained("churned").bundle, d, "mdl_test")
            with self.assertRaises(ArtifactError):
                load_bundle(path, "0" * 64)
            with open(path, "ab") as fh:
                fh.write(b"tamper")
            with self.assertRaises(ArtifactError):
                load_bundle(path, digest)
            with self.assertRaises(ArtifactError):
                load_bundle(path.with_name("missing.joblib"), digest)


class TrackingTests(unittest.TestCase):
    def test_fingerprint_is_stable_and_content_sensitive(self):
        df, _ = accounts()
        self.assertEqual(dataset_fingerprint(df), dataset_fingerprint(df.copy()))
        changed = df.copy()
        changed.loc[0, "seats"] += 1
        self.assertNotEqual(dataset_fingerprint(df), dataset_fingerprint(changed))

    def test_experiment_record_has_required_fields(self):
        rec = trained("churned").summary["experiment_record"]
        for key in ("target", "seed", "selected_model", "trained_at", "software", "dataset_fingerprint"):
            self.assertIn(key, rec)


if __name__ == "__main__":
    unittest.main()
