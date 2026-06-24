# CLAUDE.md

## Project Identity

This repository is **Dynamic-LR**, a dynamic literature-retrieval, corpus-management, and survey-production system. Its long-term purpose is to compare alternative automation architectures for literature-survey workflows:

```text
baseline
single-agent
multi-agent
```

The new work in this repository is a strong, deterministic, non-LLM baseline. It is not a toy control. It must be a competent retrieval-and-curation system whose decisions are inspectable, replayable, and comparable with the existing LLM-based systems.

The baseline retrieves and reconciles paper metadata from exactly three providers in its first complete implementation:

```text
semantic_scholar
arxiv
openalex
```

The baseline must normalize records from all three providers into the project’s shared paper schema, preserve all source provenance, resolve duplicate and conflicting records conservatively, score relevance deterministically, persist accepted and rejected records, maintain durable local state, and publish to the existing static-site data contract.

The baseline must not use an LLM for planning, query expansion, relevance judgment, summarization, tool selection, source selection, publishing decisions, or error-recovery decisions.

## Core Research Question

The engineering work supports this research question:

> Does LLM-based sequential decision-making improve a literature-survey workflow compared with a strong deterministic, multi-source API-driven baseline?

Everything implemented for the baseline should make this comparison possible. The baseline and agentic pipelines should share as much infrastructure as practical:

- the same survey configuration contract;
- the same canonical `PaperRecord` representation;
- the same accepted-paper and reject-record formats;
- the same public-site output contract;
- the same evaluation metrics and run-summary structure;
- architecture-specific artifact directories;
- shared, versioned schemas for retrieval, screening, evidence, and run state.

The systems may differ in **decision policy**, not in whether they preserve the information needed to audit those decisions.

## System Architecture and Run Policy

Treat Dynamic-LR as three strictly separated layers:

```text
Acquisition  -> query planning, API calls, raw caching, normalization,
                identifier resolution, deduplication

Curation     -> eligibility filters, relevance scoring, screening decisions,
                evidence extraction, human overrides

Presentation -> NDJSON/JSON exports, static site files, survey drafts,
                comparison reports
```

Do not allow one layer to silently perform another layer’s job.

- Acquisition must not make an unlogged relevance decision.
- Curation must not call providers directly or overwrite raw provenance.
- Presentation artifacts are projections, never the sole source of truth.
- SQLite state, immutable run artifacts, and append-only event records are authoritative.

### Single-writer rule

Each run has exactly one orchestrator: `pipeline.py`. It owns the run lifecycle, budget, checkpoints, final status, and publication permission.

Provider clients, normalizers, scorers, agent modules, and publishers must not independently mark a run successful, publish site artifacts, or overwrite another architecture’s decisions.

### Architecture isolation rule

A `ScreeningDecision` is architecture-specific. A baseline decision must never overwrite a single-agent, multi-agent, or human decision. Each new decision is a new append-only event with its own `decision_source`, `criteria_version`, timestamp, and rationale.

### Reproducibility rule

For the same:

```text
survey config
provider response cache / fixture responses
database state
runtime settings
policy version
run seed
```

the baseline must produce the same query plan, normalized records, identity matches, merge behavior, scores, filters, artifacts, and final result.

Network timing and live provider ranking are external nondeterminism. Cache-backed replay is the standard mechanism for deterministic regression tests and frozen-corpus evaluation.

## Current Project Context

The existing LLM-based architectures must remain intact. Do not break or rewrite them while implementing the baseline.

The baseline must be selectable through the existing CLI:

```bash
python -m app.run --architecture baseline --dry-run
```

The existing architecture commands must continue to work:

```bash
python -m app.run --architecture single-agent --dry-run
python -m app.run --architecture multi-agent --dry-run
```

The baseline must integrate through the existing manager layer instead of becoming a disconnected script.

## Non-Negotiable Baseline Rules

The baseline must be deterministic.

The baseline must not call any LLM chat, completion, instruction-following, or agent endpoint. It must not use an LLM for:

```text
planning
search-query reasoning
query rewriting
query prioritization
source selection
tool selection
sub-goal generation
delegation
candidate relevance judgment
paper summarization
run evaluation
publishing decisions
error recovery decisions
```

A non-LLM embedding model may be added later only as a fixed, versioned scoring function. The initial implementation should use lexical scoring, metadata scoring, and deterministic filters only.

The first complete baseline must use all three providers:

```text
Semantic Scholar Graph API
arXiv API
OpenAlex Works API
```

All three providers must be invoked by fixed policy for every eligible query unless a documented configuration flag disables one. The baseline must not dynamically choose a source because one source “looks more promising.” Provider failure is observable as a partial failure, not a trigger for hidden source-selection logic.

Retry jitter must be deterministic in baseline mode. Derive it from a stable hash of `run_id + provider + request_fingerprint + retry_attempt`, or disable jitter for fixture replay. Do not call an unseeded random generator inside deterministic core code.

## Intended Baseline Workflow

The baseline pipeline follows this workflow:

```text
read survey config
  -> validate and version config
  -> build canonical deterministic query plan
  -> translate canonical queries into provider-specific requests
  -> fetch Semantic Scholar, arXiv, and OpenAlex concurrently
     with provider-specific rate limits, retries, and cache policy
  -> persist raw response snapshots and retrieval events
  -> normalize source results into shared candidate records
  -> validate and repair minor metadata issues
  -> resolve stable identity and deduplicate within run
  -> resolve candidates against the local corpus database
  -> enrich canonical records from all matching source records
  -> apply deterministic metadata eligibility filters
  -> score relevance deterministically
  -> write screening decisions, accepts, rejects, and merge/conflict events
  -> update query state, provider metrics, and run manifest
  -> checkpoint durable database state
  -> export NDJSON / JSON projections
  -> publish static site data atomically
  -> return structured ManagerRunResult
```

The baseline is an automated loop, not a one-off search script. Every run should leave artifacts that improve observability on future runs: query performance, source coverage, duplicate and false-merge candidates, API errors, target-paper checks, and database updates.

## Canonical Data Contracts

Every architecture should write these structured record types consistently.

### `PaperRecord`

The canonical, source-agnostic paper identity and metadata record.

