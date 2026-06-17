# CLAUDE.md

## Project Identity

This repository is **Dynamic-LR**, a dynamic literature retrieval and survey-management system. The long-term purpose is to compare different automation architectures for literature survey workflows.

The project currently contains LLM-based agentic architectures. The new work in this repository is to implement a strong, deterministic, non-LLM baseline pipeline for literature retrieval and local database management.

The baseline is not a toy control. It should be a competent scripted pipeline that can be fairly compared against the existing LLM-based agent architectures.

The baseline must retrieve paper metadata through the Semantic Scholar API, normalize results into the project’s shared paper schema, detect duplicates and conflicts, score candidate relevance deterministically, persist accepted and rejected records, maintain local database state, and publish output to the existing static site data files.

The baseline must not use an LLM for planning, query expansion, relevance judgment, summarization, tool selection, publishing decisions, or error recovery decisions.

## Core Research Question

The engineering goal supports this research question:

> Does LLM-based sequential decision-making improve a literature-survey workflow compared with a strong deterministic API-driven baseline?

Everything implemented for the baseline should make this comparison possible.

This means the baseline and the agentic pipelines should share as much infrastructure as practical:

- same survey configuration file
- same candidate paper schema
- same accepted paper schema
- same run history schema
- same site output format
- same evaluation metrics
- comparable run summaries
- architecture-specific artifact directories

## Current Project Context

The existing project has three intended architectures:

```text
baseline
single-agent
multi-agent
```

The existing LLM-based architectures should remain intact. Do not break or rewrite them while implementing the baseline.

The baseline should be selectable through the existing CLI:

```bash
python -m app.run --architecture baseline --dry-run
```

The existing architecture commands must continue to work:

```bash
python -m app.run --architecture single-agent --dry-run
python -m app.run --architecture multi-agent --dry-run
```

The baseline must integrate into the existing manager layer instead of becoming a disconnected script.

## Non-Negotiable Baseline Rules

The baseline must be deterministic.

For the same config, same database state, same API responses, and same runtime settings, the baseline should produce the same decisions.

The baseline must not call any LLM chat, completion, instruction-following, or agent endpoint.

The baseline must not use an LLM for:

```text
planning
search-query reasoning
query rewriting
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

A non-LLM embedding model may be added later only if it is used as a fixed scoring function. The initial implementation should avoid embeddings and use lexical scoring, metadata scoring, and deterministic filters.

The first baseline implementation should use the Semantic Scholar API only. Keep the code modular so arXiv and OpenAlex can be added later, but do not implement multi-source crawling unless explicitly requested.

## Intended Baseline Workflow

The baseline pipeline should follow this high-level workflow:

```text
read survey config
  -> build deterministic search queries
  -> call Semantic Scholar API
  -> cache raw API responses
  -> normalize source results
  -> validate candidate records
  -> resolve identity and deduplicate
  -> compare candidates against local database
  -> score relevance deterministically
  -> apply deterministic filters
  -> persist accepted papers
  -> persist rejected candidates
  -> persist merge/conflict events
  -> update run history
  -> update system status
  -> export NDJSON / JSON files
  -> publish static site data
  -> return structured ManagerRunResult
