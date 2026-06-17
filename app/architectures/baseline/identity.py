"""Identity normalization and stable paper-id generation.

Deterministic by construction: the same identifiers always yield the same
``paper_id``. Identity priority (highest first):

    1. normalized DOI
    2. normalized arXiv id
    3. Semantic Scholar paperId
    4. corpusId
    5. other external ids (PMID, ...)
    6. fingerprint of normalized title + year + first author
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Optional

from app.state.schemas import PaperCandidate, PaperIdentifiers

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_ARXIV_VERSION = re.compile(r"v\d+$")


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    s = doi.strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s)
    s = s.strip()
    return s or None


def normalize_arxiv(arxiv_id: Optional[str]) -> Optional[str]:
    if not arxiv_id:
        return None
    s = arxiv_id.strip().lower()
    s = re.sub(r"^arxiv:\s*", "", s)
    s = re.sub(r"^https?://arxiv\.org/abs/", "", s)
    s = _ARXIV_VERSION.sub("", s)  # strip version suffix (v1, v2, ...)
    s = s.strip()
    return s or None


def normalize_title(title: Optional[str]) -> str:
    if not title:
        return ""
    s = unicodedata.normalize("NFKC", title).lower()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def normalize_author(author: Optional[str]) -> str:
    if not author:
        return ""
    s = unicodedata.normalize("NFKC", author).lower()
    s = _WS.sub(" ", s).strip()
    return s


def first_author(candidate: PaperCandidate) -> str:
    return normalize_author(candidate.authors[0]) if candidate.authors else ""


def title_fingerprint(title: Optional[str], year: Optional[int], first_auth: str) -> str:
    """SHA256 fingerprint over normalized (title, year, first author)."""
    basis = f"{normalize_title(title)}|{year or ''}|{first_auth}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def normalized_identifiers(ids: PaperIdentifiers) -> PaperIdentifiers:
    """Return a copy of ``ids`` with DOI/arXiv normalized."""
    return PaperIdentifiers(
        doi=normalize_doi(ids.doi),
        arxiv_id=normalize_arxiv(ids.arxiv_id),
        openalex_id=(ids.openalex_id or None),
        semantic_scholar_id=(ids.semantic_scholar_id or None),
        corpus_id=(str(ids.corpus_id) if ids.corpus_id else None),
        pmid=(str(ids.pmid) if ids.pmid else None),
    )


def stable_paper_id(candidate: PaperCandidate) -> str:
    """Compute the deterministic ``paper_id`` for a candidate.

    Uses the highest-priority identifier present; falls back to a title/year/
    author fingerprint so every candidate gets a stable id.
    """
    ids = normalized_identifiers(candidate.identifiers)
    if ids.doi:
        return f"doi:{ids.doi}"
    if ids.arxiv_id:
        return f"arxiv:{ids.arxiv_id}"
    if ids.semantic_scholar_id:
        return f"s2:{ids.semantic_scholar_id}"
    if ids.corpus_id:
        return f"corpus:{ids.corpus_id}"
    if ids.pmid:
        return f"pmid:{ids.pmid}"
    fp = title_fingerprint(candidate.title, candidate.year, first_author(candidate))
    return f"fp:{fp}"
