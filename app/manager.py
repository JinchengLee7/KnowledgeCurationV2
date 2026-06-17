"""Architecture dispatch layer.

Routes a requested architecture to its pipeline ``run`` function. Every
pipeline returns a :class:`ManagerRunResult` so results are comparable.
"""

from __future__ import annotations

import logging

from app.state.schemas import ManagerRunResult

logger = logging.getLogger(__name__)

ARCHITECTURES = ["baseline", "single-agent", "multi-agent"]


def run_architecture(
    architecture: str,
    config_path: str,
    dry_run: bool,
) -> ManagerRunResult:
    """Dispatch to the requested architecture's pipeline."""
    if architecture == "baseline":
        from app.architectures.baseline.pipeline import run
        return run(config_path=config_path, dry_run=dry_run)

    if architecture == "single-agent":
        from app.architectures.single_agent.pipeline import run
        return run(config_path=config_path, dry_run=dry_run)

    if architecture == "multi-agent":
        from app.architectures.multi_agent.pipeline import run
        return run(config_path=config_path, dry_run=dry_run)

    raise ValueError(
        f"Unknown architecture {architecture!r}. "
        f"Choose from: {', '.join(ARCHITECTURES)}"
    )
