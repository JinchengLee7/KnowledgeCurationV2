from app.architectures.baseline.query_builder import build_queries, clean_query


def test_query_generation_is_deterministic(survey_config):
    a = [q.query for q in build_queries(survey_config)]
    b = [q.query for q in build_queries(survey_config)]
    assert a == b


def test_includes_topic_questions_hints_and_combined(survey_config):
    kinds = {q.kind for q in build_queries(survey_config)}
    assert {"topic", "research_question", "query_hint", "combined"} <= kinds


def test_dedup_case_insensitive(survey_config):
    survey_config.query_hints = ["Explainable AI", "explainable ai"]
    survey_config.topic_overview = "Explainable AI"
    queries = [q.query.lower() for q in build_queries(survey_config)]
    assert len(queries) == len(set(queries))


def test_max_queries_cap(survey_config):
    survey_config.baseline["max_queries"] = 2
    assert len(build_queries(survey_config)) == 2


def test_clean_query_collapses_and_truncates():
    assert clean_query("  a\t b\n c ") == "a b c"
    assert len(clean_query("x" * 1000)) <= 300