```

The baseline should be designed as an automated loop, not as a one-off search script. Every run should produce structured artifacts that improve future runs: run history, query performance, duplicate rate, API error logs, target-paper checks, and database update records.

## Survey Config Contract

The baseline must read from:

```text
data/survey_config.json
```

The baseline should use these fields:

```text
topic_overview
research_questions
question_context
query_hints
timeline_from_year
timeline_to_year
min_relevance_score
```

The baseline should also support optional future fields without failing:

```text
target_papers
semantic_scholar
baseline
evaluation
```

Recommended extended config shape:

```json
{
  "topic_overview": "Explainable AI",
  "question_mode": 3,
  "research_questions": [
    "What methods have been used to make AI explainable?",
    "How uncertainty estimates have been used for explaining AI decisions?",
    "What methods have been used to make AI interpretable?"
  ],
  "question_context": "Prioritize practical methods, rigorous evaluation, and reproducible experimental settings.",
  "query_hints": [
    "AI explanation",
    "Uncertainty Quantification",
    "human AI interaction"
  ],
  "timeline_from_year": 2024,
  "timeline_to_year": 2026,
  "min_relevance_score": 0.3,
  "target_papers": [
    {
      "title": "Example Paper Title",
      "doi": null,
      "semantic_scholar_id": null,
      "must_find": false
    }
  ],
  "baseline": {
    "max_queries": 12,
    "max_results_per_query": 50,
    "use_bulk_search": false,
    "enable_raw_cache": true,
    "enable_sqlite": true,
    "min_title_tokens": 2,
    "require_title": true,
    "require_year": false,
    "require_abstract": false
  },
  "semantic_scholar": {
    "fields": [
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
      "isOpenAccess"
    ]
  }
}
```

The code must not assume these optional fields exist. Use safe defaults.

## Semantic Scholar API Contract

The baseline should use the Semantic Scholar Graph API for paper search.

Initial endpoint:

```text
GET https://api.semanticscholar.org/graph/v1/paper/search
```

Future optional endpoint:

```text
GET https://api.semanticscholar.org/graph/v1/paper/search/bulk
```

Paper lookup endpoint for target-paper checks and identifier resolution:

```text
GET https://api.semanticscholar.org/graph/v1/paper/{paper_id}
```

Important API behavior:

Semantic Scholar search is metadata-oriented. Standard paper search primarily matches query terms against paper titles and abstracts, not full text. Do not design the baseline as if it has full-text access.

The API returns metadata such as title, abstract, authors, year, DOI, arXiv ID, Semantic Scholar paperId, citation counts, venue, publication date, fields of study, open-access PDF metadata, and external identifiers when requested through the `fields` parameter.

Default requested fields:

```text
paperId
corpusId
title
abstract
year
authors
url
openAccessPdf
externalIds
citationCount
referenceCount
influentialCitationCount
publicationTypes
publicationDate
venue
fieldsOfStudy
isOpenAccess
```

The client must support:

```text
timeout
retry
exponential backoff
429 rate-limit handling
5xx retry
invalid JSON handling
request logging
raw response caching
API key through environment variable
safe operation without API key
```

Recommended environment variables:

```text
SEMANTIC_SCHOLAR_API_KEY
SEMANTIC_SCHOLAR_BASE_URL=https://api.semanticscholar.org/graph/v1
REQUEST_TIMEOUT_S=30
MAX_CANDIDATES_PER_RUN=200
TOP_K_PER_QUERY=50
BASELINE_SQLITE_PATH=data/baseline/baseline.sqlite3
DATA_DIR=data
SITE_DIR=site
```

## Baseline Query Generation

Query generation must be deterministic.

Do not ask an LLM to rewrite, rank, expand, or choose queries.

Use fixed rules:

1. Add `topic_overview` as one query.
2. Add each `research_questions` item as one query after cleaning.
3. Add each `query_hints` item as one query.
4. Add one combined query using important terms from `topic_overview`, `research_questions`, and `query_hints`.
5. Remove duplicates after normalization.
6. Limit the final query list using `baseline.max_queries`.
7. Preserve the original query string in run artifacts.

Query cleaning rules:

```text
strip whitespace
collapse repeated whitespace
remove control characters
remove unsupported search syntax
truncate very long queries
keep meaningful quoted phrases
deduplicate case-insensitively
```

Do not over-engineer NLP in the first version. Basic tokenization is sufficient.

A useful first implementation:

```text
query_1 = topic_overview
query_2..n = research_questions
query_n..m = query_hints
query_combined = top non-stopword terms from topic + questions + hints
```

The combined query should be deterministic. For example:

```text
lowercase text
remove punctuation
split on whitespace
remove built-in stopwords
count token frequency
keep top 8 to 12 tokens
join with spaces
```

Do not use external NLP packages unless necessary. Keep dependencies minimal.

## Relevance Scoring

The baseline must use deterministic relevance scoring.

The first implementation should use lexical and metadata features only.

Recommended scoring formula:

```text
score =
  0.35 * title_keyword_overlap
+ 0.30 * abstract_keyword_overlap
+ 0.15 * query_phrase_match
+ 0.10 * recency_score
+ 0.05 * identifier_score
+ 0.05 * citation_score
```

All score components must be normalized to `[0, 1]`.

Suggested component behavior:

```text
title_keyword_overlap:
  overlap between config/query tokens and normalized title tokens

abstract_keyword_overlap:
  overlap between config/query tokens and normalized abstract tokens

