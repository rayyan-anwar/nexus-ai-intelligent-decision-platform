"""Exception types raised by the machine-learning layer.

They carry a *safe* message (never raw data) that the API layer can return
to clients without further sanitising.
"""

from __future__ import annotations

from typing import Any


class MLError(Exception):
    code = "ml_error"

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}


class DataValidationError(MLError):
    code = "invalid_data"


class UnsupportedTaskError(MLError):
    code = "unsupported_task"


class PredictionInputError(MLError):
    code = "invalid_prediction_input"


class ArtifactError(MLError):
    code = "artifact_error"
