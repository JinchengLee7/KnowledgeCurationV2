"""Survey configuration loading (architecture-neutral).

Reads ``data/survey_config.json`` into a :class:`SurveyConfig`. Documented
fields are mapped explicitly; optional extended blocks are passed through with
safe defaults so missing keys never raise.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from app.state.schemas import SurveyConfig


class ConfigError(Exception):
    """Raised when the survey config is missing or unparseable.

    Defined here (shared layer) and re-exported by
    ``app.architectures.baseline.errors`` so the baseline error hierarchy has a
    single ``ConfigError`` symbol.
    """


def load_survey_config(path: str = "data/survey_config.json") -> Tuple[SurveyConfig, dict]:
    """Load and parse the survey config.

    Returns ``(SurveyConfig, raw_dict)``. The raw dict is preserved verbatim so
    it can be republished to the static site unchanged.

    Raises:
        ConfigError: if the file is missing or contains invalid JSON.
    """
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"survey_config.json not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Malformed survey_config.json: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("survey_config.json must contain a JSON object")

    config = SurveyConfig(
        topic_overview=str(raw.get("topic_overview", "") or ""),
        research_questions=list(raw.get("research_questions") or []),
        question_context=str(raw.get("question_context", "") or ""),
        query_hints=list(raw.get("query_hints") or []),
        timeline_from_year=raw.get("timeline_from_year"),
        timeline_to_year=raw.get("timeline_to_year"),
        min_relevance_score=float(raw.get("min_relevance_score", 0.0) or 0.0),
        question_mode=raw.get("question_mode"),
        target_papers=list(raw.get("target_papers") or []),
        baseline=dict(raw.get("baseline") or {}),
        semantic_scholar=dict(raw.get("semantic_scholar") or {}),
        evaluation=dict(raw.get("evaluation") or {}),
        raw=raw,
    )
    return config, raw
