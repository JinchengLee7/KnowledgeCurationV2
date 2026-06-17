"""Shared persistence: NDJSON canonical files and static-site JSON.

All writes are atomic (write to ``*.tmp`` then ``os.replace``) and respect a
``dry_run`` flag. This module is architecture-neutral and reused by the
baseline publisher; it owns the canonical public file contract:

    data/papers.ndjson
    data/rejects.ndjson
    data/run_history.ndjson
    data/changelog.md
    data/system_status.json
    site/data/*.json
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.state.schemas import (
    ManagerRunResult,
    PaperCandidate,
    PaperIdentifiers,
)

DATA_DIR = Path("data")
SITE_DATA_DIR = Path("site") / "data"

PAPERS_NDJSON = DATA_DIR / "papers.ndjson"
REJECTS_NDJSON = DATA_DIR / "rejects.ndjson"
RUN_HISTORY_NDJSON = DATA_DIR / "run_history.ndjson"
CHANGELOG_MD = DATA_DIR / "changelog.md"
SYSTEM_STATUS_JSON = DATA_DIR / "system_status.json"


# --------------------------------------------------------------------------- #
# Identity / serialization helpers
# --------------------------------------------------------------------------- #
def make_paper_id(p: PaperCandidate) -> str:
    """Return a stable id for a candidate from its strongest identifier.

    Priority: DOI > arXiv > OpenAlex > Semantic Scholar > title:year. The
    baseline computes richer ids via app.architectures.baseline.identity; this
    fallback keeps shared persistence self-sufficient.
    """
    ids = p.identifiers
    basis = (
        (ids.doi and f"doi:{ids.doi.lower()}")
        or (ids.arxiv_id and f"arxiv:{ids.arxiv_id.lower()}")
        or (ids.openalex_id and f"openalex:{ids.openalex_id.lower()}")
        or (ids.semantic_scholar_id and f"s2:{ids.semantic_scholar_id.lower()}")
        or f"title:{(p.title or '').strip().lower()}:{p.year or ''}"
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return "p" + digest[:15]


def candidate_to_dict(c: PaperCandidate) -> Dict[str, Any]:
    """Serialize a candidate to a JSON-safe dict (stable key order)."""
    return {
        "paper_id": c.paper_id,
        "title": c.title,
        "authors": list(c.authors),
        "year": c.year,
        "abstract": c.abstract,
        "url": c.url,
        "pdf_url": c.pdf_url,
        "identifiers": asdict(c.identifiers),
        "sources": list(c.sources),
        "score": c.score,
        "score_components": dict(c.score_components),
        "score_method": c.score_method,
        "rejection_reason": c.rejection_reason,
        "citation_count": c.citation_count,
        "reference_count": c.reference_count,
        "influential_citation_count": c.influential_citation_count,
        "venue": c.venue,
        "publication_date": c.publication_date,
        "fields_of_study": list(c.fields_of_study),
        "publication_types": list(c.publication_types),
        "provenance": dict(c.provenance),
        "embedding_score": c.embedding_score,
    }


def dict_to_candidate(d: Dict[str, Any]) -> PaperCandidate:
    """Inverse of :func:`candidate_to_dict` (tolerant of missing keys)."""
    ids = d.get("identifiers") or {}
    return PaperCandidate(
        title=d.get("title", ""),
        authors=list(d.get("authors") or []),
        year=d.get("year"),
        abstract=d.get("abstract"),
        url=d.get("url"),
        pdf_url=d.get("pdf_url"),
        identifiers=PaperIdentifiers(
            doi=ids.get("doi"),
            arxiv_id=ids.get("arxiv_id"),
            openalex_id=ids.get("openalex_id"),
            semantic_scholar_id=ids.get("semantic_scholar_id"),
            corpus_id=ids.get("corpus_id"),
            pmid=ids.get("pmid"),
        ),
        sources=list(d.get("sources") or []),
        score=d.get("score", 0.0) or 0.0,
        score_components=dict(d.get("score_components") or {}),
        score_method=d.get("score_method"),
        rejection_reason=d.get("rejection_reason"),
        paper_id=d.get("paper_id"),
        citation_count=d.get("citation_count"),
        reference_count=d.get("reference_count"),
        influential_citation_count=d.get("influential_citation_count"),
        venue=d.get("venue"),
        publication_date=d.get("publication_date"),
        fields_of_study=list(d.get("fields_of_study") or []),
        publication_types=list(d.get("publication_types") or []),
        provenance=dict(d.get("provenance") or {}),
        embedding_score=d.get("embedding_score"),
    )


# --------------------------------------------------------------------------- #
# Low-level atomic IO
# --------------------------------------------------------------------------- #
def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_text_atomic(path: Path, text: str) -> None:
    _ensure_parent(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_json(path: Path, data: Any) -> None:
    """Atomically write ``data`` as pretty JSON."""
    _write_text_atomic(path, json.dumps(data, indent=2, ensure_ascii=False))


def read_ndjson(path: Path) -> List[Dict[str, Any]]:
    """Read an NDJSON file, skipping blank/malformed lines."""
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def write_ndjson_atomic(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Atomically write a list of dicts as NDJSON."""
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    _write_text_atomic(path, text)


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Canonical file operations
# --------------------------------------------------------------------------- #
def load_papers() -> List[PaperCandidate]:
    return [dict_to_candidate(d) for d in read_ndjson(PAPERS_NDJSON)]


