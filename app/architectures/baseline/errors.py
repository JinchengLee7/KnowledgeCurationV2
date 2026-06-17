"""Structured baseline exceptions.

A single, explicit hierarchy makes failures classifiable for fail-soft handling
and reporting. ``ConfigError`` is the shared one from :mod:`app.config`,
re-exported so the baseline has one error namespace.
"""

from __future__ import annotations

from app.config import ConfigError  # re-exported

__all__ = [
    "BaselineError",
    "ConfigError",
    "SemanticScholarAPIError",
    "RateLimitError",
    "APIResponseError",
    "CandidateValidationError",
    "IdentityResolutionError",
    "DatabaseWriteError",
    "PublishError",
    "ExportError",
]


class BaselineError(Exception):
    """Base class for all baseline-specific errors."""


class SemanticScholarAPIError(BaselineError):
    """A Semantic Scholar request failed after retries."""


class RateLimitError(SemanticScholarAPIError):
    """The API returned HTTP 429 (rate limited)."""


class APIResponseError(SemanticScholarAPIError):
    """The API returned an unexpected status or unparseable body."""


class CandidateValidationError(BaselineError):
    """A candidate record could not be validated/repaired."""


class IdentityResolutionError(BaselineError):
    """Identity normalization or id generation failed."""


class DatabaseWriteError(BaselineError):
    """A SQLite write/transaction failed."""


class PublishError(BaselineError):
    """Publishing to site/data failed."""


class ExportError(BaselineError):
    """Exporting canonical NDJSON/JSON failed."""
