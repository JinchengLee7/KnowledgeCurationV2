"""SQLite local database: the baseline's source of truth.

Owns schema creation, transactions, upserts, and the API response cache. No ORM
- thin ``sqlite3`` helpers only. All write helpers assume the caller manages the
transaction via :func:`transaction` or commits explicitly.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from app.architectures.baseline import identity
from app.architectures.baseline.models import MergeEvent, RejectRecord, SourceHit
from app.state.schemas import PaperCandidate, PaperIdentifiers

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
  paper_id TEXT PRIMARY KEY,
  doi_norm TEXT,
  arxiv_id_norm TEXT,
  semantic_scholar_id TEXT,
  corpus_id TEXT,
  title TEXT NOT NULL,
  title_norm TEXT,
  title_fingerprint TEXT,
  abstract TEXT,
  year INTEGER,
  publication_date TEXT,
  venue TEXT,
  primary_url TEXT,
  pdf_url TEXT,
  citation_count INTEGER,
  reference_count INTEGER,
  influential_citation_count INTEGER,
  fields_of_study_json TEXT,
  publication_types_json TEXT,
  authors_json TEXT,
  external_ids_json TEXT,
  score REAL,
  score_components_json TEXT,
  score_method TEXT,
  provenance_json TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_hits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  architecture TEXT NOT NULL,
  source TEXT NOT NULL,
  query TEXT,
  rank INTEGER,
  retrieved_at TEXT NOT NULL,
  raw_json_hash TEXT
);

CREATE TABLE IF NOT EXISTS rejects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id TEXT,
  run_id TEXT NOT NULL,
  architecture TEXT NOT NULL,
  source TEXT,
  query TEXT,
  title TEXT,
  year INTEGER,
  reason TEXT NOT NULL,
  score REAL,
  evidence_json TEXT,
  raw_json_hash TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS merge_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  existing_paper_id TEXT NOT NULL,
  candidate_id TEXT,
  matched_on TEXT NOT NULL,
  source TEXT,
  query TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  architecture TEXT NOT NULL,
  topic TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  success TEXT,
  generated_queries_json TEXT,
  metrics_json TEXT,
  errors_json TEXT,
  summary TEXT
);

CREATE TABLE IF NOT EXISTS api_cache (
  cache_key TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  request_json TEXT NOT NULL,
  response_json TEXT,
  status_code INTEGER,
  created_at TEXT NOT NULL,
  expires_at TEXT
);

CREATE TABLE IF NOT EXISTS query_state (
  query_norm TEXT PRIMARY KEY,
  query_original TEXT NOT NULL,
  total_runs INTEGER DEFAULT 0,
  total_candidates INTEGER DEFAULT 0,
  total_accepted INTEGER DEFAULT 0,
  total_duplicates INTEGER DEFAULT 0,
  total_errors INTEGER DEFAULT 0,
  consecutive_zero_accept INTEGER DEFAULT 0,
  last_run_at TEXT
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_papers_title_fingerprint ON papers(title_fingerprint);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi_norm);
CREATE INDEX IF NOT EXISTS idx_papers_arxiv ON papers(arxiv_id_norm);
CREATE INDEX IF NOT EXISTS idx_papers_s2 ON papers(semantic_scholar_id);
CREATE INDEX IF NOT EXISTS idx_source_hits_run ON source_hits(run_id);
CREATE INDEX IF NOT EXISTS idx_source_hits_paper ON source_hits(paper_id);
CREATE INDEX IF NOT EXISTS idx_rejects_run ON rejects(run_id);
CREATE INDEX IF NOT EXISTS idx_merge_events_run ON merge_events(run_id);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a connection with sane pragmas and dict-like rows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.executescript(INDEXES)
    conn.commit()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block in a transaction, committing on success."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --------------------------------------------------------------------------- #
# Papers: identity lookup + row<->candidate mapping
# --------------------------------------------------------------------------- #
def find_existing(conn: sqlite3.Connection, candidate: PaperCandidate) -> Optional[sqlite3.Row]:
    """Find an existing paper matching the candidate's identity (priority order)."""
    ids = identity.normalized_identifiers(candidate.identifiers)
    checks = [
        ("doi_norm", ids.doi),
        ("arxiv_id_norm", ids.arxiv_id),
        ("semantic_scholar_id", ids.semantic_scholar_id),
        ("corpus_id", ids.corpus_id),
    ]
    for column, value in checks:
        if value:
            row = conn.execute(
                f"SELECT * FROM papers WHERE {column} = ?", (value,)
            ).fetchone()
            if row:
                return row

    fp = identity.title_fingerprint(
        candidate.title, candidate.year, identity.first_author(candidate)
    )
    row = conn.execute(
        "SELECT * FROM papers WHERE title_fingerprint = ?", (fp,)
    ).fetchone()
    return row


