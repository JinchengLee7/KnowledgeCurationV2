import json

from app.architectures.baseline import constants, db, publisher
from app.state import store
from app.state.schemas import ManagerRunResult
from tests.baseline.conftest import mk_candidate

NOW = "2025-01-01T00:00:00Z"


def _result(run_id="run1"):
    return ManagerRunResult(
        architecture="baseline", queries_generated=1, sources_queried=["semantic_scholar"],
        candidates_found=1, candidates_after_dedupe=1, papers_accepted=1,
        candidates_rejected=0, dry_run=False, started_at=NOW, finished_at=NOW,
        status="success", run_id=run_id, errors=[])


def test_publisher_writes_valid_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conn = db.connect(":memory:")
    db.init_schema(conn)
    c = mk_candidate(title="Explainable AI", doi="10.1/x", year=2025)
    c.paper_id = "doi:10.1/x"
    c.score = 0.7
    with db.transaction(conn):
        db.insert_paper(conn, c, NOW)

    status = publisher.publish(conn, _result(), {"topic_overview": "Explainable AI"},
                               dry_run=False)
    assert status["total_papers"] == 1

    papers = json.loads((tmp_path / "site" / "data" / "papers.json").read_text())
    assert papers[0]["title"] == "Explainable AI"
    assert papers[0]["provenance"]["architectures_seen"] == ["baseline"]

    # canonical NDJSON also written
    ndjson = (tmp_path / "data" / "papers.ndjson").read_text().strip().splitlines()
    assert len(ndjson) == 1
    assert json.loads(ndjson[0])["paper_id"] == "doi:10.1/x"


def test_publisher_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conn = db.connect(":memory:")
    db.init_schema(conn)
    publisher.publish(conn, _result(), {}, dry_run=True)
    assert not (tmp_path / "site").exists()
    assert not (tmp_path / "data" / "papers.ndjson").exists()