query_phrase_match:
  1.0 if an exact query phrase appears in title or abstract
  0.5 if partial phrase appears
  0.0 otherwise

recency_score:
  1.0 if year is inside configured timeline
  decay if outside timeline
  0.5 if year is missing

identifier_score:
  higher score if DOI, arXiv ID, or Semantic Scholar paperId exists

citation_score:
  log-normalized citationCount
  cap extreme citation counts
```

The score block must be stored with the candidate or rejected record:

```json
{
  "score": 0.62,
  "score_components": {
    "title_keyword_overlap": 0.7,
    "abstract_keyword_overlap": 0.5,
    "query_phrase_match": 1.0,
    "recency_score": 1.0,
    "identifier_score": 0.8,
    "citation_score": 0.2
  },
  "method": "baseline_lexical_v1"
}
```

The scoring method must be transparent. A contributor should be able to inspect a rejected record and understand why it failed.

## Filtering Rules

Filtering must be deterministic.

Reject a candidate if:

```text
title is missing or blank
score < min_relevance_score
year is outside timeline, if strict timeline filtering is enabled
metadata is malformed beyond repair
candidate is a duplicate that has already been merged
```

Do not reject solely because abstract is missing. Many useful records may not expose abstracts.

Do not reject solely because PDF URL is missing. Semantic Scholar metadata may still identify the paper correctly.

Every rejected candidate must be written to rejects with a reason.

Allowed reject reasons:

```text
missing_title
below_relevance_threshold
outside_timeline
duplicate_merged
malformed_metadata
api_error
database_error
target_not_found
other
```

Each reject record should contain:

```json
{
  "candidate_id": "...",
  "run_id": "...",
  "architecture": "baseline",
  "source": "semantic_scholar",
  "query": "...",
  "title": "...",
  "year": 2024,
  "reason": "below_relevance_threshold",
  "score": 0.18,
  "evidence": {
    "threshold": 0.3,
    "matched_terms": ["..."],
    "missing_terms": ["..."]
  },
  "raw_ref": "optional cache key or raw response hash",
  "created_at": "..."
}
```

## Identity Resolution and Deduplication

Deduplication is a central requirement.

The baseline must handle conflicts between newly retrieved literature and papers already in the local database.

Do not rely on title alone.

Use this identity priority:

```text
1. normalized DOI
2. normalized arXiv ID
3. Semantic Scholar paperId
4. CorpusId
5. PMID / ACL / MAG / other external IDs when present
6. normalized title + year + first author fingerprint
7. fuzzy title match + year tolerance + author overlap
```

Initial version can implement levels 1 through 6. Fuzzy matching can be added after the stable deterministic path is working.

Normalization rules:

```text
DOI:
  lowercase
  strip URL prefixes
  strip doi.org prefix
  strip leading "doi:"
  trim whitespace

arXiv:
  lowercase
  strip "arxiv:"
  strip version suffix such as v1, v2
  trim whitespace

title:
  lowercase
  unicode normalize
  remove punctuation
  collapse whitespace
  remove leading/trailing spaces

author:
  lowercase
  collapse whitespace
  use first listed author when available
```

Stable paper ID generation:

```text
doi:{doi_norm}
arxiv:{arxiv_id_norm}
s2:{semantic_scholar_paper_id}
corpus:{corpus_id}
fp:{sha256(title_norm + year + first_author_norm)[:16]}
```

When a new candidate matches an existing paper:

```text
do not create a new paper
update last_seen_at
add source hit
merge missing identifiers
merge missing URLs
merge missing abstract if existing abstract is empty
preserve the richer title if the existing title is weak
update citation counts as newly observed metadata
record a merge event
```

Do not overwrite good metadata with null or lower-quality metadata.

Merging preference rules:

```text
title:
  keep existing unless new title is longer, non-empty, and highly similar

abstract:
  keep the longer non-empty abstract

year:
  keep existing if present
  fill missing year from new candidate

authors:
  keep richer author list

primary_url:
  prefer DOI landing page if available
  otherwise prefer Semantic Scholar URL
  otherwise keep existing non-empty URL

pdf_url:
  fill if missing
  do not overwrite an existing valid PDF URL with null

citationCount:
  update to latest observed value
  record observation time

source_hits:
  append
