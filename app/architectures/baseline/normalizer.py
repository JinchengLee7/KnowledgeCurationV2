"""Normalize raw Semantic Scholar records into the shared PaperCandidate shape.

Pure and deterministic: maps fields, never invents data, and preserves the raw
record under ``raw["semantic_scholar"]`` for traceability.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.architectures.baseline.constants import SOURCE
from app.state.schemas import PaperCandidate, PaperIdentifiers


def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def normalize(item: Dict[str, Any], query: Optional[str] = None) -> PaperCandidate:
    """Convert one Semantic Scholar ``paper`` object to a PaperCandidate."""
    title = _clean_str(item.get("title")) or ""

    authors = [
        a.get("name", "").strip()
        for a in (item.get("authors") or [])
        if isinstance(a, dict) and a.get("name")
    ]

    ext = item.get("externalIds") or {}
    oa = item.get("openAccessPdf") or {}
    s2_id = _clean_str(item.get("paperId"))
    corpus_id = item.get("corpusId")

    identifiers = PaperIdentifiers(
        doi=_clean_str(ext.get("DOI")),
        arxiv_id=_clean_str(ext.get("ArXiv")),
        semantic_scholar_id=s2_id,
        corpus_id=_clean_str(corpus_id) if corpus_id is not None else None,
        pmid=_clean_str(ext.get("PubMed")),
    )

    url = _clean_str(item.get("url")) or (
        f"https://www.semanticscholar.org/paper/{s2_id}" if s2_id else None
    )

    return PaperCandidate(
        title=title,
        authors=authors,
        year=item.get("year"),
        abstract=_clean_str(item.get("abstract")),
        url=url,
        pdf_url=_clean_str(oa.get("url")),
        identifiers=identifiers,
        sources=[SOURCE],
        raw={SOURCE: item},
        citation_count=item.get("citationCount"),
        reference_count=item.get("referenceCount"),
        influential_citation_count=item.get("influentialCitationCount"),
        venue=_clean_str(item.get("venue")),
        publication_date=_clean_str(item.get("publicationDate")),
        fields_of_study=list(item.get("fieldsOfStudy") or []),
        publication_types=list(item.get("publicationTypes") or []),
    )