def matched_on(conn: sqlite3.Connection, candidate: PaperCandidate, existing: sqlite3.Row) -> str:
    ids = identity.normalized_identifiers(candidate.identifiers)
    if ids.doi and existing["doi_norm"] == ids.doi:
        return "doi"
    if ids.arxiv_id and existing["arxiv_id_norm"] == ids.arxiv_id:
        return "arxiv"
    if ids.semantic_scholar_id and existing["semantic_scholar_id"] == ids.semantic_scholar_id:
        return "s2"
    if ids.corpus_id and existing["corpus_id"] == ids.corpus_id:
        return "corpus"
    return "fingerprint"


def _candidate_row_values(candidate: PaperCandidate, now: str) -> Dict[str, Any]:
    ids = identity.normalized_identifiers(candidate.identifiers)
    return {
        "paper_id": candidate.paper_id,
        "doi_norm": ids.doi,
        "arxiv_id_norm": ids.arxiv_id,
        "semantic_scholar_id": ids.semantic_scholar_id,
        "corpus_id": ids.corpus_id,
        "title": candidate.title,
        "title_norm": identity.normalize_title(candidate.title),
        "title_fingerprint": identity.title_fingerprint(
            candidate.title, candidate.year, identity.first_author(candidate)
        ),
        "abstract": candidate.abstract,
        "year": candidate.year,
        "publication_date": candidate.publication_date,
        "venue": candidate.venue,
        "primary_url": candidate.url,
        "pdf_url": candidate.pdf_url,
        "citation_count": candidate.citation_count,
        "reference_count": candidate.reference_count,
        "influential_citation_count": candidate.influential_citation_count,
        "fields_of_study_json": json.dumps(candidate.fields_of_study or []),
        "publication_types_json": json.dumps(candidate.publication_types or []),
        "authors_json": json.dumps(candidate.authors or []),
        "external_ids_json": json.dumps(
            {
                "doi": ids.doi,
                "arxiv_id": ids.arxiv_id,
                "openalex_id": ids.openalex_id,
                "semantic_scholar_id": ids.semantic_scholar_id,
                "corpus_id": ids.corpus_id,
                "pmid": ids.pmid,
            }
        ),
        "score": candidate.score,
        "score_components_json": json.dumps(candidate.score_components or {}),
        "score_method": candidate.score_method,
        "provenance_json": json.dumps(candidate.provenance or {}),
        "updated_at": now,
    }


def insert_paper(conn: sqlite3.Connection, candidate: PaperCandidate, now: str) -> None:
    vals = _candidate_row_values(candidate, now)
    vals["first_seen_at"] = now
    vals["last_seen_at"] = now
    cols = ", ".join(vals.keys())
    placeholders = ", ".join(f":{k}" for k in vals)
    conn.execute(f"INSERT INTO papers ({cols}) VALUES ({placeholders})", vals)


def update_paper(conn: sqlite3.Connection, candidate: PaperCandidate, now: str) -> None:
    vals = _candidate_row_values(candidate, now)
    vals["last_seen_at"] = now
    assignments = ", ".join(f"{k} = :{k}" for k in vals if k != "paper_id")
    conn.execute(f"UPDATE papers SET {assignments} WHERE paper_id = :paper_id", vals)


def row_to_candidate(row: sqlite3.Row) -> PaperCandidate:
    ext = json.loads(row["external_ids_json"] or "{}")
    return PaperCandidate(
        title=row["title"],
        authors=json.loads(row["authors_json"] or "[]"),
        year=row["year"],
        abstract=row["abstract"],
        url=row["primary_url"],
        pdf_url=row["pdf_url"],
        identifiers=PaperIdentifiers(
            doi=ext.get("doi"),
            arxiv_id=ext.get("arxiv_id"),
            openalex_id=ext.get("openalex_id"),
            semantic_scholar_id=ext.get("semantic_scholar_id"),
            corpus_id=ext.get("corpus_id"),
            pmid=ext.get("pmid"),
        ),
        sources=["semantic_scholar"],
        score=row["score"] or 0.0,
        score_components=json.loads(row["score_components_json"] or "{}"),
        score_method=row["score_method"],
        paper_id=row["paper_id"],
        citation_count=row["citation_count"],
        reference_count=row["reference_count"],
        influential_citation_count=row["influential_citation_count"],
        venue=row["venue"],
        publication_date=row["publication_date"],
        fields_of_study=json.loads(row["fields_of_study_json"] or "[]"),
        publication_types=json.loads(row["publication_types_json"] or "[]"),
        provenance=json.loads(row["provenance_json"] or "{}"),
    )


def load_all_papers(conn: sqlite3.Connection) -> List[PaperCandidate]:
    """Return all papers ordered deterministically (score desc, then id)."""
    rows = conn.execute(
        "SELECT * FROM papers ORDER BY score DESC, paper_id ASC"
    ).fetchall()
    return [row_to_candidate(r) for r in rows]


