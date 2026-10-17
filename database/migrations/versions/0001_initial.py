"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TASK_CHECK = "task IN ('binary', 'multiclass', 'regression')"


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("stored_filename", sa.String(100), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("n_rows", sa.Integer, nullable=False),
        sa.Column("n_cols", sa.Integer, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("profile_json", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.CheckConstraint("n_rows >= 0", name="ck_datasets_n_rows"),
        sa.CheckConstraint("n_cols >= 1", name="ck_datasets_n_cols"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_datasets_size_bytes"),
    )
    op.create_index("ix_datasets_sha256", "datasets", ["sha256"])
    op.create_index("ix_datasets_expires_at", "datasets", ["expires_at"])

    op.create_table(
        "experiments",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("dataset_id", sa.String(40), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("task", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress", sa.Float, nullable=False, server_default="0"),
        sa.Column("stage", sa.String(100), nullable=True),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column("dataset_fingerprint", sa.String(64), nullable=False),
        sa.Column("config_json", sa.JSON, nullable=False),
        sa.Column("summary_json", sa.JSON, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.CheckConstraint(TASK_CHECK, name="ck_experiments_task"),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_experiments_status"),
        sa.CheckConstraint("progress >= 0 AND progress <= 1", name="ck_experiments_progress"),
    )
    op.create_index("ix_experiments_dataset_id", "experiments", ["dataset_id"])
    op.create_index("ix_experiments_status_created", "experiments", ["status", "created_at"])

    op.create_table(
        "models",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("experiment_id", sa.String(40), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("task", sa.String(20), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("artifact_filename", sa.String(100), nullable=False, unique=True),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.CheckConstraint(TASK_CHECK, name="ck_models_task"),
    )
    op.create_index("ix_models_target_created", "models", ["target", "created_at"])

    op.create_table(
        "prediction_events",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("model_id", sa.String(40), sa.ForeignKey("models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("n_records", sa.Integer, nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("summary_json", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("n_records > 0", name="ck_prediction_events_n_records"),
    )
    op.create_index("ix_prediction_events_model_created", "prediction_events", ["model_id", "created_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(40), nullable=True),
        sa.Column("detail_json", sa.JSON, nullable=True),
    )
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index("ix_audit_events_resource", "audit_events", ["resource_type", "resource_id"])


def downgrade() -> None:
    for table in ("audit_events", "prediction_events", "models", "experiments", "datasets"):
        op.drop_table(table)
