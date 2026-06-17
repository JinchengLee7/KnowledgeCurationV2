"""Baseline constants, defaults, and environment-variable accessors.

Everything tunable lives here so the deterministic behavior is easy to audit.
Environment variables override defaults; config (``survey_config.baseline``)
overrides both where applicable, resolved in the pipeline.
"""

from __future__ import annotations

import os
from pathlib import Path

ARCHITECTURE = "baseline"
SOURCE = "semantic_scholar"
SCORE_METHOD = "baseline_lexical_v1"

# --------------------------------------------------------------------------- #
# Semantic Scholar API
# --------------------------------------------------------------------------- #
DEFAULT_BASE_URL = "https://api.semanticscholar.org/graph/v1"
SEARCH_PATH = "/paper/search"
BULK_SEARCH_PATH = "/paper/search/bulk"
PAPER_PATH = "/paper"  # /paper/{id}

DEFAULT_FIELDS = [
    "paperId",
    "corpusId",
    "title",
    "abstract",
    "year",
    "authors",
    "url",
    "openAccessPdf",
    "externalIds",
    "citationCount",
    "referenceCount",
    "influentialCitationCount",
    "publicationTypes",
    "publicationDate",
    "venue",
    "fieldsOfStudy",
    "isOpenAccess",
]

USER_AGENT = "dynamic-lr-baseline/0.1 (+https://github.com/)"

# Retry / rate-limit behavior
RETRY_BACKOFF_S = [2.0, 5.0, 15.0]  # exponential-ish backoff between attempts
RATE_LIMIT_SLEEP_S = 1.1  # polite pause between successful calls (free tier ~1 rps)
MAX_ATTEMPTS = 4

# --------------------------------------------------------------------------- #
# Defaults (overridable by config.baseline)
# --------------------------------------------------------------------------- #
DEFAULT_MAX_QUERIES = 12
DEFAULT_MAX_RESULTS_PER_QUERY = 50
DEFAULT_MIN_TITLE_TOKENS = 2
DEFAULT_COMBINED_QUERY_TOKENS = 12  # keep top-N tokens for the combined query
DEFAULT_MAX_QUERY_LEN = 300

# --------------------------------------------------------------------------- #
# Scoring weights (must sum to 1.0)
# --------------------------------------------------------------------------- #
W_TITLE = 0.35
W_ABSTRACT = 0.30
W_PHRASE = 0.15
W_RECENCY = 0.10
W_IDENTIFIER = 0.05
W_CITATION = 0.05

CITATION_CAP = 1000  # citations are log-normalized then capped at this count

# --------------------------------------------------------------------------- #
# Reject reasons (closed vocabulary)
# --------------------------------------------------------------------------- #
REASON_MISSING_TITLE = "missing_title"
REASON_BELOW_THRESHOLD = "below_relevance_threshold"
REASON_OUTSIDE_TIMELINE = "outside_timeline"
REASON_DUPLICATE_MERGED = "duplicate_merged"
REASON_MALFORMED = "malformed_metadata"
REASON_API_ERROR = "api_error"
REASON_DB_ERROR = "database_error"
REASON_TARGET_NOT_FOUND = "target_not_found"
REASON_OTHER = "other"

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
DATA_DIR = Path("data")
BASELINE_DIR = DATA_DIR / "baseline"
RAW_CACHE_DIR = BASELINE_DIR / "raw_cache"
RUN_ARTIFACTS_DIR = BASELINE_DIR / "run_artifacts"
COMPARISON_DIR = DATA_DIR / "comparison"

# --------------------------------------------------------------------------- #
# Stopwords (small, fixed; intentionally minimal — no external NLP deps)
# --------------------------------------------------------------------------- #
STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have how in into is it its of on or
    that the their them then there these this to was were what when where which
    who will with how do does did using used use based via toward towards we our
    can could should would may might more most than such between within across
    been being also only over under about against among per
    """.split()
)

# Statuses written to system_status.json
STATUS_IDLE = "idle"
STATUS_LOADING_CONFIG = "loading_config"
STATUS_BUILDING_QUERIES = "building_queries"
STATUS_QUERYING = "querying_semantic_scholar"
STATUS_NORMALIZING = "normalizing"
STATUS_DEDUPING = "deduplicating"
STATUS_SCORING = "scoring"
STATUS_FILTERING = "filtering"
STATUS_PERSISTING = "persisting"
STATUS_PUBLISHING = "publishing"
STATUS_FINISHED = "finished"
STATUS_PARTIAL = "partial_success"
STATUS_FAILED = "failed"


# --------------------------------------------------------------------------- #
# Environment accessors
# --------------------------------------------------------------------------- #
def api_key() -> str | None:
    return os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or None


def base_url() -> str:
    return os.environ.get("SEMANTIC_SCHOLAR_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def request_timeout_s() -> float:
    return float(os.environ.get("REQUEST_TIMEOUT_S", "30"))


def max_candidates_per_run() -> int:
    return int(os.environ.get("MAX_CANDIDATES_PER_RUN", "200"))


def top_k_per_query() -> int:
    return int(os.environ.get("TOP_K_PER_QUERY", str(DEFAULT_MAX_RESULTS_PER_QUERY)))


def sqlite_path() -> Path:
    return Path(os.environ.get("BASELINE_SQLITE_PATH", str(BASELINE_DIR / "baseline.sqlite3")))