```

Record duplicate merges in a structured file or table:

```text
data/baseline/merge_events.ndjson
```

Each merge event should include:

```json
{
  "run_id": "...",
  "existing_paper_id": "...",
  "candidate_id": "...",
  "matched_on": "doi",
  "source": "semantic_scholar",
  "query": "...",
  "timestamp": "..."
}
```

## Local Database Design

Use SQLite as the local source of truth for the baseline.

NDJSON files are useful for project compatibility and static site output, but SQLite is better for identity resolution, conflict detection, indexing, and long-term local database management.

Recommended database path:

```text
data/baseline/baseline.sqlite3
```

The baseline should still export to the existing project files:

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
  paper_id TEXT PRIMARY KEY,
  doi_norm TEXT UNIQUE,
  arxiv_id_norm TEXT UNIQUE,
  semantic_scholar_id TEXT UNIQUE,
  corpus_id TEXT UNIQUE,
  title TEXT NOT NULL,
  title_norm TEXT,
  title_fingerprint TEXT,
  abstract TEXT,
  year INTEGER,
  publication_date TEXT,
  venue TEXT,
  primary_url TEXT,
  pdf_url TEXT,
  citation_count INTEGER,
  reference_count INTEGER,
  influential_citation_count INTEGER,
  fields_of_study_json TEXT,
  publication_types_json TEXT,
  authors_json TEXT,
  external_ids_json TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_hits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  architecture TEXT NOT NULL,
  source TEXT NOT NULL,
  query TEXT,
  rank INTEGER,
  retrieved_at TEXT NOT NULL,
  raw_json_hash TEXT,
  FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

CREATE TABLE IF NOT EXISTS rejects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id TEXT,
  run_id TEXT NOT NULL,
  architecture TEXT NOT NULL,
  source TEXT,
  query TEXT,
  title TEXT,
  year INTEGER,
  reason TEXT NOT NULL,
  score REAL,
  evidence_json TEXT,
  raw_json_hash TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS merge_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  existing_paper_id TEXT NOT NULL,
  candidate_id TEXT,
  matched_on TEXT NOT NULL,
  source TEXT,
  query TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  architecture TEXT NOT NULL,
  topic TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  success TEXT,
  generated_queries_json TEXT,
  metrics_json TEXT,
  errors_json TEXT,
  summary TEXT
);

CREATE TABLE IF NOT EXISTS api_cache (
  cache_key TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  request_json TEXT NOT NULL,
  response_json TEXT,
  status_code INTEGER,
  created_at TEXT NOT NULL,
  expires_at TEXT
);

CREATE TABLE IF NOT EXISTS query_state (
  query_norm TEXT PRIMARY KEY,
  query_original TEXT NOT NULL,
  total_runs INTEGER DEFAULT 0,
  total_candidates INTEGER DEFAULT 0,
  total_accepted INTEGER DEFAULT 0,
  total_duplicates INTEGER DEFAULT 0,
  total_errors INTEGER DEFAULT 0,
  last_run_at TEXT
);
```

Required indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_papers_title_fingerprint ON papers(title_fingerprint);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_source_hits_run ON source_hits(run_id);
CREATE INDEX IF NOT EXISTS idx_source_hits_paper ON source_hits(paper_id);
CREATE INDEX IF NOT EXISTS idx_rejects_run ON rejects(run_id);
CREATE INDEX IF NOT EXISTS idx_merge_events_run ON merge_events(run_id);
```

All database writes must use transactions.

Use atomic file writes when exporting files:

```text
write to file.tmp
fsync if practical
rename file.tmp to final path
```

## Error Management and Robustness

The baseline must fail softly where possible.

A failure in one query should not kill the entire run.

A failure in one candidate should not kill the entire run.

A publishing failure should be reported clearly and should not corrupt existing output files.

Define structured errors:

```text
BaselineError
ConfigError
SemanticScholarAPIError
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

Semantic Scholar query fails after retries:
  record query-level error
  continue next query

candidate cannot be normalized:
  write reject with reason malformed_metadata
  continue next candidate

database unique conflict:
  attempt identity merge
  if unresolved, write error and reject candidate

site export fails:
  mark run partial_success or failure depending on severity
```

The final run result should distinguish:

```text
success
partial_success
failure
```

Use `partial_success` when the run retrieved and processed some data but had recoverable errors.

Every run should write a final summary even when partially failed.

## Loop Engineering and Automation

The baseline should be designed as a repeatable automatic pipeline.

It should remember previous runs and adapt through fixed rules, not through LLM reasoning.

Allowed deterministic loop rules:

```text
If a query produces zero accepted papers for 3 consecutive runs:
  lower its priority in future runs

