from app.architectures.baseline import constants
from app.architectures.baseline.filters import apply_filters
from tests.baseline.conftest import mk_candidate


def _scored(title, score, year=2025):
    c = mk_candidate(title=title, year=year)
    c.paper_id = f"id:{title}"
    c.score = score
    return c


def test_missing_title_rejected(survey_config):
    c = _scored("", 0.9)
    c.title = ""
    accepted, rejects = apply_filters([c], survey_config, "run1")
    assert not accepted
    assert rejects[0].reason == constants.REASON_MISSING_TITLE


def test_below_threshold_rejected_with_evidence(survey_config):
    survey_config.min_relevance_score = 0.3
    c = _scored("Explainable AI", 0.1)
    accepted, rejects = apply_filters([c], survey_config, "run1")
    assert not accepted
    assert rejects[0].reason == constants.REASON_BELOW_THRESHOLD
    assert rejects[0].evidence["threshold"] == 0.3
    assert "matched_terms" in rejects[0].evidence


def test_inside_timeline_accepted_when_score_passes(survey_config):
    c = _scored("Explainable AI", 0.9, year=2025)
    accepted, rejects = apply_filters([c], survey_config, "run1")
    assert len(accepted) == 1 and not rejects


def test_outside_timeline_rejected_when_strict(survey_config):
    survey_config.baseline["strict_timeline"] = True
    c = _scored("Explainable AI", 0.9, year=2000)
    accepted, rejects = apply_filters([c], survey_config, "run1")
    assert not accepted
    assert rejects[0].reason == constants.REASON_OUTSIDE_TIMELINE


def test_accepted_sorted_by_score_desc(survey_config):
    lo = _scored("Explainable AI low", 0.4)
    hi = _scored("Explainable AI high", 0.8)
    accepted, _ = apply_filters([lo, hi], survey_config, "run1")
    assert [p.score for p in accepted] == [0.8, 0.4]
