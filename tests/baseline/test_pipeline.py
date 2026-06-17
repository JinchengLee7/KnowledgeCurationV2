"""End-to-end pipeline tests using fixture (non-network) search results."""

import json

from app.architectures.baseline import pipeline


def test_pipeline_end_to_end_writes_outputs(tmp_path, monkeypatch, fake_search, config_file):
    monkeypatch.chdir(tmp_path)
    # config_file was created under tmp_path by the fixture
    result = pipeline.run(config_path=str(config_file), dry_run=False)

    assert result.status in ("success", "partial_success")
    assert result.papers_accepted >= 1
    # 5 queries x 4 fixture items = 20 raw; the 4 distinct papers (s1==s1dup by
    # DOI) collapse to 3 unique across the whole run.
    assert result.candidates_found == 20
    assert result.candidates_after_dedupe == 3

    papers = json.loads((tmp_path / "site" / "data" / "papers.json").read_text())
    titles = {p["title"] for p in papers}
    # marine biology paper is off-topic and should be filtered out
    assert not any("coral" in t.lower() for t in titles)

    # artifacts written
    art = tmp_path / "data" / "baseline" / "run_artifacts" / result.run_id
    assert (art / "final_report.json").exists()
    assert (art / "metrics.json").exists()


def test_pipeline_is_deterministic(tmp_path, monkeypatch, fake_search, config_file):
    monkeypatch.chdir(tmp_path)
    r1 = pipeline.run(config_path=str(config_file), dry_run=True)
    r2 = pipeline.run(config_path=str(config_file), dry_run=True)
    assert r1.papers_accepted == r2.papers_accepted
    assert r1.candidates_after_dedupe == r2.candidates_after_dedupe
    assert r1.candidates_rejected == r2.candidates_rejected


def test_pipeline_missing_config_is_failure(tmp_path, monkeypatch, fake_search):
    monkeypatch.chdir(tmp_path)
    result = pipeline.run(config_path=str(tmp_path / "nope.json"), dry_run=True)
    assert result.status == "failure"
    assert result.errors
