"""Deterministic accept/reject filtering.

Reject reasons come from the closed vocabulary in ``constants``. A candidate is
rejected for: missing title, below-threshold score, or (when strict timeline is
enabled) a year outside the window. Missing abstract/PDF are NOT rejection
reasons. Every reject carries explainable evidence.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Set, Tuple

from app.architectures.baseline import constants
from app.architectures.baseline.models import RejectRecord
from app.state.schemas import PaperCandidate, SurveyConfig

_TOKEN = re.compile(r"[a-z0-9]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matched_missing_terms(candidate: PaperCandidate, config: SurveyConfig
                           ) -> Tuple[List[str], List[str]]:
    terms: Set[str] = set()
    for part in [config.topic_overview, *config.research_questions, *config.query_hints]:
        for t in _TOKEN.findall((part or "").lower()):
            if t not in constants.STOPWORDS and len(t) >= 2:
                terms.add(t)
    text = f"{candidate.title or ''} {candidate.abstract or ''}".lower()
    text_tokens = set(_TOKEN.findall(text))
    matched = sorted(terms & text_tokens)
    missing = sorted(terms - text_tokens)
    return matched, missing


def apply_filters(
    candidates: List[PaperCandidate],
    config: SurveyConfig,
    run_id: str,
) -> Tuple[List[PaperCandidate], List[RejectRecord]]:
    """Split scored candidates into (accepted, reject_records).

    Candidates are assumed already scored. Accepted candidates are returned
    sorted deterministically (score desc, then paper_id) for stable output.
    """
    threshold = config.min_relevance_score
    strict_timeline = bool(config.baseline.get("strict_timeline", False))
    lo, hi = config.timeline_from_year, config.timeline_to_year

    accepted: List[PaperCandidate] = []
    rejects: List[RejectRecord] = []

    for c in candidates:
        reason = None
        evidence: dict = {}

        if not (c.title or "").strip():
            reason = constants.REASON_MISSING_TITLE
        elif strict_timeline and c.year is not None and lo is not None and hi is not None \
                and not (lo <= c.year <= hi):
            reason = constants.REASON_OUTSIDE_TIMELINE
            evidence = {"year": c.year, "timeline_from": lo, "timeline_to": hi}
        elif c.score < threshold:
            reason = constants.REASON_BELOW_THRESHOLD
            matched, missing = _matched_missing_terms(c, config)
            evidence = {
                "threshold": threshold,
                "score": c.score,
                "matched_terms": matched[:25],
                "missing_terms": missing[:25],
            }

        if reason is None:
            accepted.append(c)
        else:
            c.rejection_reason = reason
            rejects.append(
                RejectRecord(
                    candidate_id=c.paper_id,
                    run_id=run_id,
                    architecture=constants.ARCHITECTURE,
                    source=constants.SOURCE,
                    query=None,
                    title=c.title,
                    year=c.year,
                    reason=reason,
                    score=c.score,
                    evidence=evidence,
                    created_at=_now(),
                )
            )

    accepted.sort(key=lambda x: (-x.score, x.paper_id or ""))
    return accepted, rejects