If duplicate_rate > 0.80:
  prefer newer publication date filters in future runs

If accepted_count < expected minimum:
  enable query_hints and combined query

If Semantic Scholar rate-limit errors are frequent:
  reduce request rate or disable concurrency

If target_papers are configured and not found:
  run deterministic fallback lookup:
    DOI lookup
    Semantic Scholar ID lookup
    exact title query
    quoted title query
    title keyword query
```

These rules should be implemented in a small loop-control module, not scattered across the pipeline.

Recommended file:

```text
app/architectures/baseline/loop_control.py
```

Do not build a hidden agent under the name of loop control. Loop control must be a transparent state machine with documented rules.

## Accuracy and Target Paper Detection

The baseline must support evaluation of whether it found desired papers.

Optional `target_papers` in config should support:

```json
{
  "title": "Attention Is All You Need",
  "doi": "10.xxxx/xxxxx",
  "semantic_scholar_id": null,
  "arxiv_id": null,
  "must_find": true
}
```

Detection order:

```text
1. DOI lookup
2. Semantic Scholar paperId lookup
3. arXiv ID lookup
4. exact normalized title match
5. quoted title search
6. fuzzy title match with year and author evidence
```

Target check output:

```json
{
  "target_title": "...",
  "must_find": true,
  "found": true,
  "found_by": "doi_lookup",
  "paper_id": "...",
  "was_accepted": true,
  "rank_position": 3,
  "rejection_reason": null
}
```

The run history should include target-paper metrics:

```text
target_total
target_found
target_accepted
target_missed
target_rejected
```

This is required to judge retrieval accuracy instead of merely counting accepted papers.

## Efficiency Requirements

The baseline should avoid unnecessary API calls and repeated processing.

Efficiency mechanisms:

```text
deduplicate generated queries
cache API responses
respect rate limits
batch database writes
use SQLite indexes
avoid repeated NDJSON scans when SQLite is available
export site files once at the end
use stable fingerprints to avoid repeated fuzzy comparisons
```

Metrics to record:

```text
runtime_seconds
api_call_count
cache_hit_count
cache_miss_count
raw_candidate_count
normalized_candidate_count
deduplicated_candidate_count
accepted_count
rejected_count
duplicate_count
merge_count
error_count
avg_api_latency_ms
db_write_time_ms
publish_time_ms
```

Do not optimize prematurely. Correctness, traceability, and deterministic behavior matter more than micro-optimization.

## Recommended File Structure

Implement baseline-specific code under:

```text
app/architectures/baseline/
  __init__.py
  pipeline.py
  query_builder.py
  semantic_scholar_client.py
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
```

Responsibilities:

```text
pipeline.py:
  Orchestrates the full baseline run.

query_builder.py:
  Builds deterministic queries from survey_config.json.

semantic_scholar_client.py:
  Calls Semantic Scholar API with retry, timeout, cache, and rate-limit behavior.

normalizer.py:
  Converts Semantic Scholar records into shared candidate shape.

validator.py:
  Validates required fields and repairs minor metadata issues.

identity.py:
  Normalizes DOI/arXiv/title/author identifiers and creates stable IDs.

deduper.py:
  Resolves candidate-candidate and candidate-database duplicates.

scorer.py:
  Applies deterministic lexical and metadata scoring.

filters.py:
  Applies threshold, timeline, missing metadata, and duplicate filters.

db.py:
  Owns SQLite schema, migrations, transactions, and upserts.

publisher.py:
  Exports SQLite/canonical state to NDJSON and site/data JSON.

loop_control.py:
  Maintains deterministic feedback-loop rules for repeated runs.

target_check.py:
  Checks whether configured target papers were found and accepted.

metrics.py:
  Builds run metrics and architecture-comparison metrics.

errors.py:
  Defines structured baseline exceptions.

models.py:
  Defines baseline-specific dataclasses or Pydantic models.

constants.py:
  Holds default Semantic Scholar fields, stopwords, thresholds, and filenames.
```

Shared code that should remain architecture-neutral:

```text
app/state/
  schemas.py
  store.py
