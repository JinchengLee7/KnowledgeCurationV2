from app.architectures.baseline.query_builder import build_queries
from app.architectures.baseline.scorer import score
from tests.baseline.conftest import mk_candidate


def test_components_in_unit_range(survey_config):
    queries = build_queries(survey_config)
    c = mk_candidate(title="Explainable AI methods",
                     abstract="explainable AI interpretable methods", doi="10.1/x",
                     year=2025)
    total, comp = score(c, survey_config, queries)
    for v in comp.as_dict().values():
        assert 0.0 <= v <= 1.0
    assert 0.0 <= total <= 1.0


def test_relevant_scores_higher_than_irrelevant(survey_config):
    queries = build_queries(survey_config)
    good = mk_candidate(title="Explainable AI methods for interpretable models",
                        abstract="explainable AI interpretable uncertainty methods",
                        doi="10.1/x", year=2025)
    bad = mk_candidate(title="Marine biology of coral reefs",
                       abstract="fish and coral", year=2025)
    good_total, _ = score(good, survey_config, queries)
    bad_total, _ = score(bad, survey_config, queries)
    assert good_total > bad_total


def test_phrase_match_full_credit(survey_config):
    queries = build_queries(survey_config)
    c = mk_candidate(title="explainable ai in practice",
                     abstract="discusses explainable ai", year=2025)
    _, comp = score(c, survey_config, queries)
    assert comp.query_phrase_match == 1.0


def test_missing_year_recency_half(survey_config):
    queries = build_queries(survey_config)
    c = mk_candidate(title="Explainable AI", year=None)
    _, comp = score(c, survey_config, queries)
    assert comp.recency_score == 0.5
