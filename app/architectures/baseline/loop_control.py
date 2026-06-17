"""Deterministic feedback-loop rules across repeated runs.

This is a transparent state machine over ``query_state`` and run history — NOT a
hidden agent. Each rule is documented and fires on simple thresholds. The
pipeline calls :func:`plan_adjustments` BEFORE querying to adapt the run, and
:func:`record_query_outcomes` AFTER to update state for next time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

import sqlite3

from app.architectures.baseline import db

_WS = re.compile(r"\s+")

# Rule thresholds (documented, deterministic).
DEAD_QUERY_RUNS = 3          # zero accepts for N runs -> deprioritize
HIGH_DUP_RATE = 0.80         # duplicate rate above this -> prefer recency
LOW_ACCEPT_MIN = 5           # fewer accepts than this -> enable hints+combined
RATE_LIMIT_THRESHOLD = 5     # 429s above this in a run -> throttle


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def query_norm(q: str) -> str:
    return _WS.sub(" ", (q or "").lower()).strip()


@dataclass
class LoopAdjustments:
    """Adjustments applied to the upcoming run, with human-readable reasons."""

    deprioritized_queries: List[str] = field(default_factory=list)
    prefer_recency: bool = False
    enable_hints_and_combined: bool = False
    throttle: bool = False
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "deprioritized_queries": self.deprioritized_queries,
            "prefer_recency": self.prefer_recency,
            "enable_hints_and_combined": self.enable_hints_and_combined,
            "throttle": self.throttle,
            "notes": self.notes,
        }


def plan_adjustments(conn: sqlite3.Connection) -> LoopAdjustments:
    """Inspect persisted state and decide deterministic adjustments."""
    adj = LoopAdjustments()
    state = db.get_query_state(conn)
    for qnorm, row in sorted(state.items()):
        if row.get("consecutive_zero_accept", 0) >= DEAD_QUERY_RUNS:
            adj.deprioritized_queries.append(qnorm)
    if adj.deprioritized_queries:
        adj.notes.append(
            f"{len(adj.deprioritized_queries)} query(ies) deprioritized after "
            f"{DEAD_QUERY_RUNS}+ zero-accept runs"
        )
    return adj


def record_query_outcomes(
    conn: sqlite3.Connection,
    per_query: Dict[str, Dict[str, int]],
) -> None:
    """Update query_state from this run's per-query outcomes.

    ``per_query`` maps original query -> {candidates, accepted, duplicates, errors}.
    """
    now = _now()
    with db.transaction(conn):
        for original, counts in sorted(per_query.items()):
            db.update_query_state(
                conn,
                query_norm=query_norm(original),
                query_original=original,
                candidates=counts.get("candidates", 0),
                accepted=counts.get("accepted", 0),
                duplicates=counts.get("duplicates", 0),
                errors=counts.get("errors", 0),
                now=now,
            )