```

Modify shared schemas only when needed for compatibility. Do not make shared schemas baseline-specific.

## Reserved Structure for Agent Comparison

Keep architecture-specific outputs separated.

Recommended artifact structure:

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
    raw_cache/
    run_artifacts/
      {run_id}/
        generated_queries.json
        raw_semantic_scholar_responses.json
        normalized_candidates.json
        scored_candidates.json
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
    runs/
      {comparison_id}.json
    metrics/
      architecture_summary.json
      baseline_vs_single_agent.json
      baseline_vs_multi_agent.json
      single_vs_multi_agent.json
```

Do not mix baseline internal artifacts with agent artifacts.

The canonical public project files remain shared:

```text
data/papers.ndjson
data/rejects.ndjson
data/run_history.ndjson
site/data/*.json
```

Architecture-specific artifacts are for debugging and evaluation.

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
  "generated_queries": [],
  "crawl_result": {
    "source": "semantic_scholar",
    "api_calls": 0,
    "raw_candidates": 0,
    "errors": []
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
  "summary": "Deterministic baseline run completed."
}
```

If the existing `ManagerRunResult` schema cannot hold this structure, extend it carefully. Do not break existing single-agent or multi-agent responses.

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

Do not duplicate CLI parsing logic inside the baseline folder.

## Publishing Contract

The baseline must preserve the existing static website contract.

Publish to:

```text
site/data/papers.json
site/data/run_history.json
site/data/rejects.json
site/data/changelog.md
site/data/system_status.json
site/data/survey_config.json
```

The site should work without a frontend rewrite.

If frontend changes are necessary, keep them minimal and backward-compatible.

Site data should include architecture labels so users can filter or inspect whether papers were added by baseline, single-agent, or multi-agent.

Recommended paper provenance field:

```json
{
  "provenance": {
    "architectures_seen": ["baseline"],
    "sources_seen": ["semantic_scholar"],
    "first_seen_by": "baseline",
    "last_seen_by": "baseline",
    "source_hits": []
  }
}
```

## Data Style and Schema Principles

Use explicit fields. Avoid vague blobs unless storing raw API responses.

Good:

```json
{
  "reason": "below_relevance_threshold",
  "score": 0.21,
  "threshold": 0.3
}
```

Bad:

```json
{
  "notes": "not good"
}
```

All timestamps should be ISO 8601 strings.

All architecture values should be one of:

```text
baseline
single-agent
multi-agent
```

All source values should be normalized:

```text
semantic_scholar
arxiv
openalex
manual
```

For the initial baseline, use only:

```text
semantic_scholar
```

## Coding Style

Use clear, boring Python.

Prefer simple modules and explicit functions over clever abstractions.

Use type hints for public functions.

Use dataclasses or Pydantic models for structured records.

Use small functions with single responsibility.

Avoid hidden global state.

Avoid broad `except Exception` unless re-raising or recording a structured error.

Avoid silent failures.

Avoid adding heavy dependencies unless necessary.

Do not introduce an ORM for the first version. Use `sqlite3` or a very thin database helper.

Do not introduce async unless rate limits and performance make it necessary. A reliable synchronous implementation is acceptable for the first version.

Use deterministic sorting before writing output files.

Use stable IDs.

Use atomic file writes.

## Logging and Status

The baseline should produce readable logs and machine-readable status.

Update:

```text
data/system_status.json
```

Suggested statuses:

```text
idle
loading_config
building_queries
querying_semantic_scholar
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

Status JSON should include:

```json
{
  "architecture": "baseline",
  "status": "querying_semantic_scholar",
  "run_id": "...",
  "updated_at": "...",
  "message": "Querying Semantic Scholar.",
  "progress": {
    "current_query_index": 2,
    "total_queries": 8
  }
}
```

Do not make status updates depend on the frontend.

## Testing Requirements

Add tests for deterministic core modules.

Recommended test structure:

```text
tests/
  baseline/
    test_query_builder.py
    test_identity.py
    test_deduper.py
    test_scorer.py
    test_filters.py
    test_normalizer.py
    test_db.py
    test_publisher.py
```

Minimum tests:

```text
query generation is deterministic
duplicate DOI resolves to same paper_id
duplicate arXiv ID resolves to same paper_id
same title/year/author fingerprint resolves to same paper_id
missing title is rejected
below-threshold score is rejected
inside-timeline paper is accepted when score passes
outside-timeline paper is rejected when strict timeline filtering is enabled
database upsert does not duplicate existing paper
publisher writes valid JSON
```

