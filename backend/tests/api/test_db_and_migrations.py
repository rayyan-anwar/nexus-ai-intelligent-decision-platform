from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.db.base import Base
from app.db.migrate import upgrade_to_head
from app.db.session import Database
from app.core.config import DEFAULT_MIGRATIONS_DIR

NOW = datetime(2026, 1, 1)


@pytest.fixture()
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'm.db'}")
    upgrade_to_head(f"sqlite:///{tmp_path / 'm.db'}", DEFAULT_MIGRATIONS_DIR)
    yield database
    database.dispose()


def _dataset(i="ds1", fname="f.csv"):
    return models.Dataset(id=i, name="n", stored_filename=fname, sha256="h", n_rows=1, n_cols=1, size_bytes=1, profile_json={}, created_at=NOW)


def test_migration_matches_orm_metadata(tmp_path):
    url = f"sqlite:///{tmp_path / 'check.db'}"
    upgrade_to_head(url, DEFAULT_MIGRATIONS_DIR)
    insp = inspect(create_engine(url))
    for name, table in Base.metadata.tables.items():
        assert name in insp.get_table_names(), name
        assert {c["name"] for c in insp.get_columns(name)} == {c.name for c in table.columns}, name
        assert {i["name"] for i in insp.get_indexes(name)} >= {i.name for i in table.indexes}, name


def test_cascade_delete_and_foreign_keys(db):
    with db.session() as s:
        s.add(_dataset())
        s.add(models.Experiment(id="e1", dataset_id="ds1", target="t", status="queued", seed=1, dataset_fingerprint="f", config_json={}, created_at=NOW))
    with db.session() as s:
        s.add(models.ModelRecord(id="m1", experiment_id="e1", name="rf", task="binary", target="t", artifact_filename="m.joblib", artifact_sha256="x", metadata_json={}, created_at=NOW))
    with db.session() as s:
        s.delete(s.get(models.Dataset, "ds1"))
    with db.session() as s:
        assert s.get(models.Experiment, "e1") is None and s.get(models.ModelRecord, "m1") is None
    with pytest.raises(IntegrityError), db.session() as s:
        s.add(models.Experiment(id="e2", dataset_id="missing", target="t", status="queued", seed=1, dataset_fingerprint="f", config_json={}, created_at=NOW))


def test_check_and_unique_constraints(db):
    with pytest.raises(IntegrityError), db.session() as s:
        s.add(models.Experiment(id="e3", dataset_id="x", target="t", status="bogus", seed=1, dataset_fingerprint="f", config_json={}, created_at=NOW))
    with db.session() as s:
        s.add(_dataset("a", "same.csv"))
    with pytest.raises(IntegrityError), db.session() as s:
        s.add(_dataset("b", "same.csv"))
