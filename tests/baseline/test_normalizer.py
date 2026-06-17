from app.architectures.baseline.normalizer import normalize
from tests.baseline.conftest import s2_item


def test_normalize_maps_core_fields():
    item = s2_item("s1", "Title Here", year=2025, abstract="abs",
                   doi="10.1/x", arxiv="2501.1", authors=("A B", "C D"))
    c = normalize(item, query="q")
    assert c.title == "Title Here"
    assert c.year == 2025
    assert c.abstract == "abs"
    assert c.authors == ["A B", "C D"]
    assert c.identifiers.doi == "10.1/x"
    assert c.identifiers.arxiv_id == "2501.1"
    assert c.identifiers.semantic_scholar_id == "s1"
    assert c.sources == ["semantic_scholar"]
    assert c.citation_count == 10
    assert "semantic_scholar" in c.raw


def test_normalize_handles_missing_optional_fields():
    c = normalize({"title": "Bare"}, query="q")
    assert c.title == "Bare"
    assert c.abstract is None
    assert c.authors == []
    assert c.identifiers.doi is None
