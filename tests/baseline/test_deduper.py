from app.architectures.baseline import db, deduper
from tests.baseline.conftest import mk_candidate


def test_dedupe_collapses_same_doi():
    cands = [
        mk_candidate(title="Short", doi="10.1/x", abstract="a"),
        mk_candidate(title="A much longer richer title", doi="10.1/x",
                     abstract="much longer abstract here"),
    ]
    unique, dupes = deduper.dedupe_candidates(cands)
    assert len(unique) == 1
    assert dupes == 1
    # merge keeps richer title + longer abstract
    assert unique[0].title == "A much longer richer title"
    assert unique[0].abstract == "much longer abstract here"


def test_merge_never_overwrites_with_null():
    primary = mk_candidate(title="T", doi="10.1/x", abstract="kept")
    primary.pdf_url = "https://good.pdf"
    incoming = mk_candidate(title="T", doi="10.1/x", abstract=None)
    merged = deduper.merge_candidates(primary, incoming)
    assert merged.abstract == "kept"
    assert merged.pdf_url == "https://good.pdf"


def test_resolve_against_db_detects_existing():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    existing = mk_candidate(title="Existing", doi="10.1/x")
    existing.paper_id = "doi:10.1/x"
    with db.transaction(conn):
        db.insert_paper(conn, existing, "2025-01-01T00:00:00Z")

    incoming = mk_candidate(title="Existing extended", doi="10.1/x")
    merged, is_new, event = deduper.resolve_against_db(
        conn, incoming, "run1", "q", "semantic_scholar")
    assert is_new is False
    assert event is not None
    assert event.matched_on == "doi"
    assert merged.paper_id == "doi:10.1/x"
