"""Request and response schemas (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ID_PATTERN = r"^[A-Za-z0-9_\-]{1,40}$"
Task = Literal["binary", "multiclass", "regression"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ok", "unavailable"]


class SettingsOut(BaseModel):
    version: str
    environment: str
    auth_required: bool
    retention_days: int
    max_upload_mb: int
    max_rows: int
    max_cols: int
    rate_limit_per_minute: int
    native_accelerator: bool
    synthetic_demo_available: bool


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    n_rows: int
    n_cols: int
    size_bytes: int
    sha256: str
    is_synthetic: bool
    created_at: datetime
    expires_at: datetime | None


class ExperimentCreate(Strict):
    dataset_id: str = Field(pattern=ID_PATTERN)
    target: str = Field(min_length=1, max_length=100)
    task: Task | None = None
    seed: int = Field(42, ge=0, le=2**31 - 1)
    test_size: float = Field(0.2, ge=0.05, le=0.5)
    val_size: float = Field(0.2, ge=0.05, le=0.5)
    model_names: list[str] | None = Field(None, max_length=10)
    exclude_columns: list[str] = Field(default_factory=list, max_length=200)
    positive_label: str | None = Field(None, max_length=100)


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dataset_id: str
    target: str
    task: str | None
    status: str
    progress: float
    stage: str | None
    seed: int
    error_message: str | None
    model_id: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ModelOut(BaseModel):
    id: str
    experiment_id: str
    name: str
    task: str
    target: str
    created_at: datetime
    primary_metric: str | None = None
    test_score: float | None = None


class PredictRequest(Strict):
    records: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


class LocalExplainRequest(Strict):
    record: dict[str, Any]
    target_class: str | None = Field(None, max_length=100)
    n_permutations: int = Field(30, ge=1, le=100)
    seed: int = Field(0, ge=0, le=2**31 - 1)


class AnomalyRequest(Strict):
    dataset_id: str = Field(pattern=ID_PATTERN)
    sensitivity: Literal["low", "medium", "high"] | float = "medium"
    seed: int = Field(42, ge=0, le=2**31 - 1)
    columns: list[str] | None = Field(None, max_length=200)
    max_rows: int = Field(200, ge=1, le=1000)
    include_scores: bool = False


class DriftThresholds(Strict):
    psi_warn: float = Field(0.1, gt=0, le=5)
    psi_alert: float = Field(0.25, gt=0, le=10)
    p_threshold: float = Field(0.05, gt=0, lt=1)
    dataset_share: float = Field(0.3, gt=0, le=1)
    min_samples: int = Field(30, ge=2, le=100_000)
    bins: int = Field(10, ge=2, le=50)

    @model_validator(mode="after")
    def _ordered(self) -> "DriftThresholds":
        if self.psi_warn >= self.psi_alert:
            raise ValueError("psi_warn must be smaller than psi_alert")
        return self


class DriftRequest(Strict):
    reference_dataset_id: str = Field(pattern=ID_PATTERN)
    current_dataset_id: str = Field(pattern=ID_PATTERN)
    columns: list[str] | None = Field(None, max_length=200)
    thresholds: DriftThresholds = DriftThresholds()


class PurgeOut(BaseModel):
    datasets_deleted: int
