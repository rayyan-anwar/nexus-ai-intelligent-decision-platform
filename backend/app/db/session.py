"""Engine and session management. No module-level globals: the app owns a ``Database`` instance."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str) -> Engine:
    parsed = make_url(url)
    kwargs: dict = {"pool_pre_ping": True}
    if parsed.get_backend_name() == "sqlite":
        if parsed.database and parsed.database != ":memory:":
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if parsed.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - exercised on SQLite only
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


class Database:
    def __init__(self, url: str):
        self.engine = make_engine(url)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def ping(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001
            return False

    def dispose(self) -> None:
        self.engine.dispose()
