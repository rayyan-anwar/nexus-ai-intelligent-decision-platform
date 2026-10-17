// Response shapes used by the UI (subset of the API; see docs/api.md).

export type Task = "binary" | "multiclass" | "regression";

export interface Dataset {
  id: string;
  name: string;
  n_rows: number;
  n_cols: number;
  size_bytes: number;
  sha256: string;
  is_synthetic: boolean;
  created_at: string;
  expires_at: string | null;
}

export interface ColumnProfile {
  name: string;
  dtype: string;
  kind: string;
  missing: number;
  missing_pct: number;
  unique: number;
  stats?: { min: number | null; max: number | null; mean: number | null; std: number | null; q25: number | null; median: number | null; q75: number | null };
  histogram?: { edges: number[]; counts: number[] };
  top_values?: { value: string; count: number }[];
  invalid_entries?: number;
}

export interface TargetSuggestion { column: string; task: Task; score: number; reasons: string[] }

export interface ProfileResponse {
  dataset: Dataset;
  profile: { n_rows: number; n_cols: number; duplicate_rows: number; kind_counts: Record<string, number>; columns: ColumnProfile[] };
  target_suggestions: TargetSuggestion[];
  note: string;
}

export interface QualityIssue { severity: "error" | "warning" | "info"; code: string; column: string | null; message: string; count: number | null }
export interface QualityReport {
  n_rows: number; n_cols: number; missing_cells: number; missing_cells_pct: number; duplicate_rows: number;
  severity_counts: Record<"error" | "warning" | "info", number>;
  columns: { name: string; kind: string; missing: number; missing_pct: number }[];
  issues: QualityIssue[];
}

export interface Preview { columns: string[]; rows: (string | number | boolean | null)[][]; total_rows: number }

export interface Experiment {
  id: string; dataset_id: string; target: string; task: Task | null; status: "queued" | "running" | "succeeded" | "failed";
  progress: number; stage: string | null; seed: number; error_message: string | null; model_id: string | null;
  created_at: string; started_at: string | null; finished_at: string | null;
}

export interface ExperimentRequest {
  dataset_id: string; target: string; task?: Task | null; seed?: number; test_size?: number; val_size?: number;
  model_names?: string[] | null; exclude_columns?: string[]; positive_label?: string | null;
}

export type Metrics = Record<string, number | null | undefined>;
export interface Candidate { name: string; fit_seconds: number; validation: Metrics; selected: boolean }
export interface ImportanceItem { feature: string; importance: number; std: number; unstable: boolean }
export interface ConfusionMatrix { labels: string[]; matrix: number[][] }
export interface ExperimentSummary {
  task: Task; target: string; classes: string[]; positive_label: string | null; seed: number;
  split: { n_train: number; n_validation: number; n_test: number; stratified: boolean; selection_split: string; test_evaluated_once: boolean };
  rows_used: number; features: string[]; excluded_features: Record<string, string>;
  primary_metric: { name: string; direction: "higher" | "lower" };
  candidates: Candidate[]; selected_model: string;
  baseline: { name: string; validation: Metrics; test: Metrics };
  test_metrics: Metrics & { confusion_matrix?: ConfusionMatrix; residuals?: { sample: { predicted: number; residual: number }[] } };
  interval: { level: number; half_width: number; method: string } | null;
  importance: ImportanceItem[]; explanation_warnings: string[]; warnings: string[]; limitations: string[];
}

export interface ModelSummary { id: string; experiment_id: string; name: string; task: Task; target: string; created_at: string; primary_metric: string | null; test_score: number | null }
export interface FeatureSpec { name: string; kind: "numeric" | "categorical"; categories: string[] | null; min: number | null; max: number | null; median: number | null; mode: string | null }
export interface ModelDetail extends ModelSummary {
  schema: { features: FeatureSpec[]; target: string; task: Task; classes: string[]; positive_label: string | null };
  interval: { level: number; half_width: number } | null; classes: string[]; positive_label: string | null;
}

export interface Prediction {
  prediction: string | number; confidence?: number; low_confidence?: boolean; probabilities?: Record<string, number>;
  interval_low?: number; interval_high?: number;
}
export interface PredictResponse { model: { name: string; task: Task; target: string }; n_records: number; predictions: Prediction[]; issues: string[]; uncertainty_note: string }

export interface GlobalExplanation { method: string; metric: { name: string; direction: string }; importance: ImportanceItem[]; warnings: string[]; interpretation: string }
export interface LocalExplanation {
  output: string; target_class: string | null; base_value: number; model_output: number; sum_of_contributions: number;
  contributions: { feature: string; value: string | number | null; contribution: number; std_error: number; direction: string }[];
  method: string; n_permutations: number; background_rows: number; issues: string[]; caveats: string[]; interpretation: string;
}

export interface AnomalyResult {
  n_rows: number; n_flagged: number; contamination: number; threshold: number; features_used: string[]; row_id_column: string | null;
  score_histogram: { edges: number[]; counts: number[] };
  flagged: { row_index: number; row_id: string | null; score: number; reasons: { feature: string; robust_z?: number; kind: string }[] }[];
  warning: string;
}

export type DriftLevel = "stable" | "moderate" | "significant" | "insufficient_data";
export interface DriftColumn {
  column: string; type: "numeric" | "categorical"; level: DriftLevel;
  psi: number | null; p_value: number | null; p_value_adjusted: number | null; test_significant: boolean | null;
  mean_shift_std?: number | null; unseen_categories?: { value: string; share: number }[]; notes: string[];
}
export interface DriftResult {
  n_reference: number; n_current: number; columns_analyzed: number; columns_drifted: number; share_drifted: number;
  dataset_drift: boolean; columns: DriftColumn[]; warnings: string[]; config: Record<string, number>;
}
export interface DriftThresholds { psi_warn: number; psi_alert: number; p_threshold: number; dataset_share: number; min_samples: number; bins: number }

export interface CompareRow {
  experiment_id: string; dataset_id: string; target: string; task: Task; selected_model: string;
  primary_metric: { name: string; direction: "higher" | "lower" }; validation: Metrics; test: Metrics; baseline_test: Metrics; seed: number; rows_used: number;
}
export interface CompareResponse { experiments: CompareRow[]; notes: string[] }

export interface ServerSettings {
  version: string; environment: string; auth_required: boolean; retention_days: number; max_upload_mb: number;
  max_rows: number; max_cols: number; rate_limit_per_minute: number; native_accelerator: boolean; synthetic_demo_available: boolean;
}
export interface Health { status: "ok" | "degraded"; version: string; database: "ok" | "unavailable" }
