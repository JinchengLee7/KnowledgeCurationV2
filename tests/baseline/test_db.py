from app.architectures.baseline import db
from tests.baseline.conftest import mk_candidate

NOW = "2025-01-01T00:00:00Z"


def test_schema_creates_tables():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"papers", "source_hits", "rejects", "merge_events", "runs",
            "api_cache", "query_state"} <= names


def test_upsert_does_not_duplicate_existing_paper():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    c = mk_candidate(title="Paper", doi="10.1/x")
    c.paper_id = "doi:10.1/x"
    with db.transaction(conn):
        db.insert_paper(conn, c, NOW)
    # second observation: update, not insert
    found = db.find_existing(conn, mk_candidate(title="Paper 2", doi="10.1/x"))
    assert found is not None
    with db.transaction(conn):
        c.title = "Paper updated"
        db.update_paper(conn, c, NOW)
    count = conn.execute("SELECT COUNT(*) AS c FROM papers").fetchone()["c"]
    assert count == 1
    assert conn.execute("SELECT title FROM papers").fetchone()["title"] == "Paper updated"


def test_api_cache_roundtrip():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    assert db.cache_get(conn, "k") is None
    db.cache_put(conn, "k", "semantic_scholar", "/paper/search",
                 {"q": "x"}, {"data": [1, 2, 3]}, 200, NOW)
    assert db.cache_get(conn, "k") == {"data": [1, 2, 3]}


def test_query_state_tracks_consecutive_zero_accepts():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    for _ in range(3):
        db.update_query_state(conn, "q", "q", candidates=5, accepted=0,
                              duplicates=0, errors=0, now=NOW)
    conn.commit()
    row = db.get_query_state(conn)["q"]
    assert row["consecutive_zero_accept"] == 3
    db.update_query_state(conn, "q", "q", candidates=5, accepted=2,
                          duplicates=0, errors=0, now=NOW)
    assert db.get_query_state(conn)["q"]["consecutive_zero_accept"] == 0
