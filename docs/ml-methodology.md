# ML methodology

This document describes what the code does, its assumptions, and where it falls short. Numbers from real runs are in [results.md](results.md); nothing here is a benchmark claim.

## 1. Data handling

* **Ingestion** (`ml/ingest.py`): UTF-8 CSV only; rejects empty files, binary content, duplicate or blank headers, files over the size, row or column limits, and unparseable input. Fully empty rows are dropped.
* **Column kinds** (`ml/profiling.py`): numeric, numeric-like (text that is mostly numbers), categorical, boolean, datetime, identifier, text, constant, empty. Identifier, text, datetime and constant columns are **never** used as features and the reason is recorded.
* **Invalid numbers** in numeric-like columns are reported and treated as missing during modelling; they are not silently corrected.

## 2. Task inference

`ml/tasks.py` proposes targets (column-name hints, last-column convention, number of distinct values) and infers the task: two distinct values means binary; text with 3 to 20 values means multiclass; integer-valued numbers with 3 to 10 distinct values are treated as classes (override with `task=regression` for counts); other numeric targets are regression. **The user must confirm the target.** Constant, identifier, text, datetime and over-20-class targets fail with a clear message.

## 3. Splits and leakage controls

* Default split: 60% train, 20% validation, 20% test (`val_size` and `test_size` are configurable). Classification splits are stratified; every class needs at least 5 rows and at least 50 rows with a valid target are required.
* Preprocessing is **inside** the scikit-learn pipeline and fitted on the training split only. Tests assert that the imputer statistics equal the training-row medians and differ from the full-data medians.
* The **test split is evaluated once**, for the already-selected model and the baseline. A test spies on the evaluation calls to enforce the order.
* A label-permutation test checks that test performance on shuffled labels stays near chance.
* Numeric features with |correlation| above 0.95 with the target raise a leakage warning. This catches only obvious cases; it cannot detect leakage through categorical features or business logic.

## 4. Models and selection

| Task | Candidates | Baseline |
|---|---|---|
| Classification | Logistic regression (balanced class weights), random forest (200 trees, balanced), gradient boosting (150 trees, depth 3) | Class prior |
| Regression | Linear regression, random forest, gradient boosting | Mean |

Preprocessing: numeric columns use median imputation and standardisation; categorical columns use a constant "missing" category and one-hot encoding (rare levels grouped, at most 30 levels per column, unseen levels handled without error).

The **selection metric** is computed on the validation split only: PR-AUC for binary targets whose rarest class is below 20%, otherwise ROC-AUC; macro-F1 for multiclass; RMSE (lower is better) for regression. No hyperparameter search is performed; defaults are fixed and documented above. XGBoost and SHAP are not included (see roadmap).

## 5. Evaluation

* Classification: accuracy, balanced accuracy, precision, recall, F1 (positive class is the rarer class unless set), macro-F1, ROC-AUC, PR-AUC (binary), log loss, Brier score (binary), per-class metrics, confusion matrix.
* Regression: MAE, RMSE, R², median absolute error, residual summary and a sample of residuals for plotting.
* Metrics come from **one random split**. They carry sampling uncertainty, which is largest for small datasets and rare classes; the app warns for datasets under 200 rows and for imbalance. Cross-validation and confidence intervals on metrics are not implemented.
* Warnings are raised when the selected model does not beat the baseline on validation data, or when training performance is far above validation performance.

## 6. Communicating uncertainty

* **Classification:** the predicted class, its estimated probability, all class probabilities, and a *low confidence* flag below 60%. Probabilities are **not calibrated**; Brier score and log loss are reported but no calibration step is applied.
* **Regression:** a prediction interval from split-conformal calibration: the 90% quantile (with the finite-sample rank correction) of absolute residuals on the validation split is added to and subtracted from each prediction. Assumptions: validation and future data are exchangeable. Limitations: the validation split is also used for model selection, so coverage is approximate; the interval has a constant width, so it is too narrow for noisy regions and too wide for quiet ones.
* Inputs outside the training range or with unseen categories produce explicit warnings.

## 7. Explanations

