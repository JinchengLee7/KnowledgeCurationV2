"""Publishing: export canonical SQLite state to NDJSON + static-site JSON.

Reuses the shared atomic writers in :mod:`app.state.store`. Adds a provenance
block to each paper (which architectures/sources/queries observed it) so the
site can attribute papers to an architecture.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.architectures.baseline import constants, db
from app.state import store
from app.state.schemas import ManagerRunResult, PaperCandidate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_provenance(conn: sqlite3.Connection, paper_id: str) -> Dict[str, Any]:
    """Assemble a provenance block from this paper's source_hits."""
    rows = conn.execute(
        "SELECT architecture, source, query, run_id, retrieved_at, rank "
        "FROM source_hits WHERE paper_id = ? ORDER BY id ASC",
        (paper_id,),
    ).fetchall()
    architectures: List[str] = []
    sources: List[str] = []
    hits: List[Dict[str, Any]] = []
    for r in rows:
        if r["architecture"] not in architectures:
            architectures.append(r["architecture"])
        if r["source"] not in sources:
            sources.append(r["source"])
        hits.append({
            "architecture": r["architecture"],
            "source": r["source"],
            "query": r["query"],
            "run_id": r["run_id"],
            "retrieved_at": r["retrieved_at"],
            "rank": r["rank"],
        })
    return {
        "architectures_seen": architectures or [constants.ARCHITECTURE],
        "sources_seen": sources or [constants.SOURCE],
        "first_seen_by": architectures[0] if architectures else constants.ARCHITECTURE,
        "last_seen_by": architectures[-1] if architectures else constants.ARCHITECTURE,
        "source_hits": hits,
    }


def _papers_with_provenance(conn: sqlite3.Connection) -> List[PaperCandidate]:
    papers = db.load_all_papers(conn)
    for p in papers:
        p.provenance = build_provenance(conn, p.paper_id)
    return papers


def _rejects_as_candidates(conn: sqlite3.Connection) -> List[PaperCandidate]:
    out: List[PaperCandidate] = []
    for r in db.load_rejects(conn):
        out.append(PaperCandidate(
            title=r.get("title") or "",
            year=r.get("year"),
            score=r.get("score") or 0.0,
            rejection_reason=r.get("reason"),
            paper_id=r.get("candidate_id"),
            sources=[r.get("source") or constants.SOURCE],
        ))
    return out


def _changelog_entry(result: ManagerRunResult, papers: List[PaperCandidate]) -> str:
    lines = [
        f"\n## {result.finished_at} — {result.architecture} ({result.status})\n",
        f"- run_id: `{result.run_id}`\n",
        f"- queries: {result.queries_generated}, candidates: {result.candidates_found}, "
        f"after dedupe: {result.candidates_after_dedupe}\n",
        f"- accepted: {result.papers_accepted}, rejected: {result.candidates_rejected}, "
        f"errors: {len(result.errors)}\n",
    ]
    top = sorted(papers, key=lambda p: (-p.score, p.paper_id or ""))[:20]
    if top:
        lines.append("- top accepted:\n")
        for p in top:
            lines.append(f"  - ({p.score:.3f}) {p.title}\n")
    return "".join(lines)


def build_system_status(result: ManagerRunResult, total_papers: int) -> Dict[str, Any]:
    return {
        "architecture": result.architecture,
        "status": constants.STATUS_FINISHED if result.status != "failure"
        else constants.STATUS_FAILED,
        "run_id": result.run_id,
        "updated_at": _now(),
        "message": result.status,
        "last_run": result.finished_at,
        "papers_accepted": result.papers_accepted,
        "candidates_rejected": result.candidates_rejected,
        "total_papers": total_papers,
    }


def publish(
    conn: sqlite3.Connection,
    result: ManagerRunResult,
    survey_config_raw: Dict[str, Any],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Export everything. Returns the system_status dict that was written."""
    papers = _papers_with_provenance(conn)
    rejects = _rejects_as_candidates(conn)
    system_status = build_system_status(result, total_papers=len(papers))

    if not dry_run:
        store.save_papers(papers)
        store.save_rejects(rejects)
        store.persist_run_history(result)
        store.append_changelog(_changelog_entry(result, papers))
        store.write_system_status(system_status)
        run_history = store.read_ndjson(store.RUN_HISTORY_NDJSON)
        store.publish_site_data(
            papers, rejects, run_history, system_status, survey_config_raw
        )

    return system_status