def load_rejects() -> List[PaperCandidate]:
    return [dict_to_candidate(d) for d in read_ndjson(REJECTS_NDJSON)]


def save_papers(papers: List[PaperCandidate], dry_run: bool = False) -> None:
    if dry_run:
        return
    rows = [candidate_to_dict(p) for p in papers]
    write_ndjson_atomic(PAPERS_NDJSON, rows)


def save_rejects(rejects: List[PaperCandidate], dry_run: bool = False) -> None:
    if dry_run:
        return
    rows = [candidate_to_dict(r) for r in rejects]
    write_ndjson_atomic(REJECTS_NDJSON, rows)


def persist_run_history(result: ManagerRunResult, dry_run: bool = False) -> None:
    if dry_run:
        return
    _ensure_parent(RUN_HISTORY_NDJSON)
    record = asdict(result)
    rows = read_ndjson(RUN_HISTORY_NDJSON)
    rows.append(record)
    write_ndjson_atomic(RUN_HISTORY_NDJSON, rows)


def append_changelog(text: str, dry_run: bool = False) -> None:
    if dry_run:
        return
    _ensure_parent(CHANGELOG_MD)
    existing = CHANGELOG_MD.read_text(encoding="utf-8") if CHANGELOG_MD.exists() else ""
    _write_text_atomic(CHANGELOG_MD, existing + text)


def write_system_status(status: Dict[str, Any], dry_run: bool = False) -> None:
    """Write the machine-readable system status (always to data/)."""
    if dry_run:
        return
    write_json(SYSTEM_STATUS_JSON, status)


def publish_site_data(
    papers: List[PaperCandidate],
    rejects: List[PaperCandidate],
    run_history: List[Dict[str, Any]],
    system_status: Dict[str, Any],
    survey_config_raw: Dict[str, Any],
    dry_run: bool = False,
) -> None:
    """Export canonical state to ``site/data/*.json`` for the static site."""
    if dry_run:
        return
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_json(SITE_DATA_DIR / "papers.json", [candidate_to_dict(p) for p in papers])
    write_json(SITE_DATA_DIR / "rejects.json", [candidate_to_dict(r) for r in rejects])
    write_json(SITE_DATA_DIR / "run_history.json", run_history)
    write_json(SITE_DATA_DIR / "system_status.json", system_status)
    write_json(SITE_DATA_DIR / "survey_config.json", survey_config_raw)
    if CHANGELOG_MD.exists():
        _write_text_atomic(
            SITE_DATA_DIR / "changelog.md", CHANGELOG_MD.read_text(encoding="utf-8")
        )
