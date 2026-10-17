"""ORM models. Alembic migration 0001 mirrors these; database/sql/schema.sql is a readable snapshot.

Timestamps are naive UTC. Raw dataset rows are NOT stored in the database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

TASK_CHECK = "task IN ('binary', 'multiclass', 'regression')"


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint("n_rows >= 0", name="ck_datasets_n_rows"),
        CheckConstraint("n_cols >= 1", name="ck_datasets_n_cols"),
        CheckConstraint("size_bytes >= 0", name="ck_datasets_size_bytes"),
        Index("ix_datasets_sha256", "sha256"),
        Index("ix_datasets_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    n_cols: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    experiments: Mapped[list[Experiment]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        CheckConstraint(TASK_CHECK, name="ck_experiments_task"),
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_experiments_status"),
        CheckConstraint("progress >= 0 AND progress <= 1", name="ck_experiments_progress"),
        Index("ix_experiments_dataset_id", "dataset_id"),
        Index("ix_experiments_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    target: Mapped[str] = mapped_column(String(100), nullable=False)
    task: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="experiments")
    model: Mapped[ModelRecord | None] = relationship(
        back_populates="experiment", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def model_id(self) -> str | None:
        return self.model.id if self.model is not None else None


class ModelRecord(Base):
    __tablename__ = "models"
    __table_args__ = (
        CheckConstraint(TASK_CHECK, name="ck_models_task"),
        Index("ix_models_target_created", "target", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    task: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[str] = mapped_column(String(100), nullable=False)
    artifact_filename: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    experiment: Mapped[Experiment] = relationship(back_populates="model")
    predictions: Mapped[list[PredictionEvent]] = relationship(
        back_populates="model", cascade="all, delete-orphan", passive_deletes=True
    )


class PredictionEvent(Base):
    __tablename__ = "prediction_events"
    __table_args__ = (
        CheckConstraint("n_records > 0", name="ck_prediction_events_n_records"),
        Index("ix_prediction_events_model_created", "model_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    n_records: Mapped[int] = mapped_column(Integer, nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)  # hash only; inputs are never stored
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    model: Mapped[ModelRecord] = relationship(back_populates="predictions")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_resource", "resource_type", "resource_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detail_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
