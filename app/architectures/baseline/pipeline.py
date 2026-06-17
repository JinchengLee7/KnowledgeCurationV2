"""Baseline pipeline orchestrator.

Runs the full deterministic workflow and returns a flat
:class:`ManagerRunResult`. Rich detail is written to per-run artifacts under
``data/baseline/run_artifacts/{run_id}/``.

Workflow:
    load config -> build queries -> (loop-control adjust) -> query Semantic
    Scholar (cached) -> normalize -> validate -> intra-run dedupe -> resolve
    identity vs DB -> score -> filter -> persist papers/rejects/merges/source
    hits -> target check -> update query state -> finish run -> publish ->
    write artifacts -> return result.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.architectures.baseline import (
    constants,
    db,
    deduper,
    filters,
    loop_control,
    metrics as metrics_mod,
    normalizer,
    publisher,
    scorer,
    target_check,
)
from app.architectures.baseline.errors import BaselineError, ConfigError
from app.architectures.baseline.models import RunMetrics, SourceHit
from app.architectures.baseline.query_builder import build_queries
from app.architectures.baseline.semantic_scholar_client import SemanticScholarClient
from app.config import load_survey_config
from app.state import store
from app.state.schemas import ManagerRunResult, PaperCandidate, SurveyConfig

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_run_id() -> str:
    return "baseline-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def _status(status: str, run_id: str, message: str, dry_run: bool,
            progress: Optional[Dict[str, Any]] = None) -> None:
    store.write_system_status(
        {
            "architecture": constants.ARCHITECTURE,
            "status": status,
            "run_id": run_id,
            "updated_at": _now(),
            "message": message,
            "progress": progress or {},
        },
        dry_run=dry_run,
    )


def run(config_path: str = "data/survey_config.json", dry_run: bool = False) -> ManagerRunResult:
    started_at = _now()
    started_perf = time.perf_counter()
    run_id = _make_run_id()
    errors: List[str] = []
    logger.info("Baseline run %s started (dry_run=%s)", run_id, dry_run)

    # ---- Config -------------------------------------------------------- #
    _status(constants.STATUS_LOADING_CONFIG, run_id, "Loading survey config", dry_run)
    try:
        config, config_raw = load_survey_config(config_path)
    except ConfigError as exc:
        logger.error("Config error: %s", exc)
        return _failure_result(run_id, dry_run, started_at, [str(exc)])

    # ---- Queries ------------------------------------------------------- #
    _status(constants.STATUS_BUILDING_QUERIES, run_id, "Building queries", dry_run)
    queries = build_queries(config)
    if not queries:
        return _failure_result(run_id, dry_run, started_at,
                               ["No queries generated from survey config"])
    logger.info("Generated %d queries", len(queries))

    # ---- Database ------------------------------------------------------ #
    sqlite_target = ":memory:" if dry_run else str(constants.sqlite_path())
    conn = db.connect(sqlite_target)
    db.init_schema(conn)

    adjustments = loop_control.plan_adjustments(conn)
    if adjustments.deprioritized_queries:
        depri = set(adjustments.deprioritized_queries)
        queries = [q for q in queries if loop_control.query_norm(q.query) not in depri] or queries
    enable_cache = bool(config.baseline.get("enable_raw_cache", True))

    db.start_run(conn, run_id, constants.ARCHITECTURE, config.topic_overview,
                 started_at, [q.query for q in queries])

    client = SemanticScholarClient(conn, enable_cache=enable_cache)
    fields = config.semantic_scholar.get("fields") or constants.DEFAULT_FIELDS
    limit = int(config.baseline.get("max_results_per_query", constants.top_k_per_query()))
    max_total = constants.max_candidates_per_run()

    # ---- Crawl + normalize + validate ---------------------------------- #
    _status(constants.STATUS_QUERYING, run_id, "Querying Semantic Scholar", dry_run,
            {"total_queries": len(queries)})
    collected: List[Tuple[PaperCandidate, str, int]] = []  # (candidate, query, rank)
    per_query: Dict[str, Dict[str, int]] = {}

    for qi, gq in enumerate(queries):
        per_query.setdefault(gq.query, {"candidates": 0, "accepted": 0,
                                        "duplicates": 0, "errors": 0})
        try:
            raw_items = client.search(gq.query, fields=fields, limit=limit)
        except BaselineError as exc:
            msg = f"query {gq.query!r}: {exc}"
            errors.append(msg)
            per_query[gq.query]["errors"] += 1
            logger.error(msg)
            continue

        for rank, item in enumerate(raw_items):
            try:
                candidate = normalizer.normalize(item, query=gq.query)
            except Exception as exc:  # normalization should never kill the run
                errors.append(f"normalize error: {exc}")
                continue
            from app.architectures.baseline.validator import validate
            vr = validate(candidate, int(config.baseline.get("min_title_tokens",
                                                             constants.DEFAULT_MIN_TITLE_TOKENS)))
            if not vr.ok:
                # malformed/missing-title -> recorded as a reject later via filters
                candidate.rejection_reason = vr.reason
            collected.append((vr.candidate, gq.query, rank))
            per_query[gq.query]["candidates"] += 1

        if len(collected) >= max_total:
            logger.info("Reached MAX_CANDIDATES_PER_RUN=%d; stopping crawl", max_total)
            errors.append(f"candidate cap reached ({max_total}); remaining queries skipped")
            break

    raw_candidate_count = len(collected)

    # First-seen query/rank per stable id (for source-hit attribution).
    from app.architectures.baseline import identity as _identity
    first_seen: Dict[str, Tuple[str, int]] = {}
    for cand, q, rank in collected:
        pid = _identity.stable_paper_id(cand)
        first_seen.setdefault(pid, (q, rank))

    # ---- Intra-run dedupe --------------------------------------------- #
    _status(constants.STATUS_DEDUPING, run_id, "Deduplicating", dry_run)
    unique, intra_dupes = deduper.dedupe_candidates([c for c, _, _ in collected])
    logger.info("Dedupe: %d unique (%d intra-run duplicates)", len(unique), intra_dupes)

    # ---- Resolve identity vs DB + score ------------------------------- #
    _status(constants.STATUS_SCORING, run_id, "Resolving identity and scoring", dry_run)
    resolved: List[PaperCandidate] = []
    is_new_map: Dict[str, bool] = {}
    merge_events = []
    db_merges = 0
    for cand in unique:
        merged, is_new, event = deduper.resolve_against_db(
            conn, cand, run_id, first_seen.get(cand.paper_id, (None, None))[0],
            constants.SOURCE)
        scorer.apply_score(merged, config, queries)
        resolved.append(merged)
        is_new_map[merged.paper_id] = is_new
        if event is not None:
            merge_events.append(event)
            db_merges += 1

    # ---- Filter -------------------------------------------------------- #
    _status(constants.STATUS_FILTERING, run_id, "Filtering", dry_run)
    accepted, reject_records = filters.apply_filters(resolved, config, run_id)
    accepted_ids = {p.paper_id for p in accepted}
    logger.info("Filtered: %d accepted, %d rejected", len(accepted), len(reject_records))

    # ---- Persist ------------------------------------------------------- #
    _status(constants.STATUS_PERSISTING, run_id, "Persisting to SQLite", dry_run)
    db_started = time.perf_counter()
    new_papers = updated_papers = 0
    try:
        with db.transaction(conn):
            now = _now()
            for p in accepted:
                if is_new_map.get(p.paper_id, True):
                    db.insert_paper(conn, p, now)
                    new_papers += 1
                else:
                    db.update_paper(conn, p, now)
                    updated_papers += 1
                q, rank = first_seen.get(p.paper_id, (None, None))
                raw_hash = store.hash_text(str(p.raw.get(constants.SOURCE, "")))
                db.record_source_hit(conn, SourceHit(
                    paper_id=p.paper_id, run_id=run_id,
                    architecture=constants.ARCHITECTURE, source=constants.SOURCE,
                    query=q, rank=rank, retrieved_at=now, raw_json_hash=raw_hash))
            for ev in merge_events:
                if ev.existing_paper_id in accepted_ids:
                    db.record_merge_event(conn, ev)
            for rr in reject_records:
                db.record_reject(conn, rr)
    except BaselineError as exc:
        errors.append(f"database error: {exc}")
        logger.error("DB persist failed: %s", exc)
    db_write_ms = (time.perf_counter() - db_started) * 1000.0

    # per-query accepted attribution (by first-seen query)
    for p in accepted:
        q, _ = first_seen.get(p.paper_id, (None, None))
        if q in per_query:
            per_query[q]["accepted"] += 1

    # ---- Target check -------------------------------------------------- #
    target_results = target_check.check_targets(conn, config.target_papers)
    tmetrics = target_check.target_metrics(target_results)

    # ---- Loop-control state update ------------------------------------ #
    loop_control.record_query_outcomes(conn, per_query)

    # ---- Metrics + result --------------------------------------------- #
    duplicate_count = intra_dupes + db_merges
    status = _decide_status(errors, len(accepted) + len(reject_records))
    finished_at = _now()

    rmetrics = RunMetrics(
        runtime_seconds=round(time.perf_counter() - started_perf, 3),
        api_call_count=client.stats.api_call_count,
        cache_hit_count=client.stats.cache_hit_count,
        cache_miss_count=client.stats.cache_miss_count,
        raw_candidate_count=raw_candidate_count,
        normalized_candidate_count=len(collected),
        deduplicated_candidate_count=len(unique),
        accepted_count=len(accepted),
        rejected_count=len(reject_records),
        duplicate_count=duplicate_count,
        merge_count=db_merges,
        new_paper_count=new_papers,
        updated_paper_count=updated_papers,
        error_count=len(errors),
        avg_api_latency_ms=round(client.stats.avg_latency_ms, 2),
        db_write_time_ms=round(db_write_ms, 2),
    )

    result = ManagerRunResult(
        architecture=constants.ARCHITECTURE,
        queries_generated=len(queries),
        sources_queried=[constants.SOURCE],
        candidates_found=raw_candidate_count,
        candidates_after_dedupe=len(unique),
        papers_accepted=len(accepted),
        candidates_rejected=len(reject_records),
        dry_run=dry_run,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        run_id=run_id,
        errors=errors,
    )

    metrics_summary = metrics_mod.summarize(rmetrics)
    db.finish_run(conn, run_id, finished_at, status, metrics_summary, errors,
                  _summary_text(result))

    # ---- Publish ------------------------------------------------------- #
    _status(constants.STATUS_PUBLISHING, run_id, "Publishing", dry_run)
    publish_started = time.perf_counter()
    try:
        publisher.publish(conn, result, config_raw, dry_run=dry_run)
    except BaselineError as exc:
        errors.append(f"publish error: {exc}")
        result.status = constants.STATUS_PARTIAL if result.status == "success" else result.status
        logger.error("Publish failed: %s", exc)
    rmetrics.publish_time_ms = round((time.perf_counter() - publish_started) * 1000.0, 2)
    metrics_summary = metrics_mod.summarize(rmetrics)

    # ---- Artifacts + comparison --------------------------------------- #
    _write_artifacts(run_id, queries, resolved, accepted, reject_records,
                     merge_events, target_results, metrics_summary, errors,
                     result, dry_run)
    metrics_mod.write_comparison_record(run_id, constants.ARCHITECTURE,
                                        metrics_summary, dry_run=dry_run)

    conn.close()
    logger.info("Baseline run %s finished: status=%s accepted=%d rejected=%d errors=%d",
                run_id, result.status, len(accepted), len(reject_records), len(errors))
    return result


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _decide_status(errors: List[str], processed: int) -> str:
    if errors and processed == 0:
        return "failure"
    if errors:
        return "partial_success"
    return "success"


def _summary_text(result: ManagerRunResult) -> str:
    return (f"Deterministic baseline run: {result.papers_accepted} accepted, "
            f"{result.candidates_rejected} rejected, {len(result.errors)} errors.")


def _failure_result(run_id: str, dry_run: bool, started_at: str,
                    errors: List[str]) -> ManagerRunResult:
    return ManagerRunResult(
        architecture=constants.ARCHITECTURE,
        queries_generated=0,
        sources_queried=[constants.SOURCE],
        candidates_found=0,
        candidates_after_dedupe=0,
        papers_accepted=0,
        candidates_rejected=0,
        dry_run=dry_run,
        started_at=started_at,
        finished_at=_now(),
        status="failure",
        run_id=run_id,
        errors=errors,
    )


def _write_artifacts(run_id, queries, scored, accepted, rejects, merge_events,
                     target_results, metrics_summary, errors, result, dry_run) -> None:
    if dry_run:
        return
    art_dir = constants.RUN_ARTIFACTS_DIR / run_id
    art_dir.mkdir(parents=True, exist_ok=True)
    store.write_json(art_dir / "generated_queries.json", [asdict(q) for q in queries])
    store.write_json(art_dir / "scored_candidates.json",
                     [store.candidate_to_dict(c) for c in scored])
    store.write_json(art_dir / "accepted_candidates.json",
                     [store.candidate_to_dict(c) for c in accepted])
    store.write_json(art_dir / "rejected_candidates.json", [asdict(r) for r in rejects])
    store.write_json(art_dir / "merge_events.json", [asdict(e) for e in merge_events])
    store.write_json(art_dir / "target_check.json", [asdict(t) for t in target_results])
    store.write_json(art_dir / "metrics.json", metrics_summary)
    store.write_json(art_dir / "errors.json", errors)
    store.write_json(art_dir / "final_report.json", asdict(result))