```json
{
  "paper_key": "doi:10.0000/example",
  "identifiers": {
    "doi": "10.0000/example",
    "arxiv": "2501.00001",
    "openalex": "W1234567890",
    "semantic_scholar": "abc123",
    "semantic_scholar_corpus": "987654",
    "pmid": null,
    "acl": null,
    "mag": null
  },
  "title": "Example Paper",
  "title_normalized": "example paper",
  "abstract": "...",
  "authors": [],
  "year": 2025,
  "publication_date": "2025-01-15",
  "venue": "Example Venue",
  "citation_count": 42,
  "document_type": "article",
  "open_access": true,
  "primary_url": "...",
  "pdf_url": "...",
  "first_seen_run_id": "...",
  "first_seen_at": "...",
  "last_seen_at": "...",
  "provenance": {
    "sources_seen": ["semantic_scholar", "arxiv", "openalex"],
    "source_record_ids": {},
    "field_sources": {},
    "metadata_conflicts": []
  }
}
```

### `RetrievalEvent`

One event per provider result occurrence. Do not collapse events just because the paper later merges.

```json
{
  "event_id": "...",
  "run_id": "...",
  "architecture": "baseline",
  "query_id": "q_003",
  "query_origin": "config",
  "canonical_query": "...",
  "provider_query": "...",
  "source": "openalex",
  "source_rank": 12,
  "request_fingerprint": "...",
  "cache_status": "miss",
  "raw_payload_hash": "...",
  "retrieved_at": "..."
}
```

### `ScreeningDecision`

A typed, append-only decision record.

```json
{
  "decision_id": "...",
  "paper_key": "...",
  "run_id": "...",
  "architecture": "baseline",
  "stage": "baseline_score",
  "decision": "include",
  "score": 0.62,
  "criteria_version": "baseline_lexical_v1",
  "decision_source": "rule",
  "brief_rationale": "Title and abstract satisfy threshold.",
  "created_at": "..."
}
```

Allowed stages:

```text
metadata_filter
baseline_score
agent_review
human_override
evidence_validation
```

Allowed decisions:

```text
include
exclude
needs_review
defer
```

### `EvidenceUnit`

An evidence-bearing extraction for later agentic or human synthesis. The baseline may initially create only lightweight evidence placeholders, but must preserve the references needed to add richer extraction later.

```text
paper_key
claim_type (finding|method|result|limitation)
text_or_source_span
source_locator
created_by
parent_cluster_id
parent_survey_section_id
```

### `RunManifest`

A durable record of what occurred in a run.

```text
run_id
architecture
git_commit
config_hash
policy_versions
provider_plan
query_plan
cache_policy
started_at
finished_at
artifacts_written
provider_outcomes
retry_counts
failures
final_status
```

## Survey Config Contract

The baseline reads from:

```text
data/survey_config.json
```

Required shared fields:

```text
topic_overview
research_questions
question_context
query_hints
timeline_from_year
timeline_to_year
min_relevance_score
```

Optional fields must be parsed safely and ignored only when genuinely irrelevant:

```text
target_papers
sources
semantic_scholar
arxiv
openalex
baseline
evaluation
```

Recommended extended configuration shape:

```json
{
  "topic_overview": "Explainable AI",
  "question_mode": 3,
  "research_questions": [
    "What methods have been used to make AI explainable?",
    "How have uncertainty estimates been used for explaining AI decisions?",
    "What methods have been used to make AI interpretable?"
  ],
  "question_context": "Prioritize practical methods, rigorous evaluation, and reproducible experimental settings.",
  "query_hints": [
    "AI explanation",
    "uncertainty quantification",
    "human AI interaction"
  ],
  "timeline_from_year": 2024,
  "timeline_to_year": 2026,
  "min_relevance_score": 0.30,
  "target_papers": [],
  "sources": {
    "enabled": ["semantic_scholar", "arxiv", "openalex"],
    "require_all": false,
    "concurrent_provider_fetches": true
  },
  "baseline": {
    "max_queries": 12,
    "max_results_per_query": 50,
    "max_candidates_per_run": 500,
    "max_pages_per_query_per_source": 3,
    "enable_raw_cache": true,
    "enable_sqlite": true,
    "strict_timeline_filter": false,
    "min_title_tokens": 2,
    "require_title": true,
    "require_year": false,
    "require_abstract": false,
    "deterministic_seed": "dynamic-lr-baseline-v1",
    "retry_jitter_mode": "deterministic",
    "source_timeout_s": 30
  },
  "semantic_scholar": {
    "enabled": true,
    "max_results_per_query": 50,
    "cache_ttl_seconds": 21600,
    "fields": ["paperId", "corpusId", "title", "abstract", "year", "authors", "url", "openAccessPdf", "externalIds", "citationCount", "referenceCount", "influentialCitationCount", "publicationTypes", "publicationDate", "venue", "fieldsOfStudy", "isOpenAccess"]
  },
  "arxiv": {
    "enabled": true,
    "max_results_per_query": 100,
    "cache_ttl_seconds": 86400,
    "min_request_interval_seconds": 3.0,
    "categories": [],
    "sort_by": "submittedDate",
    "sort_order": "descending"
  },
  "openalex": {
    "enabled": true,
    "max_results_per_query": 100,
    "cache_ttl_seconds": 21600,
    "per_page": 100,
    "work_types": ["article", "preprint", "review"],
    "exclude_retracted": true,
    "exclude_paratext": true,
    "sort": "relevance_score:desc"
  },
  "evaluation": {
    "frozen_corpus_mode": false,
    "target_paper_checks": true,
    "record_possible_duplicates": true
  }
}
```

Do not assume optional blocks or fields exist. Apply documented defaults through a versioned config parser.

## Provider Architecture

Implement providers behind a common abstraction. Do not put provider-specific request logic inside the pipeline, scorer, or deduper.

Recommended structure:

```text
app/architectures/baseline/providers/
  __init__.py
  base.py
  semantic_scholar.py
  arxiv.py
  openalex.py
  rate_limit.py
  cache.py
```

Recommended provider contract:

```python
class LiteratureProvider(Protocol):
    source_name: str

    async def search(self, request: ProviderSearchRequest) -> ProviderSearchResult:
        ...

    async def lookup(self, identifier: ProviderLookupRequest) -> ProviderLookupResult:
        ...

    def translate_query(self, canonical_query: CanonicalQuery, config: SurveyConfig) -> ProviderQuery:
        ...
```

