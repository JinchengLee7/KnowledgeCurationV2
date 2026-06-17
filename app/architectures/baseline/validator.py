"""Candidate validation and light, deterministic repair.

Returns a validation verdict rather than raising, so the pipeline can fail soft
on a per-candidate basis. Only repairs trivial issues (whitespace); anything
worse is flagged for rejection with a closed-vocabulary reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.architectures.baseline import constants
from app.state.schemas import PaperCandidate

_WS = re.compile(r"\s+")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass
class ValidationResult:
    ok: bool
    candidate: PaperCandidate
    reason: Optional[str] = None  # closed-vocab reject reason when not ok


def _clean(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    text = _CTRL.sub("", text)
    text = _WS.sub(" ", text).strip()
    return text or None


def validate(candidate: PaperCandidate, min_title_tokens: int = 1) -> ValidationResult:
    """Validate (and lightly repair) a candidate.

    Rejects when the title is missing/too short. Does NOT reject for missing
    abstract or PDF (per spec). Returns the possibly-repaired candidate.
    """
    title = _clean(candidate.title)
    if not title:
        return ValidationResult(False, candidate, constants.REASON_MISSING_TITLE)

    if len(title.split()) < max(1, min_title_tokens):
        return ValidationResult(False, candidate, constants.REASON_MISSING_TITLE)

    candidate.title = title
    candidate.abstract = _clean(candidate.abstract)

    # Coerce year to int when feasible; drop if nonsensical.
    if candidate.year is not None:
        try:
            candidate.year = int(candidate.year)
        except (TypeError, ValueError):
            candidate.year = None

    return ValidationResult(True, candidate, None)
