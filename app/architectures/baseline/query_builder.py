"""Deterministic query generation from the survey config.

No LLM, no external NLP. Fixed rules only:

    1. topic_overview                          -> one query
    2. each research_question (cleaned)        -> one query
    3. each query_hint                         -> one query
    4. one combined query of top non-stopword tokens from all of the above

Then: dedup case-insensitively, preserve order, cap at ``max_queries``.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import List

from app.architectures.baseline import constants
from app.architectures.baseline.models import GeneratedQuery
from app.state.schemas import SurveyConfig

_WS = re.compile(r"\s+")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_TOKEN = re.compile(r"[a-z0-9]+")


def clean_query(text: str) -> str:
    """Normalize a query string deterministically (whitespace/control/length)."""
    text = _CTRL.sub("", text or "")
    text = _WS.sub(" ", text).strip()
    if len(text) > constants.DEFAULT_MAX_QUERY_LEN:
        text = text[: constants.DEFAULT_MAX_QUERY_LEN].rstrip()
    return text


def _tokens(text: str) -> List[str]:
    return _TOKEN.findall((text or "").lower())


def _combined_query(config: SurveyConfig, max_tokens: int) -> str:
    """Build the combined query: top tokens by frequency, deterministic ties.

    Ties broken alphabetically so the output is reproducible.
    """
    counter: Counter[str] = Counter()
    parts = [config.topic_overview, *config.research_questions, *config.query_hints]
    for part in parts:
        for tok in _tokens(part):
            if tok in constants.STOPWORDS or len(tok) < 2:
                continue
            counter[tok] += 1
    if not counter:
        return ""
    # Sort by (-count, token) for a stable, deterministic ordering.
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    top = [tok for tok, _ in ranked[:max_tokens]]
    return " ".join(top)


def build_queries(config: SurveyConfig) -> List[GeneratedQuery]:
    """Return the deterministic, deduplicated, capped query list."""
    max_queries = int(config.baseline.get("max_queries", constants.DEFAULT_MAX_QUERIES))
    max_tokens = int(
        config.baseline.get("combined_query_tokens", constants.DEFAULT_COMBINED_QUERY_TOKENS)
    )

    raw: List[GeneratedQuery] = []
    idx = 0

    if config.topic_overview.strip():
        raw.append(GeneratedQuery(clean_query(config.topic_overview), config.topic_overview, "topic", idx))
        idx += 1

    for rq in config.research_questions:
        cleaned = clean_query(rq)
        if cleaned:
            raw.append(GeneratedQuery(cleaned, rq, "research_question", idx))
            idx += 1

    for hint in config.query_hints:
        cleaned = clean_query(hint)
        if cleaned:
            raw.append(GeneratedQuery(cleaned, hint, "query_hint", idx))
            idx += 1

    combined = _combined_query(config, max_tokens)
    if combined:
        raw.append(GeneratedQuery(combined, combined, "combined", idx))
        idx += 1

    # Deduplicate case-insensitively, preserving first occurrence / order.
    seen = set()
    deduped: List[GeneratedQuery] = []
    for gq in raw:
        key = gq.query.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(gq)

    return deduped[:max_queries]