Every `ProviderSearchResult` must contain:

```text
source
request_fingerprint
provider_query
status (success|partial_success|retryable_failure|permanent_failure|skipped_by_policy)
raw_payload_refs
records
next_page_state
latency_ms
api_calls
cache_hits
cache_misses
retries
errors
```

### Semantic Scholar contract

Use the Semantic Scholar Academic Graph API for metadata-rich search and identifier lookup.

Initial endpoints:

```text
GET https://api.semanticscholar.org/graph/v1/paper/search
GET https://api.semanticscholar.org/graph/v1/paper/{paper_id}
```

Use only supported filters and requested fields. Semantic Scholar search does not support Boolean operators or wildcards; quoted text is supported. It does not generally expand acronyms, so query expansion must remain explicit, deterministic, and config-driven.

Environment variables:

```text
SEMANTIC_SCHOLAR_API_KEY
SEMANTIC_SCHOLAR_BASE_URL=https://api.semanticscholar.org/graph/v1
```

### arXiv contract

Use the arXiv query API as a preprint-oriented provider.

Initial endpoint:

```text
GET https://export.arxiv.org/api/query
```

arXiv responses are Atom XML, not JSON. Preserve raw response text, content type, payload hash, request URL/parameters, and parsed page metadata. Use `search_query`, `id_list`, `start`, `max_results`, `sortBy`, and `sortOrder` according to the provider’s documented API behavior.

Use source-specific query translation rather than passing Semantic Scholar syntax through unchanged. The translation may use deterministic title/abstract/all-field forms and configured categories, but it must preserve the originating canonical query ID.

Do not assume a returned list is perfectly date-sorted. Never stop pagination merely because one entry appears older than the configured time window; filter dates record by record and stop only at explicit page/budget limits.

Environment variables:

```text
ARXIV_API_BASE_URL=https://export.arxiv.org/api/query
```

### OpenAlex contract

Use OpenAlex’s Works API for broad coverage and metadata enrichment.

Initial endpoint:

```text
GET https://api.openalex.org/works
```

Use `search`, deterministic filters, `select`, `per-page`, and cursor pagination. For deep pagination, start with `cursor=*` and use the returned `next_cursor`; do not emulate cursors by incrementing page numbers. Preserve response metadata such as `next_cursor`, count, and response latency.

OpenAlex abstracts can be supplied as an inverted index. Reconstruct them deterministically by sorting token positions. Preserve the original inverted-index payload reference so reconstruction can be audited.

Environment variables:

```text
OPENALEX_API_KEY
OPENALEX_BASE_URL=https://api.openalex.org
```

### Provider request policy

All enabled providers receive every canonical query under the same run policy. Providers may receive different **translated** request strings because their query syntaxes differ, but translation must be deterministic and recorded.

Use provider-specific limits and a shared global run budget:

```text
per-provider semaphore / token bucket
per-provider timeout
per-provider request interval
per-provider retry policy
per-provider cache TTL
run-level API-call cap
run-level candidate cap
```

Do not use one provider’s error as a reason to alter another provider’s query plan during the same run.

## Caching, Retry, and Resume Policy

Raw responses are cacheable acquisition artifacts, not paper records.

The cache key must include:

```text
source
endpoint
HTTP method
canonicalized request parameters
requested field set
provider query
policy version
```

Do not use a cache key based only on the query text; a source, endpoint, date filter, cursor, selected fields, or page can change the response.

Because arXiv returns Atom XML, the cache schema must support arbitrary response bodies. Do not store every response in a JSON-only column.

Recommended cache fields:

```text
cache_key
source
endpoint
request_json
response_body
content_type
status_code
payload_hash
created_at
expires_at
last_accessed_at
```

### Retry policy

- Respect `Retry-After` when the provider supplies it.
- Retry transient 429, 500, 502, 503, and 504 responses within a documented attempt budget.
- Treat invalid JSON/XML, malformed provider schema, 4xx validation errors, and unsupported query syntax as classified errors rather than generic failures.
- Use exponential backoff with deterministic jitter in baseline mode.
- Cache successful payloads with explicit TTLs.
- Cache known permanent request failures briefly only when it prevents repeated bad requests and clearly label them as negative cache entries.
- Checkpoint after every durable stage so a later failure does not require re-fetching successful provider pages.

A source failure should yield `partial_success` if other sources or other queries completed. Never silently drop a failed provider request.

## Baseline Query Generation

Query generation must be deterministic, source-independent at the canonical-plan stage, and source-specific only at translation time.

### Canonical query rules

1. Add `topic_overview` as one query.
2. Add each cleaned `research_questions` item as one query.
3. Add each cleaned `query_hints` item as one query.
4. Add one combined query using important terms from topic, questions, and hints.
5. Normalize and deduplicate case-insensitively.
6. Limit the final canonical list using `baseline.max_queries`.
7. Preserve the original text, normalized text, origin, and order in run artifacts.
8. Assign stable query IDs before provider translation.

Query cleaning rules:

```text
strip whitespace
collapse repeated whitespace
remove control characters
remove provider-unsafe unsupported syntax from canonical form
truncate extreme lengths
preserve meaningful quoted phrases
deduplicate case-insensitively
```

The combined query must be deterministic:

```text
lowercase text
Unicode normalize
remove punctuation
split on whitespace
remove built-in stopwords
count token frequency
sort by (-frequency, token)
keep top 8 to 12 tokens
join with spaces
```

Do not over-engineer NLP in the first version. No LLM query rewrite, no LLM synonym generation, no hidden auto-expansion.

### Provider-specific translation

Persist a `QueryPlan` that separates canonical intent from provider syntax:

```json
{
  "query_id": "q_004",
  "origin": "research_question",
  "canonical_text": "How have uncertainty estimates been used for explaining AI decisions?",
  "translations": {
    "semantic_scholar": {"query": "uncertainty estimates explaining AI decisions"},
    "arxiv": {"search_query": "all:uncertainty AND all:explainable AND all:AI"},
    "openalex": {"search": "uncertainty estimates explaining AI decisions"}
  }
}
```

