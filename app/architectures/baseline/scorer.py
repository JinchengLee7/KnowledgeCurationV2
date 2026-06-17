"""Deterministic relevance scoring (lexical + metadata, no LLM, no embeddings).

    score = 0.35 * title_keyword_overlap
          + 0.30 * abstract_keyword_overlap
          + 0.15 * query_phrase_match
          + 0.10 * recency_score
          + 0.05 * identifier_score
          + 0.05 * citation_score

All components are normalized to [0, 1] and stored on the candidate so any
rejection is fully explainable.
"""

from __future__ import annotations

import math
import re
from typing import List, Set, Tuple

from app.architectures.baseline import constants
from app.architectures.baseline.models import GeneratedQuery, ScoreComponents
from app.state.schemas import PaperCandidate, SurveyConfig

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    return _TOKEN.findall((text or "").lower())


def _content_tokens(text: str) -> Set[str]:
    return {t for t in _tokens(text) if t not in constants.STOPWORDS and len(t) >= 2}


def _config_terms(config: SurveyConfig) -> Set[str]:
    """The bag of meaningful terms from the whole config (deterministic)."""
    terms: Set[str] = set()
    for part in [config.topic_overview, *config.research_questions, *config.query_hints]:
        terms |= _content_tokens(part)
    return terms


def _overlap(terms: Set[str], text: str) -> float:
    if not terms:
        return 0.0
    text_tokens = _content_tokens(text)
    if not text_tokens:
        return 0.0
    return len(terms & text_tokens) / len(terms)


def _phrase_match(queries: List[GeneratedQuery], title: str, abstract: str) -> float:
    """1.0 exact query phrase in title/abstract; 0.5 partial; else 0.0."""
    haystack = f"{title or ''} {abstract or ''}".lower()
    if not haystack.strip():
        return 0.0
    best = 0.0
    for gq in queries:
        phrase = gq.query.lower().strip()
        if not phrase:
            continue
        if phrase in haystack:
            return 1.0
        # partial: at least half the phrase tokens appear
        ptoks = [t for t in _tokens(phrase) if t not in constants.STOPWORDS]
        if ptoks:
            present = sum(1 for t in ptoks if t in haystack)
            if present / len(ptoks) >= 0.5:
                best = max(best, 0.5)
    return best


def _recency(year, config: SurveyConfig) -> float:
    """1.0 inside timeline; 0.5 if year missing; linear decay outside."""
    if year is None:
        return 0.5
    lo = config.timeline_from_year
    hi = config.timeline_to_year
    if lo is not None and hi is not None:
        if lo <= year <= hi:
            return 1.0
        # decay by 0.1 per year outside the window, floored at 0.
        if year < lo:
            return max(0.0, 1.0 - 0.1 * (lo - year))
        return max(0.0, 1.0 - 0.1 * (year - hi))
    return 1.0


def _identifier_score(candidate: PaperCandidate) -> float:
    ids = candidate.identifiers
    present = sum(
        1 for v in (ids.doi, ids.arxiv_id, ids.semantic_scholar_id, ids.corpus_id) if v
    )
    return min(1.0, present / 2.0)  # two+ strong ids -> full credit


def _citation_score(candidate: PaperCandidate) -> float:
    cc = candidate.citation_count or 0
    if cc <= 0:
        return 0.0
    capped = min(cc, constants.CITATION_CAP)
    return math.log1p(capped) / math.log1p(constants.CITATION_CAP)


def score(
    candidate: PaperCandidate,
    config: SurveyConfig,
    queries: List[GeneratedQuery],
) -> Tuple[float, ScoreComponents]:
    """Compute the relevance score and its components for a candidate."""
    terms = _config_terms(config)
    comp = ScoreComponents(
        title_keyword_overlap=_overlap(terms, candidate.title),
        abstract_keyword_overlap=_overlap(terms, candidate.abstract or ""),
        query_phrase_match=_phrase_match(queries, candidate.title, candidate.abstract or ""),
        recency_score=_recency(candidate.year, config),
        identifier_score=_identifier_score(candidate),
        citation_score=_citation_score(candidate),
    )
    total = (
        constants.W_TITLE * comp.title_keyword_overlap
        + constants.W_ABSTRACT * comp.abstract_keyword_overlap
        + constants.W_PHRASE * comp.query_phrase_match
        + constants.W_RECENCY * comp.recency_score
        + constants.W_IDENTIFIER * comp.identifier_score
        + constants.W_CITATION * comp.citation_score
    )
    return round(total, 4), comp


def apply_score(candidate: PaperCandidate, config: SurveyConfig,
                queries: List[GeneratedQuery]) -> PaperCandidate:
    """Score the candidate in place and record components + method."""
    total, comp = score(candidate, config, queries)
    candidate.score = total
    candidate.score_components = comp.as_dict()
    candidate.score_method = constants.SCORE_METHOD
    return candidate