Use fixture responses for Semantic Scholar. Do not call live APIs in unit tests.

Live API tests should be optional and skipped by default.

## Dry Run Semantics

`--dry-run` should prevent git commit and push behavior.

However, if the existing project semantics allow dry-run to write local data and site files, preserve that behavior for consistency.

Do not invent a new meaning of dry-run unless the project owner requests it.

If a stricter dry-run is needed later, add a separate flag such as:

```bash
--no-write
```

## Git Behavior

The baseline should not commit or push unless the existing CLI explicitly asks it to do so.

Respect existing flags:

```text
--commit
--push
```

Never auto-push from baseline.

Never hide generated files from the user.

## Implementation Phases

### Phase 1: Baseline Skeleton

Create the baseline package and wire it into the manager.

Expected result:

```bash
python -m app.run --architecture baseline --dry-run
```

runs without calling Semantic Scholar yet and returns a structured placeholder result.

### Phase 2: Query Builder and Semantic Scholar Client

Implement deterministic query generation and Semantic Scholar search.

Expected result:

```text
generated queries are saved
raw API responses are cached
API errors are structured
```

### Phase 3: Normalization, Validation, and Identity

Convert Semantic Scholar records into candidate records.

Expected result:

```text
candidate records have stable IDs
bad records are rejected with reasons
DOI/arXiv/S2/title fingerprints are normalized
```

### Phase 4: SQLite Persistence and Deduplication

Implement local database, upsert, merge, and source-hit tracking.

Expected result:

```text
new papers are inserted
existing papers are updated
duplicates are merged
merge events are recorded
```

### Phase 5: Scoring and Filtering

Implement deterministic lexical relevance scoring.

Expected result:

```text
accepted and rejected candidates are separated
score components are stored
threshold behavior is explainable
```

### Phase 6: Publishing

Export canonical data to NDJSON and site JSON.

Expected result:

```text
existing site can read baseline output
run history is updated
changelog is updated
system_status is updated
```

### Phase 7: Evaluation and Agent Comparison

Add comparison artifacts.

Expected result:

```text
baseline runs can be compared against single-agent and multi-agent runs
shared metrics are emitted
architecture-specific artifacts remain separate
```

## Definition of Done

The baseline implementation is complete when:

```text
python -m app.run --architecture baseline --dry-run
```

can:

```text
read data/survey_config.json
build deterministic queries
call Semantic Scholar API
normalize returned papers
deduplicate against existing database
score candidates without LLMs
accept/reject candidates deterministically
write accepted papers
write rejected candidates
record duplicate merges
update run history
update system status
publish site/data JSON
return a structured manager result
preserve existing single-agent and multi-agent behavior
```

The baseline must also produce enough metrics to compare with agentic architectures:

```text
accepted paper count
rejected candidate count
duplicate rate
merge count
target-paper found rate
runtime
API call count
cache hit rate
error rate
source coverage
stability across repeated runs
```

## What Not To Do

Do not replace the existing agent architectures.

Do not move existing single-agent or multi-agent files unless necessary.

Do not make the baseline depend on LM Studio.

Do not call an LLM from baseline code.

Do not create a separate standalone CLI that bypasses `app.run`.

Do not hard-code one research topic.

Do not treat Semantic Scholar search as full-text search.

Do not silently discard duplicates without recording merge evidence.

Do not silently discard errors.

Do not overwrite good metadata with null metadata.

Do not rewrite the frontend unless required.

Do not introduce unnecessary dependencies.

## Practical Implementation Notes for Claude Code

When editing this project:

1. Inspect the existing schemas before creating new ones.
2. Preserve backward compatibility with existing agent runs.
3. Add baseline files under `app/architectures/baseline/`.
4. Add comparison artifacts under `data/comparison/` only if needed.
5. Use Semantic Scholar only for the first baseline implementation.
6. Use SQLite for baseline local state, but export to existing NDJSON and site JSON files.
7. Keep all deterministic decisions documented in code comments or module docstrings.
8. Add tests for identity resolution, deduplication, filtering, and scoring.
9. Prefer incremental commits or small patch sets.
10. After implementation, run the existing commands for all three architectures if possible.

The baseline should be strong, transparent, reproducible, and boring. The agents can be complex; the baseline should be clear enough that any improvement from agents has to be earned rather than assumed.