Exact provider syntax may differ, but the mapping must be generated by transparent deterministic templates and versioned as `query_translation_v1`.

## Normalization and Validation

Provider normalizers convert raw provider records into a shared `PaperCandidate` shape. They do not perform relevance judgment.

Recommended normalizer modules:

```text
normalizers/
  semantic_scholar.py
  arxiv.py
  openalex.py
  common.py
```

Required normalized fields:

```text
source_record_id
source
title
abstract
authors
year
publication_date
venue
primary_url
pdf_url
citation_count
reference_count
influential_citation_count
publication_types
document_type
fields_of_study
open_access
identifiers
source_raw_ref
source_rank
```

Source-specific notes:

- Semantic Scholar: preserve `paperId`, `corpusId`, external IDs, citation fields, fields of study, and open-access PDF information.
- arXiv: parse Atom entries, arXiv ID/version, title, summary, author list, categories, `published`, `updated`, DOI when present, abstract URL, and PDF URL.
- OpenAlex: preserve work ID, DOI, title/display name, publication year/date, cited-by count, type, language, open-access locations, and retracted/paratext flags. Reconstruct `abstract_inverted_index` deterministically when available.

Validation must be conservative:

```text
missing title -> reject
blank title -> reject
malformed source record that cannot be repaired -> reject
missing abstract -> retain
missing PDF URL -> retain
missing DOI -> retain
missing year -> retain unless strict policy requires year
```

Every source-normalization failure must become a structured reject or provider error with a raw payload reference.

## Relevance Scoring

The baseline uses deterministic relevance scoring. The first implementation uses lexical and metadata features only.

Recommended formula:

```text
score =
  0.35 * title_keyword_overlap
+ 0.30 * abstract_keyword_overlap
+ 0.15 * query_phrase_match
+ 0.10 * recency_score
+ 0.05 * identifier_score
+ 0.05 * citation_score
```

All components must be normalized to `[0, 1]` and stored with the screening decision.

Do not add a substantial provider-prestige weight. Being found by three sources is evidence of metadata corroboration, not proof of topical relevance. Cross-source occurrence may be recorded as a separate confidence or completeness field, but it must not silently dominate relevance scoring.

Suggested behavior:

```text
title_keyword_overlap:
  overlap between canonical config/query tokens and normalized title tokens

abstract_keyword_overlap:
  overlap between canonical config/query tokens and normalized abstract tokens

query_phrase_match:
  exact or partial canonical phrase match in title or abstract

recency_score:
  1.0 inside configured timeline; documented decay outside;
  0.5 for missing year unless strict filtering is enabled

identifier_score:
  higher score for stable identifiers; do not penalize arXiv preprints for missing DOI

citation_score:
  log-normalized citation count; capped so older canonical papers do not dominate
```

Store the complete score record:

```json
{
  "score": 0.62,
  "score_components": {
    "title_keyword_overlap": 0.70,
    "abstract_keyword_overlap": 0.50,
    "query_phrase_match": 1.00,
    "recency_score": 1.00,
    "identifier_score": 0.80,
    "citation_score": 0.20
  },
  "method": "baseline_lexical_v1",
  "criteria_version": "baseline_lexical_v1"
}
```

A contributor must be able to inspect a rejected record and understand why it failed.

## Filtering Rules

Filtering must be deterministic and staged.

### Stage 0: metadata eligibility

Reject or defer only for explicit rules:

```text
missing_title
malformed_metadata
outside_timeline (only when strict timeline filtering is enabled)
retracted_work (when configured)
paratext_work (when configured)
unsupported_document_type (when configured)
```

### Stage 1: relevance decision

Reject when:

```text
score < min_relevance_score
duplicate_merged
identity_conflict_needs_review
```

Do not reject solely because:

```text
abstract is missing
PDF URL is missing
DOI is missing
a citation count is low
record is only present in one source
```

Every reject must be persisted with an allowed typed reason:

```text
missing_title
below_relevance_threshold
outside_timeline
unsupported_document_type
retracted_work
paratext_work
duplicate_merged
possible_duplicate
identity_conflict_needs_review
malformed_metadata
api_error
database_error
target_not_found
other
```

## Identity Resolution and Deduplication

Deduplication is central. The system must reconcile conflicts between records from the three providers and papers already in the local database.

Do not rely on title similarity alone.

### Identity priority

```text
1. normalized DOI
2. normalized arXiv ID (version stripped)
3. normalized OpenAlex Work ID
4. Semantic Scholar paperId
5. Semantic Scholar corpusId
6. PMID / ACL / MAG / other stable external IDs
7. normalized title + year + first-author fingerprint
8. fuzzy-title candidate + year tolerance + author overlap
```

Initial implementation must fully support levels 1 through 7. Level 8 must produce `possible_duplicate` or `identity_conflict_needs_review` unless a later, explicitly versioned policy enables auto-merge.

### Identifier normalization

```text
DOI:
  lowercase
  strip URL prefixes and leading "doi:"
  trim whitespace

arXiv:
  lowercase
  strip URL and "arxiv:" prefixes
  strip version suffix such as v1, v2
  trim whitespace

OpenAlex:
  normalize "https://openalex.org/W..." to uppercase W identifier

Semantic Scholar:
  preserve paperId string exactly after whitespace cleanup

Title:
  Unicode normalize
  lowercase
  remove punctuation
  collapse whitespace

Author:
  Unicode normalize
  lowercase
  collapse whitespace
  use first listed author when available
```

Stable paper key generation:

```text
doi:{doi_norm}
arxiv:{arxiv_id_norm}
openalex:{openalex_id_norm}
s2:{semantic_scholar_paper_id}
corpus:{corpus_id}
fp:{sha256(title_norm + year + first_author_norm)[:16]}
```

### Merge policy

When records match:

```text
do not create a new paper
update last_seen_at
append retrieval/source hits
union non-conflicting identifiers
fill missing URLs and PDF URLs
fill missing abstract from a non-empty source record
preserve field-level provenance
record citation observations with source and timestamp
record a typed merge event
```

Do not overwrite good metadata with null, lower-confidence, or conflicting metadata.

Field-specific rules:

