"""Shared fixtures: fixture Semantic Scholar responses and temp working dirs.

Unit tests never hit the network. The ``fake_search`` fixture monkeypatches the
client so the full pipeline runs against in-memory fixture data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.state.schemas import PaperCandidate, PaperIdentifiers, SurveyConfig


def s2_item(paper_id, title, year=2025, abstract="", doi=None, arxiv=None,
            authors=("Alice Smith",), citations=10, corpus=None):
    return {
        "paperId": paper_id,
        "corpusId": corpus,
        "title": title,
        "abstract": abstract,
        "year": year,
        "authors": [{"name": a} for a in authors],
        "url": f"https://www.semanticscholar.org/paper/{paper_id}",
        "openAccessPdf": {"url": f"https://example.org/{paper_id}.pdf"},
        "externalIds": {k: v for k, v in (("DOI", doi), ("ArXiv", arxiv)) if v},
        "citationCount": citations,
        "referenceCount": 5,
        "influentialCitationCount": 2,
        "publicationTypes": ["JournalArticle"],
        "publicationDate": f"{year}-01-01",
        "venue": "Journal of XAI",
        "fieldsOfStudy": ["Computer Science"],
        "isOpenAccess": True,
    }


@pytest.fixture
def sample_items():
    """A small fixture corpus. Includes a strong match, a weak match, and a
    duplicate (same DOI, different title length) of the first."""
    return [
        s2_item("s1", "Explainable AI methods for interpretable models",
                abstract="We study explainable AI and interpretable methods.",
                doi="10.1/xai", citations=100),
        s2_item("s1dup", "Explainable AI methods for interpretable models (extended version)",
                abstract="Extended study of explainable AI interpretability.",
                doi="10.1/xai", citations=120),  # same DOI -> duplicate of s1
        s2_item("s2", "A paper about marine biology and coral reefs",
                abstract="Nothing to do with the survey topic.",
                doi="10.2/coral", citations=3),
        s2_item("s3", "Uncertainty quantification for AI explanation",
                abstract="Uncertainty estimates explaining AI decisions.",
                arxiv="2501.00001", citations=40),
    ]


@pytest.fixture
def survey_config():
    return SurveyConfig(
        topic_overview="Explainable AI",
        research_questions=["What methods make AI explainable?"],
        query_hints=["uncertainty quantification", "AI explanation"],
        timeline_from_year=2024,
        timeline_to_year=2026,
        min_relevance_score=0.3,
        baseline={"max_queries": 12, "max_results_per_query": 50, "min_title_tokens": 2},
        semantic_scholar={},
    )


@pytest.fixture
def config_file(tmp_path):
    """Write a survey_config.json into a temp dir and return its path."""
    cfg = {
        "topic_overview": "Explainable AI",
        "research_questions": ["What methods make AI explainable?"],
        "query_hints": ["uncertainty quantification", "AI explanation"],
        "timeline_from_year": 2024,
        "timeline_to_year": 2026,
        "min_relevance_score": 0.3,
        "baseline": {"max_queries": 12, "max_results_per_query": 50},
    }
    p = tmp_path / "survey_config.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


@pytest.fixture
def fake_search(monkeypatch, sample_items):
    """Patch the client so search() returns fixture items (no network, no sleep)."""
    from app.architectures.baseline.semantic_scholar_client import SemanticScholarClient

    def _search(self, query, fields, limit):
        return [dict(it) for it in sample_items]

    monkeypatch.setattr(SemanticScholarClient, "search", _search)
    return _search


def mk_candidate(title="Some title", year=2025, doi=None, arxiv=None, s2=None,
                 authors=("Alice Smith",), abstract=None):
    return PaperCandidate(
        title=title,
        authors=list(authors),
        year=year,
        abstract=abstract,
        identifiers=PaperIdentifiers(doi=doi, arxiv_id=arxiv, semantic_scholar_id=s2),
        sources=["semantic_scholar"],
    )
