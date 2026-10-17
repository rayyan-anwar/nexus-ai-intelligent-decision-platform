"""Safe file naming and atomic writes."""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from pathlib import Path

_BAD = re.compile(r"[\x00-\x1f\x7f<>:\"|?*\\/]")


def display_name(filename: str | None, default: str = "upload.csv") -> str:
    """A cosmetic, length-limited name for UI display only. Never used to build paths."""
    if not filename:
        return default
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = _BAD.sub("", name).strip(" .")
    return name[:100] or default


def new_stored_name(prefix: str, ext: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}.{ext.lstrip('.')}"


def write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def resolve_inside(base: Path, filename: str) -> Path:
    """Join and verify the result stays within ``base`` (defence in depth against traversal)."""
    candidate = (base / filename).resolve()
    if base.resolve() not in candidate.parents:
        raise ValueError("path escapes the data directory")
    return candidate