```text
title:
  retain existing canonical title unless the new title is non-empty,
  strongly normalized-equivalent, and clearly richer; retain variants

abstract:
  retain longest non-empty abstract; retain source reference and variants

year/publication date:
  prefer complete ISO publication date; flag unresolved disagreement

authors:
  retain the richer ordered author list; keep alternatives in provenance

primary URL:
  prefer DOI landing URL, then a verified publisher/venue URL,
  then Semantic Scholar/OpenAlex/arXiv landing URL

PDF URL:
  fill missing; do not replace a working non-empty PDF URL with null

citation count:
  store observations by source/time; display a chosen current value only as a projection
```

Never merge two records solely because their titles are 90% similar. A false merge is worse than a retained duplicate because it silently destroys coverage and provenance.

Record every merge:

```json
{
  "run_id": "...",
  "existing_paper_key": "...",
  "candidate_id": "...",
  "matched_on": "doi",
  "source": "openalex",
  "query_id": "q_003",
  "created_at": "..."
}
```

## Local Database Design

Use SQLite as the local source of truth for baseline acquisition and curation state.

Recommended path:

```text
data/baseline/baseline.sqlite3
```

NDJSON and static JSON are export projections for project compatibility. They are not the primary database.

The canonical public exports remain:

```text
data/papers.ndjson
data/rejects.ndjson
data/run_history.ndjson
data/changelog.md
site/data/papers.json
site/data/rejects.json
site/data/run_history.json
site/data/system_status.json
site/data/survey_config.json
```

Recommended SQLite tables:

```sql
CREATE TABLE IF NOT EXISTS papers (
  paper_key TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  title_norm TEXT NOT NULL,
  title_fingerprint TEXT,
  abstract TEXT,
  year INTEGER,
  publication_date TEXT,
  venue TEXT,
  document_type TEXT,
  primary_url TEXT,
  pdf_url TEXT,
  open_access INTEGER,
  citation_count INTEGER,
  reference_count INTEGER,
  influential_citation_count INTEGER,
  fields_of_study_json TEXT,
  publication_types_json TEXT,
  authors_json TEXT,
  provenance_json TEXT NOT NULL,
  first_seen_run_id TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_identifiers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_key TEXT NOT NULL,
  id_type TEXT NOT NULL,
  id_normalized TEXT NOT NULL,
  source TEXT,
  first_seen_at TEXT NOT NULL,
  UNIQUE(id_type, id_normalized),
  FOREIGN KEY (paper_key) REFERENCES papers(paper_key)
);

CREATE TABLE IF NOT EXISTS retrieval_events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  architecture TEXT NOT NULL,
  paper_key TEXT,
  candidate_id TEXT,
  query_id TEXT NOT NULL,
  query_origin TEXT NOT NULL,
  canonical_query TEXT NOT NULL,
  provider_query TEXT NOT NULL,
  source TEXT NOT NULL,
  source_rank INTEGER,
  request_fingerprint TEXT NOT NULL,
  cache_status TEXT NOT NULL,
  raw_payload_hash TEXT,
  retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screening_decisions (
  decision_id TEXT PRIMARY KEY,
  paper_key TEXT,
  candidate_id TEXT,
  run_id TEXT NOT NULL,
  architecture TEXT NOT NULL,
  stage TEXT NOT NULL,
  decision TEXT NOT NULL,
  score REAL,
  criteria_version TEXT NOT NULL,
  decision_source TEXT NOT NULL,
  rationale TEXT,
  evidence_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS merge_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  existing_paper_key TEXT NOT NULL,
  candidate_id TEXT,
  matched_on TEXT NOT NULL,
  source TEXT,
  query_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_cache (
  cache_key TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  request_json TEXT NOT NULL,
  response_body BLOB,
  content_type TEXT,
  status_code INTEGER,
  payload_hash TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  last_accessed_at TEXT
);

CREATE TABLE IF NOT EXISTS query_state (
  query_id TEXT NOT NULL,
  source TEXT NOT NULL,
  query_norm TEXT NOT NULL,
  query_original TEXT NOT NULL,
  total_runs INTEGER DEFAULT 0,
  total_candidates INTEGER DEFAULT 0,
  total_accepted INTEGER DEFAULT 0,
  total_duplicates INTEGER DEFAULT 0,
  total_errors INTEGER DEFAULT 0,
  last_run_at TEXT,
  PRIMARY KEY(query_id, source)
);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  architecture TEXT NOT NULL,
  topic TEXT,
  config_hash TEXT NOT NULL,
  policy_versions_json TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  generated_queries_json TEXT,
  metrics_json TEXT,
  errors_json TEXT,
  manifest_json TEXT NOT NULL
);
```

