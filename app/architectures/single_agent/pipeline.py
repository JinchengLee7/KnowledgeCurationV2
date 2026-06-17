"""Single-agent pipeline placeholder.

This version focuses on the deterministic baseline. The single-agent LLM
architecture is not implemented yet, but it honors the shared ``run`` contract
and returns a structured :class:`ManagerRunResult` so the CLI and comparison
tooling keep working.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.state.schemas import ManagerRunResult

_ARCH = "single-agent"


def run(config_path: str = "data/survey_config.json", dry_run: bool = False) -> ManagerRunResult:
    now = datetime.now(timezone.utc).isoformat()
    return ManagerRunResult(
        architecture=_ARCH,
        queries_generated=0,
        sources_queried=[],
        candidates_found=0,
        candidates_after_dedupe=0,
        papers_accepted=0,
        candidates_rejected=0,
        dry_run=dry_run,
        started_at=now,
        finished_at=now,
        status="failure",
        run_id="",
        errors=[f"{_ARCH} architecture is not implemented in this version"],
    )
