"""Run Alembic migrations programmatically (single code path for dev, Docker and production)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url


def alembic_config(database_url: str, migrations_dir: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def upgrade_to_head(database_url: str, migrations_dir: Path) -> None:
    parsed = make_url(database_url)
    if parsed.get_backend_name() == "sqlite" and parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(database_url, migrations_dir), "head")
