"""Deduplication and metadata merging.

Two stages:
  1. intra-run: collapse duplicate candidates returned across queries.
  2. against-DB: match a candidate to an existing paper and merge, or insert new.

Merge rules never overwrite good metadata with null/lower-quality data.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from app.architectures.baseline import db, identity
from app.architectures.baseline.models import MergeEvent
from app.state.schemas import PaperCandidate, PaperIdentifiers


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _merge_identifiers(a: PaperIdentifiers, b: PaperIdentifiers) -> PaperIdentifiers:
    """Fill missing identifiers in ``a`` from ``b`` (never overwrite present)."""
    return PaperIdentifiers(
        doi=a.doi or b.doi,
        arxiv_id=a.arxiv_id or b.arxiv_id,
        openalex_id=a.openalex_id or b.openalex_id,
        semantic_scholar_id=a.semantic_scholar_id or b.semantic_scholar_id,
        corpus_id=a.corpus_id or b.corpus_id,
        pmid=a.pmid or b.pmid,
    )


def merge_candidates(primary: PaperCandidate, new: PaperCandidate) -> PaperCandidate:
    """Merge ``new`` into ``primary`` following spec preference rules.

    primary is mutated and returned.
    """
    # Title: keep existing unless the new one is longer and non-empty.
    if new.title and len(new.title) > len(primary.title or ""):
        primary.title = new.title

    # Abstract: keep the longer non-empty abstract.
    if new.abstract and len(new.abstract) > len(primary.abstract or ""):
        primary.abstract = new.abstract

    # Year: fill if missing.
    if primary.year is None and new.year is not None:
        primary.year = new.year

    # Authors: keep the richer (longer) list.
    if len(new.authors) > len(primary.authors):
        primary.authors = list(new.authors)

    # URLs: prefer existing; fill if missing. Never overwrite a PDF with null.
    primary.url = primary.url or new.url
    primary.pdf_url = primary.pdf_url or new.pdf_url

    # Identifiers: union (fill missing).
    primary.identifiers = _merge_identifiers(primary.identifiers, new.identifiers)

    # Citation metadata: take the latest observed (max, treating None as 0).
    for attr in ("citation_count", "reference_count", "influential_citation_count"):
        new_val = getattr(new, attr)
        if new_val is not None:
            cur = getattr(primary, attr)
            setattr(primary, attr, new_val if cur is None else max(cur, new_val))

    primary.venue = primary.venue or new.venue
    primary.publication_date = primary.publication_date or new.publication_date
    primary.fields_of_study = primary.fields_of_study or list(new.fields_of_study)
    primary.publication_types = primary.publication_types or list(new.publication_types)

    # Sources: union, order-preserving.
    for s in new.sources:
        if s not in primary.sources:
            primary.sources.append(s)

    return primary


def dedupe_candidates(candidates: List[PaperCandidate]) -> Tuple[List[PaperCandidate], int]:
    """Collapse intra-run duplicates by stable paper id.

    Returns (unique_candidates, intra_run_duplicate_count). Order is preserved
    by first appearance for determinism.
    """
    by_id: dict[str, PaperCandidate] = {}
    order: List[str] = []
    duplicates = 0
    for c in candidates:
        c.paper_id = identity.stable_paper_id(c)
        if c.paper_id in by_id:
            merge_candidates(by_id[c.paper_id], c)
            duplicates += 1
        else:
            by_id[c.paper_id] = c
            order.append(c.paper_id)
    return [by_id[pid] for pid in order], duplicates


def resolve_against_db(
    conn: sqlite3.Connection,
    candidate: PaperCandidate,
    run_id: str,
    query: Optional[str],
    source: str,
) -> Tuple[PaperCandidate, bool, Optional[MergeEvent]]:
    """Match candidate to an existing DB paper and merge, or mark as new.

    Returns (resolved_candidate, is_new, merge_event_or_None). Does not write to
    the papers table here; the pipeline persists the resolved candidate so that
    scoring happens first.
    """
    existing_row = db.find_existing(conn, candidate)
    if existing_row is None:
        candidate.paper_id = identity.stable_paper_id(candidate)
        return candidate, True, None

    existing = db.row_to_candidate(existing_row)
    match = db.matched_on(conn, candidate, existing_row)
    merged = merge_candidates(existing, candidate)
    merged.paper_id = existing_row["paper_id"]

    event = MergeEvent(
        run_id=run_id,
        existing_paper_id=existing_row["paper_id"],
        candidate_id=candidate.paper_id,
        matched_on=match,
        source=source,
        query=query,
        created_at=_now(),
    )
    return merged, False, event
