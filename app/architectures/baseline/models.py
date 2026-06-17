"""Baseline-local dataclasses not part of the shared schema.

These capture the richer, architecture-specific detail the baseline records in
artifacts, SQLite, and merge/reject logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GeneratedQuery:
    """A deterministic query plus its provenance."""

    query: str  # cleaned query string actually sent to the API
    original: str  # original source string before cleaning
    kind: str  # topic | research_question | query_hint | combined
    index: int  # stable ordering index


@dataclass
class ScoreComponents:
    """Normalized [0,1] components behind a relevance score."""

    title_keyword_overlap: float = 0.0
    abstract_keyword_overlap: float = 0.0
    query_phrase_match: float = 0.0
    recency_score: float = 0.0
    identifier_score: float = 0.0
    citation_score: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "title_keyword_overlap": round(self.title_keyword_overlap, 4),
            "abstract_keyword_overlap": round(self.abstract_keyword_overlap, 4),
            "query_phrase_match": round(self.query_phrase_match, 4),
            "recency_score": round(self.recency_score, 4),
            "identifier_score": round(self.identifier_score, 4),
            "citation_score": round(self.citation_score, 4),
        }


@dataclass
class RejectRecord:
    """A rejected candidate with an explainable reason and evidence."""

    candidate_id: Optional[str]
    run_id: str
    architecture: str
    source: str
    query: Optional[str]
    title: Optional[str]
    year: Optional[int]
    reason: str
    score: Optional[float]
    evidence: Dict[str, Any] = field(default_factory=dict)
    raw_ref: Optional[str] = None
    created_at: str = ""


@dataclass
class MergeEvent:
    """Records that a candidate was merged into an existing paper."""

    run_id: str
    existing_paper_id: str
    candidate_id: Optional[str]
    matched_on: str  # doi | arxiv | s2 | corpus | external | fingerprint
    source: str
    query: Optional[str]
    created_at: str = ""


@dataclass
class SourceHit:
    """One observation of a paper from a source/query during a run."""

    paper_id: str
    run_id: str
    architecture: str
    source: str
    query: Optional[str]
    rank: Optional[int]
    retrieved_at: str
    raw_json_hash: Optional[str] = None


@dataclass
class TargetCheckResult:
    """Whether a configured target paper was found and accepted."""

    target_title: Optional[str]
    must_find: bool
    found: bool
    found_by: Optional[str] = None
    paper_id: Optional[str] = None
    was_accepted: bool = False
    rank_position: Optional[int] = None
    rejection_reason: Optional[str] = None


@dataclass
class RunMetrics:
    """Per-run metrics for efficiency and architecture comparison."""

    runtime_seconds: float = 0.0
    api_call_count: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    raw_candidate_count: int = 0
    normalized_candidate_count: int = 0
    deduplicated_candidate_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    merge_count: int = 0
    new_paper_count: int = 0
    updated_paper_count: int = 0
    error_count: int = 0
    avg_api_latency_ms: float = 0.0
    db_write_time_ms: float = 0.0
    publish_time_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}
