"""Target-paper detection.

Given optional ``target_papers`` in the config, determine whether each was found
in the local DB (and accepted). Detection order:

    DOI -> Semantic Scholar id -> arXiv id -> exact normalized title

Fuzzy title matching is intentionally deferred; the deterministic path above is
sufficient for accuracy evaluation in v1.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from app.architectures.baseline import identity
from app.architectures.baseline.models import TargetCheckResult


def _find(conn: sqlite3.Connection, column: str, value: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        f"SELECT * FROM papers WHERE {column} = ?", (value,)
    ).fetchone()


def check_targets(conn: sqlite3.Connection,
                  targets: List[Dict[str, Any]]) -> List[TargetCheckResult]:
    """Resolve each configured target against the papers table."""
    results: List[TargetCheckResult] = []
    for t in targets:
        title = t.get("title")
        must_find = bool(t.get("must_find", False))
        row = None
        found_by = None

        doi = identity.normalize_doi(t.get("doi"))
        arxiv = identity.normalize_arxiv(t.get("arxiv_id"))
        s2 = t.get("semantic_scholar_id")

        if doi and (row := _find(conn, "doi_norm", doi)):
            found_by = "doi_lookup"
        elif s2 and (row := _find(conn, "semantic_scholar_id", s2)):
            found_by = "s2_lookup"
        elif arxiv and (row := _find(conn, "arxiv_id_norm", arxiv)):
            found_by = "arxiv_lookup"
        elif title:
            tn = identity.normalize_title(title)
            if row := _find(conn, "title_norm", tn):
                found_by = "title_match"

        if row is None:
            results.append(TargetCheckResult(
                target_title=title, must_find=must_find, found=False))
        else:
            # Presence in the papers table means it was accepted.
            results.append(TargetCheckResult(
                target_title=title, must_find=must_find, found=True,
                found_by=found_by, paper_id=row["paper_id"], was_accepted=True))
    return results


def target_metrics(results: List[TargetCheckResult]) -> Dict[str, int]:
    total = len(results)
    found = sum(1 for r in results if r.found)
    accepted = sum(1 for r in results if r.was_accepted)
    return {
        "target_total": total,
        "target_found": found,
        "target_accepted": accepted,
        "target_missed": total - found,
        "target_rejected": found - accepted,
    }