Required indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_papers_title_fingerprint ON papers(title_fingerprint);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_identifiers_paper ON paper_identifiers(paper_key);
CREATE INDEX IF NOT EXISTS idx_retrieval_events_run ON retrieval_events(run_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_events_paper ON retrieval_events(paper_key);
CREATE INDEX IF NOT EXISTS idx_screening_decisions_run ON screening_decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_merge_events_run ON merge_events(run_id);
CREATE INDEX IF NOT EXISTS idx_cache_expiry ON api_cache(expires_at);
```

All database writes must use transactions. Export files with atomic writes:

```text
write file.tmp
flush and fsync when practical
rename file.tmp to final path
```

## Error Management and Robustness

The baseline must fail softly where possible.

A failure in one provider query must not kill the entire run. A failure normalizing one candidate must not kill the batch. A publisher failure must not corrupt already published output.

Define structured errors:

```text
BaselineError
ConfigError
ProviderError
SemanticScholarAPIError
ArxivAPIError
OpenAlexAPIError
RateLimitError
APIResponseError
CandidateValidationError
IdentityResolutionError
DatabaseWriteError
PublishError
ExportError
```

Error handling policy:

```text
config cannot be loaded:
  fail run

one provider request fails after retries:
  record provider/query-level error; continue other providers and queries

candidate cannot be normalized:
  write typed reject with malformed_metadata; continue

identifier conflict cannot be resolved:
  write possible_duplicate or identity_conflict_needs_review; do not auto-merge

database uniqueness conflict:
  retry identity resolution inside transaction; otherwise record error

site export fails:
  preserve database state; mark run partial_success or failure by severity
```

Final run statuses:

```text
success
partial_success
failure
```

Every run writes a final summary, even when partial or failed.

## Loop Engineering and Automation

Loop control must be a transparent state machine, not a hidden agent.

Recommended file:

```text
app/architectures/baseline/loop_control.py
```

Rules may alter future runs only through documented configuration state and a versioned policy. In frozen-corpus or architecture-comparison mode, query plans and provider policies must remain fixed.

Allowed deterministic cross-run rules:

```text
If a canonical query has zero accepted papers for 3 completed runs:
  lower priority only in exploratory mode; retain in comparison mode

If duplicate_rate exceeds configured threshold:
  reduce redundant page budget before altering queries

If accepted_count is below minimum:
  enable already-configured query hints and combined query;
  do not invent new semantic queries

If a provider is repeatedly rate-limited:
  lower only that provider’s request rate or pause it by explicit policy

If configured target papers are missing:
  execute deterministic lookup ladders across all capable providers
```

Do not make ad hoc policy changes inside `pipeline.py`. Log every loop decision as an event with `loop_policy_version`.

## Accuracy and Target Paper Detection

The baseline must evaluate whether it found configured target papers.

Optional `target_papers` records:

```json
{
  "title": "Attention Is All You Need",
  "doi": "10.xxxx/xxxxx",
  "semantic_scholar_id": null,
  "arxiv_id": null,
  "openalex_id": null,
  "must_find": true
}
```

Detection order:

```text
1. normalized DOI through local identifiers and provider lookups
2. Semantic Scholar paperId
3. arXiv ID
4. OpenAlex work ID
5. exact normalized title match
6. provider-specific exact/quoted title query
7. fuzzy title candidate with year and author evidence
```

Target check output:

```json
{
  "target_title": "...",
  "must_find": true,
  "found": true,
  "found_by": "openalex_doi_lookup",
  "paper_key": "...",
  "sources_found": ["semantic_scholar", "openalex"],
  "was_accepted": true,
  "best_rank_position": 3,
  "rejection_reason": null
}
```

Run history must include:

```text
target_total
target_found
target_accepted
target_missed
target_rejected
```

## Efficiency Requirements

Correctness, traceability, and deterministic behavior matter more than micro-optimization. Once those are intact, optimize acquisition where it is safe.

Required mechanisms:

```text
deduplicate canonical queries
translate once per provider per query
cache raw provider responses with TTL
run independent provider fetches concurrently
apply per-provider rate limits and request intervals
use cursor pagination for OpenAlex
use start/max-results paging for arXiv
use bounded pagination for all providers
batch database writes
use SQLite indexes
avoid repeated NDJSON scans when SQLite is available
export site files once at end of run
use exact identifiers before fingerprints or fuzzy comparisons
```

Do not introduce unbounded concurrency. Provider concurrency should reduce wall-clock time without violating provider-specific request policy.

Metrics to record at run, provider, and query level:

```text
runtime_seconds
api_call_count
api_call_count_by_source
cache_hit_count
cache_miss_count
cache_hit_rate_by_source
raw_candidate_count
raw_candidate_count_by_source
normalized_candidate_count
unique_candidate_count
accepted_count
rejected_count
duplicate_count
merge_count
possible_duplicate_count
error_count
retry_count
provider_latency_ms
avg_api_latency_ms
db_write_time_ms
publish_time_ms
source_coverage
cross_source_overlap
target_paper_found_rate
stability_across_replays
```

## Recommended File Structure

Implement baseline-specific code under:

```text
app/architectures/baseline/
  __init__.py
  pipeline.py
  query_builder.py
  query_translation.py
  normalizer.py
  validator.py
  identity.py
  deduper.py
  scorer.py
  filters.py
  db.py
  publisher.py
  loop_control.py
  target_check.py
  metrics.py
  errors.py
  models.py
  constants.py
  providers/
    __init__.py
    base.py
    semantic_scholar.py
    arxiv.py
    openalex.py
    cache.py
    rate_limit.py
```

Responsibilities:

```text
pipeline.py:
  owns run orchestration, checkpoints, and final structured result

query_builder.py:
  builds source-independent deterministic canonical queries

query_translation.py:
  produces deterministic provider-specific request translations

providers/*:
  provider API calls, pagination, raw response cache, retry policy, source parsing boundary

normalizer.py:
  converts parsed provider records into shared candidate shape

validator.py:
  validates required fields and repairs minor metadata issues

identity.py:
  normalizes identifiers and creates stable canonical keys

deduper.py:
  resolves candidate-candidate and candidate-database duplicates; emits merge/conflict events

scorer.py:
  applies deterministic lexical and metadata relevance scoring

filters.py:
  applies eligibility, threshold, timeline, and duplicate decisions

db.py:
  owns schema, migrations, transactions, upserts, and event persistence

publisher.py:
  exports SQLite canonical state to NDJSON and site/data JSON atomically

loop_control.py:
  implements versioned deterministic cross-run feedback rules

target_check.py:
  checks configured target papers across local state and providers

metrics.py:
  builds run, query, provider, and comparison metrics
```

Shared architecture-neutral code remains under:

```text
app/state/
  schemas.py
  store.py
```

Modify shared schemas only when necessary for compatibility. Do not make shared schemas baseline-specific.

## Reserved Structure for Agent Comparison

Keep internal artifacts separated by architecture, while retaining compatible public exports.

```text
data/
  papers.ndjson
  rejects.ndjson
  run_history.ndjson
  changelog.md
  system_status.json
  survey_config.json

  baseline/
    baseline.sqlite3
    run_artifacts/
      {run_id}/
        run_manifest.json
        canonical_query_plan.json
        provider_query_plan.json
        provider_results/
          semantic_scholar.json
          arxiv.json
          openalex.json
        normalized_candidates.json
        dedupe_results.json
        screening_decisions.json
        accepted_candidates.json
        rejected_candidates.json
        merge_events.json
        target_check.json
        metrics.json
        errors.json
        final_report.json

  single_agent/
    run_artifacts/
      {run_id}/
        crawler_report.json
        verifier_report.json
        builder_report.json
        final_report.json

  multi_agent/
    run_artifacts/
      {run_id}/
        central_report.json
        crawler_report.json
        verifier_report.json
        web_builder_report.json
        final_report.json

  comparison/
    frozen_corpora/
      {corpus_id}/
        manifest.json
        papers.ndjson
    runs/
      {comparison_id}.json
    metrics/
      architecture_summary.json
      baseline_vs_single_agent.json
      baseline_vs_multi_agent.json
      single_vs_multi_agent.json
```

A frozen corpus is a normalized, deduplicated snapshot supplied identically to multiple architectures. It is required to separate retrieval quality from screening and synthesis quality.

## Comparison Interface

All architectures should return comparable result objects.

A baseline result should include:

```json
{
  "run_id": "...",
  "architecture": "baseline",
  "success": true,
  "status": "success",
  "topic": "...",
  "started_at": "...",
  "finished_at": "...",
  "query_plan": [],
  "acquisition_result": {
    "sources": {
      "semantic_scholar": {"api_calls": 0, "raw_candidates": 0, "errors": []},
      "arxiv": {"api_calls": 0, "raw_candidates": 0, "errors": []},
      "openalex": {"api_calls": 0, "raw_candidates": 0, "errors": []}
    },
    "cache_hits": 0,
    "cache_misses": 0
  },
  "verification_result": {
    "method": "baseline_lexical_v1",
    "scored_candidates": 0,
    "accepted": 0,
    "rejected": 0
  },
  "dedupe_result": {
    "duplicates": 0,
    "merged": 0,
    "possible_duplicates": 0,
    "new_papers": 0,
    "updated_papers": 0
  },
  "target_check": {
    "target_total": 0,
    "target_found": 0,
    "target_accepted": 0,
    "target_missed": 0
  },
  "build_result": {
    "papers_ndjson_written": true,
    "site_data_written": true
  },
  "metrics": {},
  "summary": "Deterministic multi-source baseline run completed."
}
```

If the existing `ManagerRunResult` cannot hold this structure, extend it carefully and preserve compatibility with single-agent and multi-agent outputs.

## Evaluation Design

Use two complementary evaluation modes.

### Frozen-corpus comparison

Build one normalized, deduplicated corpus snapshot. Supply the same snapshot, acceptance criteria, and evaluation set to baseline, single-agent, and multi-agent paths.

This isolates:

```text
screening accuracy
organization
provenance behavior
evidence extraction
synthesis quality
```

from retrieval variance.

### End-to-end retrieval comparison

Run each architecture from the same config and time window. Record:

```text
source coverage
query count and query origins
provider request counts
raw candidates
unique candidates
cross-source overlap
deduplication and merge behavior
accepted records
runtime
cache hits
retries
failures
target-paper recall
```

Do not evaluate systems solely by final prose quality. A well-written survey that cannot reproduce inclusion, citations, and run state is not a credible research workflow.

## Integration Points

Update CLI architecture selection so this works:

```bash
python -m app.run --architecture baseline --dry-run
```

Likely files to inspect and modify:

```text
app/run.py
app/manager.py
app/state/schemas.py
app/config.py
pyproject.toml
```

Expected manager behavior:

```text
if architecture == "baseline":
  call app.architectures.baseline.pipeline.run_baseline(...)
elif architecture == "single-agent":
  keep existing behavior
elif architecture == "multi-agent":
  keep existing behavior
else:
  raise clear validation error
```

Do not duplicate CLI parsing logic inside the baseline package.

## Publishing Contract

The baseline must preserve the existing static-website contract.

Publish to:

```text
site/data/papers.json
site/data/run_history.json
site/data/rejects.json
site/data/changelog.md
site/data/system_status.json
site/data/survey_config.json
```

The site should work without a frontend rewrite. Frontend changes, if necessary, must be minimal and backward-compatible.

Paper provenance must expose source and architecture history:

```json
{
  "provenance": {
    "architectures_seen": ["baseline"],
    "sources_seen": ["semantic_scholar", "arxiv", "openalex"],
    "first_seen_by": "baseline",
    "last_seen_by": "baseline",
    "source_hits": [],
    "field_sources": {}
  }
}
```

## Data Style and Schema Principles

Use explicit fields. Avoid vague blobs unless preserving raw provider payloads.

Good:

```json
{
  "reason": "below_relevance_threshold",
  "score": 0.21,
  "threshold": 0.30,
  "criteria_version": "baseline_lexical_v1"
}
```

Bad:

```json
{
  "notes": "not good"
}
```

All timestamps are ISO 8601 strings.

Architecture values:

```text
baseline
single-agent
multi-agent
```

Source values:

```text
semantic_scholar
arxiv
openalex
manual
```

## Coding Style

Use clear, boring Python.

Prefer simple modules and explicit functions over clever abstractions. Use type hints for public functions. Use dataclasses or Pydantic models for structured records. Keep functions small and single-purpose.

Avoid hidden global state. Avoid broad `except Exception` unless re-raising or recording a typed error. Avoid silent failures. Avoid heavy dependencies unless they materially improve reliability.

Use a thin SQLite helper rather than an ORM for the first version.

Use async I/O for concurrent provider fetching only. Keep deterministic transforms, scoring, identity resolution, and database transactions synchronous and explicit. Do not introduce parallel database writers.

Use deterministic sorting before writing output. Use stable IDs. Use atomic file writes.

## Logging and Status

The baseline must produce readable logs and machine-readable status.

Update:

```text
data/system_status.json
```

Suggested statuses:

```text
idle
loading_config
building_queries
translating_provider_queries
fetching_sources
normalizing
deduplicating
scoring
filtering
persisting
publishing
finished
partial_success
failed
```

Status JSON example:

```json
{
  "architecture": "baseline",
  "status": "fetching_sources",
  "run_id": "...",
  "updated_at": "...",
  "message": "Fetching query q_002 from enabled providers.",
  "progress": {
    "current_query_index": 2,
    "total_queries": 8,
    "provider_states": {
      "semantic_scholar": "success",
      "arxiv": "running",
      "openalex": "cache_hit"
    }
  }
}
```

Do not make status updates depend on the frontend.

## Testing Requirements

Add deterministic tests for core logic and provider boundaries.

Recommended structure:

```text
tests/
  baseline/
    test_query_builder.py
    test_query_translation.py
    test_semantic_scholar_provider.py
    test_arxiv_provider.py
    test_openalex_provider.py
    test_normalizer.py
    test_identity.py
    test_deduper.py
    test_scorer.py
    test_filters.py
    test_db.py
    test_publisher.py
    test_pipeline_replay.py
```

Minimum tests:

```text
canonical query generation is deterministic
provider query translation is deterministic
same fixtures yield identical run artifacts
Semantic Scholar JSON fixture normalizes correctly
arXiv Atom XML fixture normalizes correctly
OpenAlex inverted-index abstract reconstructs correctly
cursor pagination is persisted for OpenAlex
arXiv date filtering does not prematurely stop on one old record
duplicate DOI resolves to one paper key
duplicate arXiv ID resolves to one paper key
OpenAlex and Semantic Scholar IDs merge through shared DOI
same title/year/author fingerprint resolves consistently
identifier conflict is not silently auto-merged
missing title is rejected
below-threshold score is rejected
inside-timeline paper is accepted when score passes
outside-timeline paper is rejected when strict filtering is enabled
one provider failure produces partial_success when others succeed
cache key differs when source or pagination cursor differs
database upsert does not duplicate existing paper
publisher writes valid deterministic JSON
```

Use fixture responses. Unit tests must not call live APIs. Live integration tests should be explicitly marked and skipped by default.

## Dry Run Semantics

`--dry-run` must prevent git commit and push behavior.

If existing project semantics permit dry-run to write local data and site files, preserve that behavior. Do not invent a different meaning of dry run without an explicit project decision.

If stricter behavior is required, introduce a separate flag:

```bash
--no-write
```

## Git Behavior

The baseline must not commit or push unless the existing CLI explicitly requests it.

Respect existing flags:

```text
--commit
--push
```

Never auto-push. Never hide generated files.

## Implementation Phases

### Phase 1: Baseline skeleton and contracts

Create the baseline package, shared result types, run manifest, database migration helper, and manager wiring.

Expected result:

```bash
python -m app.run --architecture baseline --dry-run
```

returns a structured placeholder result without API calls.

### Phase 2: Canonical query plan and provider abstraction

Implement deterministic query generation, provider interfaces, provider configuration, cache interface, and fixture tests.

Expected result:

```text
canonical and provider-translated queries are saved
providers can be invoked through one orchestrated interface
```

### Phase 3: Three provider clients

Implement Semantic Scholar, arXiv, and OpenAlex retrieval with source-specific pagination, retries, deterministic jitter, cache policy, and raw payload persistence.

Expected result:

```text
three-source fetch works concurrently
source failures are isolated and visible
raw JSON/XML payloads are cacheable and replayable
```

### Phase 4: Normalization, validation, identity, and deduplication

Normalize all provider responses, validate candidates, resolve identifiers, and implement conservative merge/conflict policy.

Expected result:

```text
candidate records have stable keys
bad records are rejected with typed reasons
cross-source duplicates merge with source provenance
possible duplicates are flagged rather than silently merged
```

### Phase 5: SQLite persistence and scoring

Implement transactions, retrieval events, screening decisions, deterministic lexical scoring, filters, query state, and target checks.

Expected result:

```text
new papers are inserted
existing papers are enriched
score components are stored
accepted and rejected records are explainable
```

### Phase 6: Publishing and run status

Export canonical data to NDJSON and static JSON; update changelog, run history, system status, and artifact directory.

Expected result:

```text
existing site reads baseline output
provider provenance is visible
run history is complete
```

### Phase 7: Evaluation and agent comparison

Add frozen corpus generation, end-to-end comparison artifacts, and cross-architecture metrics.

Expected result:

```text
baseline runs can be compared fairly against single-agent and multi-agent runs
retrieval and curation are evaluated separately
```

## Definition of Done

The baseline implementation is complete when:

```bash
python -m app.run --architecture baseline --dry-run
```

can:

```text
read data/survey_config.json
build deterministic canonical queries
translate them for Semantic Scholar, arXiv, and OpenAlex
fetch all enabled providers with bounded concurrency
cache raw JSON/XML provider responses
normalize returned records into a shared schema
resolve identity and deduplicate across providers and local state
score candidates without LLMs
accept/reject candidates deterministically
persist accepted papers, rejects, retrieval events, screening decisions, and merge events
update run history and system status
publish site/data JSON atomically
return a structured manager result
preserve single-agent and multi-agent behavior
```

It must also report enough metrics for comparison:

```text
accepted paper count
rejected candidate count
duplicate and possible-duplicate rate
merge count
target-paper found rate
runtime
API call count by source
cache hit rate by source
retry and error rates
source coverage and overlap
stability across cache-backed repeated runs
```

## What Not To Do

Do not replace existing agent architectures.

Do not move existing single-agent or multi-agent files unless necessary.

Do not make the baseline depend on LM Studio or any LLM endpoint.

Do not create a standalone CLI that bypasses `app.run`.

Do not hard-code one research topic.

Do not treat any provider search as full-text search.

Do not treat Semantic Scholar syntax as arXiv or OpenAlex syntax.

Do not dynamically choose sources based on unlogged model-like heuristics.

Do not silently discard provider failures, duplicates, or identity conflicts.

Do not overwrite good metadata with null metadata.

Do not auto-merge on title similarity alone.

Do not let an agent overwrite baseline or human screening decisions.

Do not rewrite the frontend unless required.

Do not introduce unnecessary dependencies or unbounded concurrency.

## Practical Implementation Notes for Claude Code

When editing this project:

1. Inspect existing schemas and manager behavior before creating new models.
2. Preserve backward compatibility with existing agent runs.
3. Add baseline files under `app/architectures/baseline/`.
4. Keep provider implementations isolated under `providers/`.
5. Implement the three sources through one deterministic provider contract.
6. Use SQLite for authoritative baseline state; export to existing NDJSON and site JSON.
7. Treat raw provider payloads, retrieval events, screening decisions, and merge events as first-class artifacts.
8. Keep all deterministic policies documented in module docstrings or constants.
9. Add unit fixtures for JSON and Atom XML before relying on live APIs.
10. Prefer small, reviewable patch sets and run the existing commands for all three architectures after changes.

The baseline should be strong, transparent, reproducible, and boring. The agents can be complex; any measured improvement from them must be earned rather than assumed.
