from app.architectures.baseline import identity
from tests.baseline.conftest import mk_candidate


def test_normalize_doi_strips_prefixes():
    assert identity.normalize_doi("https://doi.org/10.1/ABC") == "10.1/abc"
    assert identity.normalize_doi("doi:10.1/AbC") == "10.1/abc"


def test_normalize_arxiv_strips_version_and_prefix():
    assert identity.normalize_arxiv("arXiv:2501.00001v3") == "2501.00001"
    assert identity.normalize_arxiv("https://arxiv.org/abs/2501.00001") == "2501.00001"


def test_doi_yields_stable_id_regardless_of_other_fields():
    a = mk_candidate(title="Title A", doi="10.1/x")
    b = mk_candidate(title="A completely different title", doi="10.1/X")
    assert identity.stable_paper_id(a) == identity.stable_paper_id(b) == "doi:10.1/x"


def test_arxiv_id_priority_after_doi():
    c = mk_candidate(arxiv="2501.00001v2")
    assert identity.stable_paper_id(c) == "arxiv:2501.00001"


def test_fingerprint_fallback_same_title_year_author():
    a = mk_candidate(title="Same Title", year=2024, authors=("Jane Doe",))
    b = mk_candidate(title="same   title", year=2024, authors=("jane doe",))
    assert identity.stable_paper_id(a) == identity.stable_paper_id(b)
    assert identity.stable_paper_id(a).startswith("fp:")