* **Global:** permutation importance on the validation split (5 repeats), scored with the selection metric. Features whose mean importance is within two standard deviations of zero are marked *unstable*. Strongly correlated numeric pairs (|r| >= 0.8) are listed because correlated features share importance.
* **Local:** Monte-Carlo Shapley values over the original input columns, interventional, using up to 20 stored training rows as background and 30 random feature orderings by default. Contributions are additive by construction (a test verifies that base value plus contributions equals the model output) and each has a Monte-Carlo standard error.
* Both are **descriptions of the model, not causal effects**. The UI and API state this next to every explanation. Combining background rows can create unrealistic records, and explanations may change when the model is retrained.

## 7a. What the stored background rows mean for privacy

Local explanations need a small background sample, so up to 50 rows of **training** data are stored inside each model artifact. They are removed when the model is deleted and covered by dataset retention rules. Treat model files as sensitive as the training data.

## 8. Anomaly detection

Isolation Forest (200 trees) on median-imputed, standardised numeric features and one-hot categorical features. *Sensitivity* sets the expected share of flagged rows (low 1%, medium 3%, high 8%, or a custom value from 0.1% to 30%). Scores are rescaled to 0-1 for display (not probabilities). For each flagged row the app lists features that are far from the column median (robust z-score of at least 3.5) or that have a rare category (under 1%). It is unsupervised and cannot tell a data error from a genuine rare event, which the UI states.

## 9. Data-quality and drift analysis

* **Quality:** missing-value rates, exact duplicate rows, numeric-like columns with invalid entries, infinite values, extreme outliers (beyond 3 IQR), constant and identifier columns, unseen categories and out-of-range values relative to a trained schema.
* **Drift** (reference vs new data):
  * *Population Stability Index* with bins from the reference quantiles; levels default to below 0.1 stable, 0.1 to 0.25 moderate, above 0.25 significant. These cut-offs are conventions, are configurable, and are not statistical thresholds.
  * *Two-sample Kolmogorov-Smirnov test* (numeric): assumes independent samples; tied integer data make p-values conservative.
  * *Chi-square test of homogeneity* (categorical): needs expected counts of at least 5 per cell; the report flags when this fails.
  * P-values are adjusted across columns with Benjamini-Hochberg. Because large samples make tiny shifts significant, the **level is driven by PSI**; p-values are shown alongside.
  * Previously unseen categories above 2% of rows raise the column to at least *moderate*. Columns with fewer than 30 non-missing values in either sample are reported as *insufficient data*.
  * Dataset-level drift is declared when at least 30% of assessed columns have shifted (configurable).
* Drift in inputs does not prove predictions are wrong, and absence of drift does not prove they are right. Concept drift (a changed relationship between inputs and target) needs fresh labels and is not covered.

## 10. Reproducibility

Experiments record: id, dataset fingerprint (SHA-256 of the stored file), target, task, seed, model name, split sizes, metrics, UTC training time, and versions of Python, scikit-learn, pandas, NumPy and the application. Models are artifacts verified by SHA-256 before loading. With the same data, seed and library versions results are reproducible (a test checks identical metrics and importances on a re-run).

## 11. Known limitations

* Single random split; no confidence intervals on metrics; no hyperparameter tuning.
* No calibration of classification probabilities; no fairness or bias assessment.
* Time ordering is ignored (random split), which is wrong for forecasting problems.
* Wide or very high-cardinality data is only handled by grouping rare categories.
* The synthetic sample's relationships are written into the generator, so results on it do not generalise.

## 12. Implemented versus proposed

Implemented: everything above. **Proposed, not implemented:** XGBoost/SHAP backends, calibration, cross-validation with confidence intervals, ordinal models, adaptive conformal intervals.

*Possible research question (not studied here):* under covariate shift flagged by PSI, does re-calibrating split-conformal intervals on a small labelled window restore nominal coverage better than static intervals? A genuine contribution would need public datasets with natural shift, pre-registered metrics (coverage, interval width) and comparison with existing adaptive-conformal baselines; combining existing algorithms in an application does not by itself establish novelty.
