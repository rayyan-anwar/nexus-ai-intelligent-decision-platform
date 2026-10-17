"""Safe CSV ingestion and safe CSV export."""

from __future__ import annotations

import csv
import io
import re

import pandas as pd

from .errors import DataValidationError

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def load_csv_bytes(
    content: bytes,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    max_rows: int = 200_000,
    max_cols: int = 200,
) -> pd.DataFrame:
    """Parse and validate uploaded CSV bytes. Raises :class:`DataValidationError`."""
    if not content or not content.strip():
        raise DataValidationError("The file is empty.", code="empty_file")
    if len(content) > max_bytes:
        raise DataValidationError(
            f"The file exceeds the {max_bytes // (1024 * 1024)} MB upload limit.", code="file_too_large"
        )
    if b"\x00" in content[:8192]:
        raise DataValidationError("The file does not look like a text CSV file.", code="not_text")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataValidationError("The file must be UTF-8 encoded.", code="bad_encoding") from exc

    try:
        header = next(csv.reader(io.StringIO(text)))
    except (StopIteration, csv.Error) as exc:
        raise DataValidationError("Could not read a header row.", code="bad_header") from exc
    names = [h.strip() for h in header]
    if any(not h for h in names):
        raise DataValidationError("Every column needs a non-empty name.", code="bad_header")
    if len(set(names)) != len(names):
        raise DataValidationError("Column names must be unique.", code="duplicate_columns")
    if any(len(h) > 100 or _CONTROL.search(h) for h in names):
        raise DataValidationError("Column names must be under 100 characters and contain no control characters.", code="bad_header")
    if len(names) > max_cols:
        raise DataValidationError(f"The file has more than {max_cols} columns.", code="too_many_columns")

    try:
        df = pd.read_csv(io.StringIO(text), skipinitialspace=True)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
        raise DataValidationError("The CSV could not be parsed. Check delimiters and quoting.", code="parse_error") from exc

    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(axis=0, how="all").reset_index(drop=True)
    if df.shape[0] == 0:
        raise DataValidationError("The file contains a header but no data rows.", code="no_rows")
    if df.shape[0] > max_rows:
        raise DataValidationError(f"The file has more than {max_rows:,} rows.", code="too_many_rows")
    return df


def read_stored_csv(path) -> pd.DataFrame:
    """Re-read a CSV that was validated at upload time (same parser settings)."""
    df = pd.read_csv(path, skipinitialspace=True, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(axis=0, how="all").reset_index(drop=True)


def sanitize_cell(value):
    """Neutralise spreadsheet formula injection in exported text cells."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def to_safe_csv(df: pd.DataFrame) -> str:
    """Serialise a frame to CSV with formula-injection protection on text cells and headers."""
    out = df.copy()
    for col in out.columns:
        if not pd.api.types.is_numeric_dtype(out[col]) and not pd.api.types.is_bool_dtype(out[col]):
            out[col] = out[col].map(sanitize_cell)
    out.columns = [sanitize_cell(str(c)) for c in out.columns]
    return out.to_csv(index=False)