# --------------------------------------------------------------------------- #
# Event logs
# --------------------------------------------------------------------------- #
def record_source_hit(conn: sqlite3.Connection, hit: SourceHit) -> None:
    conn.execute(
        """INSERT INTO source_hits
        (paper_id, run_id, architecture, source, query, rank, retrieved_at, raw_json_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (hit.paper_id, hit.run_id, hit.architecture, hit.source, hit.query,
         hit.rank, hit.retrieved_at, hit.raw_json_hash),
    )


def record_reject(conn: sqlite3.Connection, rec: RejectRecord) -> None:
    conn.execute(
        """INSERT INTO rejects
        (candidate_id, run_id, architecture, source, query, title, year, reason,
         score, evidence_json, raw_json_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rec.candidate_id, rec.run_id, rec.architecture, rec.source, rec.query,
         rec.title, rec.year, rec.reason, rec.score, json.dumps(rec.evidence or {}),
         rec.raw_ref, rec.created_at),
    )


def record_merge_event(conn: sqlite3.Connection, ev: MergeEvent) -> None:
    conn.execute(
        """INSERT INTO merge_events
        (run_id, existing_paper_id, candidate_id, matched_on, source, query, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ev.run_id, ev.existing_paper_id, ev.candidate_id, ev.matched_on,
         ev.source, ev.query, ev.created_at),
    )


def load_rejects(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM rejects ORDER BY created_at ASC, id ASC"
    ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #
def start_run(conn: sqlite3.Connection, run_id: str, architecture: str,
              topic: str, started_at: str, generated_queries: List[str]) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO runs
        (run_id, architecture, topic, started_at, generated_queries_json)
        VALUES (?, ?, ?, ?, ?)""",
        (run_id, architecture, topic, started_at, json.dumps(generated_queries)),
    )
    conn.commit()


def finish_run(conn: sqlite3.Connection, run_id: str, finished_at: str,
               success: str, metrics: Dict[str, Any], errors: List[str],
               summary: str) -> None:
    conn.execute(
        """UPDATE runs SET finished_at = ?, success = ?, metrics_json = ?,
        errors_json = ?, summary = ? WHERE run_id = ?""",
        (finished_at, success, json.dumps(metrics), json.dumps(errors), summary, run_id),
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# Query state (loop control)
# --------------------------------------------------------------------------- #
def update_query_state(conn: sqlite3.Connection, query_norm: str, query_original: str,
                       candidates: int, accepted: int, duplicates: int,
                       errors: int, now: str) -> None:
    row = conn.execute(
        "SELECT * FROM query_state WHERE query_norm = ?", (query_norm,)
    ).fetchone()
    consecutive_zero = 0 if accepted > 0 else 1
    if row:
        consecutive_zero = 0 if accepted > 0 else (row["consecutive_zero_accept"] + 1)
        conn.execute(
            """UPDATE query_state SET
            total_runs = total_runs + 1,
            total_candidates = total_candidates + ?,
            total_accepted = total_accepted + ?,
            total_duplicates = total_duplicates + ?,
            total_errors = total_errors + ?,
            consecutive_zero_accept = ?,
            last_run_at = ?
            WHERE query_norm = ?""",
            (candidates, accepted, duplicates, errors, consecutive_zero, now, query_norm),
        )
    else:
        conn.execute(
            """INSERT INTO query_state
            (query_norm, query_original, total_runs, total_candidates, total_accepted,
             total_duplicates, total_errors, consecutive_zero_accept, last_run_at)
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)""",
            (query_norm, query_original, candidates, accepted, duplicates, errors,
             consecutive_zero, now),
        )


def get_query_state(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM query_state").fetchall()
    return {r["query_norm"]: dict(r) for r in rows}


# --------------------------------------------------------------------------- #
# API cache
# --------------------------------------------------------------------------- #
def cache_get(conn: sqlite3.Connection, cache_key: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT response_json, status_code FROM api_cache WHERE cache_key = ?",
        (cache_key,),
    ).fetchone()
    if not row or row["response_json"] is None:
        return None
    try:
        return json.loads(row["response_json"])
    except json.JSONDecodeError:
        return None


def cache_put(conn: sqlite3.Connection, cache_key: str, source: str, endpoint: str,
              request: Dict[str, Any], response: Optional[Dict[str, Any]],
              status_code: Optional[int], now: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO api_cache
        (cache_key, source, endpoint, request_json, response_json, status_code, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cache_key, source, endpoint, json.dumps(request),
         json.dumps(response) if response is not None else None,
         status_code, now, None),
    )
    conn.commit()


def run_duplicate_rate(conn: sqlite3.Connection, run_id: str) -> float:
    """Duplicate rate for a run = merges / source_hits (0 if no hits)."""
    hits = conn.execute(
        "SELECT COUNT(*) AS c FROM source_hits WHERE run_id = ?", (run_id,)
    ).fetchone()["c"]
    merges = conn.execute(
        "SELECT COUNT(*) AS c FROM merge_events WHERE run_id = ?", (run_id,)
    ).fetchone()["c"]
    return (merges / hits) if hits else 0.0
