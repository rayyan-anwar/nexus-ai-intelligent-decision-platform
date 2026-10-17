"""Environment-based configuration (stdlib only). Every variable is prefixed NEXUS_."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MIGRATIONS_DIR = REPO_ROOT / "database" / "migrations"
DEFAULT_SAMPLE_CSV = REPO_ROOT / "data" / "sample" / "nexus_synthetic_accounts.csv"


def _split(value: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in value.split(",") if p.strip())


def _int(env: dict, name: str, default: int, lo: int, hi: int) -> int:
    raw = env.get(name)
    if raw in (None, ""):
        return default
    try:
        val = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not lo <= val <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return val


def _bool(env: dict, name: str, default: bool) -> bool:
    raw = env.get(name)
    return default if raw in (None, "") else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    database_url: str = "sqlite:///./var/nexus.db"
    data_dir: Path = Path("./var")
    migrations_dir: Path = DEFAULT_MIGRATIONS_DIR
    sample_csv: Path = DEFAULT_SAMPLE_CSV
    max_upload_bytes: int = 10 * 1024 * 1024
    max_rows: int = 200_000
    max_cols: int = 200
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    api_token_hashes: tuple[str, ...] = ()
    admin_token_hashes: tuple[str, ...] = ()
    rate_limit_per_minute: int = 120
    retention_days: int = 30
    training_workers: int = 1
    log_level: str = "INFO"
    run_migrations: bool = True
    trust_proxy_headers: bool = False

    # ------------------------------------------------------------------ #
    @classmethod
    def from_env(cls, env: dict | None = None) -> Settings:
        e = dict(os.environ if env is None else env)
        get = lambda k, d="": e.get(k, d) or d  # noqa: E731
        return cls(
            env=get("NEXUS_ENV", "development").lower(),
            database_url=get("NEXUS_DATABASE_URL", cls.database_url),
            data_dir=Path(get("NEXUS_DATA_DIR", "./var")),
            migrations_dir=Path(get("NEXUS_MIGRATIONS_DIR", str(DEFAULT_MIGRATIONS_DIR))),
            sample_csv=Path(get("NEXUS_SAMPLE_CSV", str(DEFAULT_SAMPLE_CSV))),
            max_upload_bytes=_int(e, "NEXUS_MAX_UPLOAD_MB", 10, 1, 500) * 1024 * 1024,
            max_rows=_int(e, "NEXUS_MAX_ROWS", 200_000, 100, 5_000_000),
            max_cols=_int(e, "NEXUS_MAX_COLS", 200, 2, 2000),
            cors_origins=_split(get("NEXUS_CORS_ORIGINS", "http://localhost:5173")),
            api_token_hashes=_split(get("NEXUS_API_TOKEN_HASHES")),
            admin_token_hashes=_split(get("NEXUS_ADMIN_TOKEN_HASHES")),
            rate_limit_per_minute=_int(e, "NEXUS_RATE_LIMIT_PER_MINUTE", 120, 0, 100_000),
            retention_days=_int(e, "NEXUS_RETENTION_DAYS", 30, 0, 3650),
            training_workers=_int(e, "NEXUS_TRAINING_WORKERS", 1, 1, 16),
            log_level=get("NEXUS_LOG_LEVEL", "INFO").upper(),
            run_migrations=_bool(e, "NEXUS_RUN_MIGRATIONS", True),
            trust_proxy_headers=_bool(e, "NEXUS_TRUST_PROXY_HEADERS", False),
        )

    # ------------------------------------------------------------------ #
    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def auth_required(self) -> bool:
        return self.is_production or bool(self.api_token_hashes or self.admin_token_hashes)

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / "datasets"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def safe_database_url(self) -> str:
        """Database URL with any password masked (safe to log)."""
        parts = urlsplit(self.database_url)
        if parts.password:
            netloc = parts.netloc.replace(f":{parts.password}@", ":***@")
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
        return self.database_url

    def problems(self) -> list[str]:
        """Configuration errors that must stop the server from starting."""
        issues: list[str] = []
        if self.env not in {"development", "test", "production"}:
            issues.append("NEXUS_ENV must be development, test or production.")
        if self.is_production:
            if not (self.api_token_hashes or self.admin_token_hashes):
                issues.append("Production requires NEXUS_API_TOKEN_HASHES and/or NEXUS_ADMIN_TOKEN_HASHES.")
            if "*" in self.cors_origins:
                issues.append("Production must not allow wildcard CORS origins.")
            if self.database_url.startswith("sqlite"):
                issues.append("Production should use PostgreSQL (NEXUS_DATABASE_URL), not SQLite.")
        for h in self.api_token_hashes + self.admin_token_hashes:
            if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
                issues.append("Token hashes must be 64-character lowercase hex SHA-256 digests.")
                break
        return issues
