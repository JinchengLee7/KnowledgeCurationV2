"""Run metrics and architecture-comparison summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.architectures.baseline import constants
from app.architectures.baseline.models import RunMetrics
from app.state import store


def duplicate_rate(metrics: RunMetrics) -> float:
    total = metrics.raw_candidate_count
    return (metrics.duplicate_count + metrics.merge_count) / total if total else 0.0


def error_rate(metrics: RunMetrics) -> float:
    total = max(1, metrics.api_call_count)
    return metrics.error_count / total


def cache_hit_rate(metrics: RunMetrics) -> float:
    total = metrics.cache_hit_count + metrics.cache_miss_count
    return metrics.cache_hit_count / total if total else 0.0


def summarize(metrics: RunMetrics) -> Dict[str, Any]:
    """A flat, comparison-friendly metrics dict."""
    d = metrics.as_dict()
    d["duplicate_rate"] = round(duplicate_rate(metrics), 4)
    d["error_rate"] = round(error_rate(metrics), 4)
    d["cache_hit_rate"] = round(cache_hit_rate(metrics), 4)
    return d


def write_comparison_record(run_id: str, architecture: str,
                            metrics: Dict[str, Any], dry_run: bool = False) -> None:
    """Append a per-run comparison record under data/comparison/runs/."""
    if dry_run:
        return
    runs_dir = constants.COMPARISON_DIR / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    store.write_json(runs_dir / f"{run_id}.json", {
        "run_id": run_id,
        "architecture": architecture,
        "metrics": metrics,
    })
