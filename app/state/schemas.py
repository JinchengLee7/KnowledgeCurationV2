"""Shared, architecture-neutral data schemas.

These dataclasses are used by every architecture (baseline, single-agent,
multi-agent) so that runs are directly comparable. Keep them stable: the
baseline stores its richer, architecture-specific detail in per-run artifact
files rather than bloating these shared shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PaperIdentifiers:
    """Persistent external identifiers for a paper.

    All fields are optional; a paper is identified by whichever are present,
    in priority order (see app.architectures.baseline.identity).
    """

    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    openalex_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    corpus_id: Optional[str] = None
    pmid: Optional[str] = None


@dataclass
class PaperCandidate:
    """A candidate paper flowing through the pipeline.

    The same shape is used for accepted papers and rejected candidates; the
    ``rejection_reason`` distinguishes them. Optional metadata fields default
    safely so partial records never crash serialization.
    """

    title: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    identifiers: PaperIdentifiers = field(default_factory=PaperIdentifiers)
    sources: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    # Scoring
    score: float = 0.0
    score_components: Dict[str, float] = field(default_factory=dict)
    score_method: Optional[str] = None

    # Disposition / identity
    rejection_reason: Optional[str] = None
    paper_id: Optional[str] = None

    # Richer metadata (filled when available; never required)
    citation_count: Optional[int] = None
    reference_count: Optional[int] = None
    influential_citation_count: Optional[int] = None
    venue: Optional[str] = None
    publication_date: Optional[str] = None
    fields_of_study: List[str] = field(default_factory=list)
    publication_types: List[str] = field(default_factory=list)

    # Provenance (which architectures/sources observed this paper)
    provenance: Dict[str, Any] = field(default_factory=dict)

    # Optional embedding score, reserved for a future fixed (non-LLM) scorer.
    embedding_score: Optional[float] = None


@dataclass
class SurveyConfig:
    """Parsed survey configuration.

    Documented fields are first-class; optional extended blocks
    (``baseline``, ``semantic_scholar``, ``target_papers``, ``evaluation``)
    are kept as plain dicts and accessed with safe defaults so the code never
    assumes they exist.
    """

    topic_overview: str
    research_questions: List[str] = field(default_factory=list)
    question_context: str = ""
    query_hints: List[str] = field(default_factory=list)
    timeline_from_year: Optional[int] = None
    timeline_to_year: Optional[int] = None
    min_relevance_score: float = 0.0

    # Optional / extended (safe defaults)
    question_mode: Optional[int] = None
    target_papers: List[Dict[str, Any]] = field(default_factory=list)
    baseline: Dict[str, Any] = field(default_factory=dict)
    semantic_scholar: Dict[str, Any] = field(default_factory=dict)
    evaluation: Dict[str, Any] = field(default_factory=dict)

    # The original parsed JSON, preserved for republishing verbatim.
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ManagerRunResult:
    """Flat, comparable run summary returned by every architecture.

    Rich nested detail (crawl/verification/dedupe/target breakdowns) is written
    to per-run artifact files by the baseline; this object stays flat so all
    architectures can be tabulated side by side.
    """

    architecture: str
    queries_generated: int
    sources_queried: List[str]
    candidates_found: int
    candidates_after_dedupe: int
    papers_accepted: int
    candidates_rejected: int
    dry_run: bool
    started_at: str
    finished_at: str
    status: str = "success"  # success | partial_success | failure
    run_id: str = ""
    errors: List[str] = field(default_factory=list)
