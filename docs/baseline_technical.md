# Dynamic-LR Baseline: Technical Process Documentation

This document traces every step of a single baseline run from the moment `pipeline.run()` is called to the moment `ManagerRunResult` is returned. It is written as a first-person walkthrough: *I* am the pipeline, processing data in real time. Every data transformation, decision rule, and error response is described in terms of what actually happens in the code.

---

## Before Anything Starts

The entry point is `app/architectures/baseline/pipeline.py:run()`. Before I touch any data, I do three things in a single instant:

1. I record `started_at` as an ISO 8601 UTC timestamp.
2. I start a `time.perf_counter()` wall-clock so I can measure total runtime at the end.
3. I generate a `run_id` by formatting the current UTC time as `"baseline-20260617T143022123456"`. This string is unique and sortable — no UUID, no randomness, no external service.

I then initialize an empty `errors: List[str]`. Every recoverable problem I encounter during the run gets appended here. This list, not an exception, is how I communicate partial failure to the caller.

---

## Step 1 — Load Configuration (`app/config.py`)

### What I do

I call `store.write_system_status({"status": "loading_config", ...})`, which writes a machine-readable status to `data/system_status.json`. This file can be polled by anything watching the run.

Then I call `load_survey_config(config_path)`. This opens the JSON file at `data/survey_config.json` (or the path the CLI passed in), parses it with `json.load`, and maps every recognized field into a `SurveyConfig` dataclass. I also keep a raw `dict` copy of the entire file — I will need it later when I publish the site data.

The `SurveyConfig` dataclass gives me:

| Field | Type | Where it comes from |
|---|---|---|
| `topic_overview` | `str` | `survey_config["topic_overview"]` |
| `research_questions` | `List[str]` | `survey_config["research_questions"]` |
| `query_hints` | `List[str]` | `survey_config["query_hints"]` |
| `question_context` | `str` | `survey_config["question_context"]` |
| `timeline_from_year` | `Optional[int]` | `survey_config["timeline_from_year"]` |
| `timeline_to_year` | `Optional[int]` | `survey_config["timeline_to_year"]` |
| `min_relevance_score` | `float` | `survey_config["min_relevance_score"]` |
| `target_papers` | `List[dict]` | `survey_config.get("target_papers", [])` |
| `baseline` | `dict` | `survey_config.get("baseline", {})` |
| `semantic_scholar` | `dict` | `survey_config.get("semantic_scholar", {})` |

Optional blocks (`baseline`, `semantic_scholar`, `target_papers`) use `.get(..., default)` so missing keys never raise.

### What can go wrong

If the file does not exist, is not valid JSON, or is missing required top-level fields, `load_survey_config` raises `ConfigError`. This is the **only hard stop** in the entire pipeline. When it fires, I immediately construct a `ManagerRunResult` with `status="failure"` and return it. No further work happens.

---

## Step 2 — Build Deterministic Queries (`query_builder.py`)

### What I do

I call `build_queries(config)` and receive a list of `GeneratedQuery` objects. Each has:

```python
@dataclass
class GeneratedQuery:
    query: str        # the cleaned string that goes to the API
    original: str     # the original string from the config (preserved in artifacts)
    kind: str         # "topic" | "research_question" | "query_hint" | "combined"
    index: int        # position in the final list
```

The construction rules are fixed and run in this exact order:

**Rule 1 — topic query.** If `topic_overview` is non-empty after stripping whitespace, I clean it and add one query with `kind="topic"`.

**Rule 2 — question queries.** For each string in `research_questions`, I clean it and add one query with `kind="research_question"`.

**Rule 3 — hint queries.** For each string in `query_hints`, I add one with `kind="query_hint"`.

**Rule 4 — combined query.** I pool all tokens from topic, questions, and hints together. For every token longer than 1 character that is not in the stopword list, I increment a counter. I then sort entries by `(-count, token_alphabetically)` — the negative count ensures higher-frequency terms come first; alphabetical order on ties makes the result deterministic when two tokens appear equally often. I take the top `combined_query_tokens` tokens (default 10 from `constants.DEFAULT_COMBINED_QUERY_TOKENS`) and join them with spaces.

**Cleaning** (`clean_query`): strips control characters (characters 0x00–0x1f except tab/newline), collapses repeated whitespace, and truncates to `DEFAULT_MAX_QUERY_LEN` characters. The original is preserved unchanged in the `GeneratedQuery.original` field.

**Deduplication**: I scan the list with a `seen` set of lowercased query strings. If two queries would be identical case-insensitively, only the first survives.

**Cap**: The final list is sliced to `max_queries` (default 12). The combined query, being last, is the first to be dropped when the cap is tight.

### What can go wrong

If all queries produce empty strings after cleaning — an unlikely but possible configuration — the list is empty. I check for this before connecting to the database. An empty query list is a `failure` with a clear message: `"No queries generated from survey config"`.

---

## Step 3 — Open the Database and Start the Run (`db.py`)

### What I do

I open (or create) the SQLite database. If `dry_run` is `True`, the connection string is `":memory:"` — everything runs in RAM and nothing is written to disk. If `dry_run` is `False`, the path is `data/baseline/baseline.sqlite3` (configurable via `BASELINE_SQLITE_PATH`).

I call `db.init_schema(conn)`, which executes `CREATE TABLE IF NOT EXISTS` statements for all seven tables and their indexes in a single transaction:

- `papers` — accepted paper records (primary key: `paper_id TEXT`)
- `source_hits` — one row per (paper × run × query); links a paper to how it was found
- `rejects` — candidates that failed validation or scoring
- `merge_events` — records when an incoming candidate matched an existing paper
- `runs` — one row per run; records queries, metrics, errors, status, summary
- `api_cache` — raw API response cache keyed by a hash of (endpoint + params)
- `query_state` — per-query running totals across all runs

This is idempotent. The same schema call on run 2 or run 100 changes nothing if the tables already exist.

I then call `db.start_run(conn, run_id, ...)`, which inserts a row into `runs` with `success = NULL` and `finished_at = NULL` — a sentinel I will fill in when the run completes.

---

## Step 4 — Loop-Control: Plan Adjustments (`loop_control.py`)

### What I do

Before making any API call, I read the persisted history of every query I have ever run. `db.get_query_state(conn)` returns a dict mapping normalized query strings to their accumulated counts. I look specifically at `consecutive_zero_accept`.

The rule is simple: if a query has produced zero accepted papers for three or more consecutive runs, I add it to `adj.deprioritized_queries`. When I return to `pipeline.py`, I filter the query list — any query whose normalized form appears in the deprioritized set is removed from this run's plan.

I always leave at least one query in the list even if loop control would deprioritize everything. The guard is: `queries = [q for q in queries if ...] or queries`. The `or queries` fallback prevents accidentally running with zero queries.

I record a human-readable `note` explaining what was deprioritized and why, so I can inspect it in the run artifact later.

On the first run ever, `get_query_state` returns an empty dict, so `plan_adjustments` returns a `LoopAdjustments` with all defaults (no deprioritization, no flags set).

---

## Step 5 — Query Semantic Scholar (`semantic_scholar_client.py`)

### Setup

I create one `SemanticScholarClient(conn, enable_cache=True)` instance for the whole run. This client holds a `ClientStats` dataclass that accumulates counts of API calls, cache hits/misses, rate-limit events, and latency samples.

I read the list of fields to request from `config.semantic_scholar.get("fields")`, falling back to `constants.DEFAULT_FIELDS` which requests 18 metadata fields: `paperId`, `corpusId`, `title`, `abstract`, `year`, `authors`, `url`, `openAccessPdf`, `externalIds`, `citationCount`, `referenceCount`, `influentialCitationCount`, `publicationTypes`, `publicationDate`, `venue`, `fieldsOfStudy`, `isOpenAccess`.

I set a per-query result limit: `min(max_results_per_query, 100)`. Semantic Scholar's standard search endpoint caps at 100 results per request.

### For each query

I iterate over every `GeneratedQuery` in the (possibly adjusted) list. For each one:

**Cache check.** I compute a cache key by concatenating the endpoint path (`/graph/v1/paper/search`) with the URL-encoded, alphabetically-sorted parameters, then hashing that string with SHA-256 (truncated to hex). I query `api_cache` in SQLite for this key. If a row exists, I return the stored response directly — no network call. The `cache_hit_count` counter increments. This is why repeated runs on the same config are reproducible: the exact same bytes that came back from the API the first time are replayed.

**HTTP GET.** If there is no cache hit, I build the URL:

```
https://api.semanticscholar.org/graph/v1/paper/search?query=<encoded>&fields=<...>&limit=<n>
```

I set a `User-Agent` header and, if `SEMANTIC_SCHOLAR_API_KEY` is set in the environment, an `x-api-key` header. I issue the request with `urllib.request.urlopen` under a timeout (default 30 seconds from `REQUEST_TIMEOUT_S`).

**Response parsing.** On HTTP 200, I parse the body as JSON. The top-level response is `{"total": N, "offset": 0, "data": [...]}`. I extract the `data` list and return it. Each element in `data` is a raw dict representing one paper.

**Error handling — by attempt.** The retry loop runs up to `MAX_ATTEMPTS=4` times:

| Error condition | What I observe | What I do |
|---|---|---|
| HTTP 429 | `urllib.error.HTTPError` with code 429 | Raise `RateLimitError`, increment `rate_limit_events`, log a warning |
| HTTP 5xx | `urllib.error.HTTPError` with code ≥ 500 | Raise `APIResponseError` |
| Invalid JSON | `json.JSONDecodeError` in body parsing | Raise `APIResponseError` |
| Network error | `urllib.error.URLError`, `TimeoutError`, `OSError` | Catch and log |
| After catching an error | — | Sleep for `RETRY_BACKOFF_S[attempt]` seconds (2, 5, 15) then retry |

If all four attempts fail, I raise `APIResponseError`. Back in `pipeline.py`, this is caught as a `BaselineError`. I append a message to `errors`, increment the per-query error count, and `continue` to the next query. The run does not stop.

After a successful response, I sleep for `RATE_LIMIT_SLEEP_S` (a small polite delay between requests) before returning.

**Cache write.** If the request succeeded, I write the response to both the SQLite `api_cache` table and a file at `data/baseline/raw_cache/{cache_key}.json`. The file write is wrapped in a try/except — if the disk write fails for any reason, it is silently ignored (the SQLite cache is the authoritative copy).

### Collecting candidates

For each raw item in the response list, I call `normalizer.normalize(item, query=gq.query)`. The result is a `PaperCandidate`. Normalization errors (unexpected shapes, completely empty items) are caught and appended to `errors` before continuing.

I immediately validate the candidate. I also record the candidate's query and rank (position in the result list) in a `first_seen` dict keyed by stable paper id — I will need this later for source-hit attribution.

I check the total `collected` count against `max_candidates_per_run` (default 200). If I reach the cap, I stop the crawl loop, log a message, append a note to `errors`, and break. The note is surfaced in the final result so no silent truncation occurs.

---

## Step 6 — Normalize Each Raw Record (`normalizer.py`)

### What I do

For each raw dict from Semantic Scholar, I extract fields by name, handling missing keys with `.get(..., default)`. I construct a `PaperCandidate` object:

```python
@dataclass
class PaperCandidate:
    paper_id: str               # assigned later by identity.stable_paper_id
    title: str
    abstract: Optional[str]
    year: Optional[int]
    authors: List[str]          # list of author name strings
    url: Optional[str]
    pdf_url: Optional[str]
    identifiers: PaperIdentifiers
    score: float                # 0.0 until scorer runs
    score_components: dict
    score_method: str
    rejection_reason: Optional[str]
    sources: List[str]          # ["semantic_scholar"]
    raw: dict                   # {"semantic_scholar": <original item>}
    citation_count: Optional[int]
    reference_count: Optional[int]
    influential_citation_count: Optional[int]
    venue: Optional[str]
    publication_date: Optional[str]
    fields_of_study: List[str]
    publication_types: List[str]
    provenance: dict            # filled in by publisher, not here
```

The `identifiers` field is a `PaperIdentifiers` dataclass built from `externalIds`:

```python
PaperIdentifiers(
    doi          = item.get("externalIds", {}).get("DOI"),
    arxiv_id     = item.get("externalIds", {}).get("ArXiv"),
    semantic_scholar_id = item.get("paperId"),
    corpus_id    = item.get("corpusId"),
    pmid         = item.get("externalIds", {}).get("PubMed"),
    openalex_id  = None,   # not in S2 response
)
```

Authors are extracted as a list of name strings from the nested `[{"name": "..."}]` list. The raw dict is preserved in `raw["semantic_scholar"]` so it can be written to artifacts and used for cache-key hashing later.

---

## Step 7 — Validate Each Candidate (`validator.py`)

### What I do

I call `validate(candidate, min_title_tokens)` for every normalized candidate. The validator returns a `ValidationResult(ok: bool, reason: Optional[str], candidate: PaperCandidate)`.

First I repair the candidate:
- I strip leading/trailing whitespace from `title` and `abstract`.
- I collapse repeated internal whitespace.
- I strip control characters.

Then I apply rejection criteria:
- If `title` is empty or only whitespace: `reason = "missing_title"`, `ok = False`.
- If the number of word tokens in `title` is less than `min_title_tokens` (default 2): `reason = "missing_title"`, `ok = False`.

I do **not** reject for:
- Missing abstract
- Missing PDF URL
- Missing year
- Short abstract

If validation fails, I set `candidate.rejection_reason = vr.reason`. The candidate is still added to `collected`. The reason will cause it to fail the filter step later, where it will be written to the rejects log with a proper `RejectRecord`.

---

## Step 8 — Intra-Run Deduplication (`deduper.py`)

### What I do

I call `deduper.dedupe_candidates(candidates)`. This collapses every candidate in `collected` by stable `paper_id`. Before any merging, I assign every candidate its stable id by calling `identity.stable_paper_id(candidate)`.

### How `stable_paper_id` works

This function examines the `PaperIdentifiers` on a candidate in priority order:

1. **DOI** — if present, normalize it (lowercase, strip `https://doi.org/`, strip `doi:` prefix, trim) and return `"doi:<normalized>"`.
2. **arXiv id** — if present, normalize it (lowercase, strip `arxiv:`, strip version suffix `v1`/`v2`/...) and return `"arxiv:<normalized>"`.
3. **Semantic Scholar paperId** — return `"s2:<paperId>"`.
4. **corpusId** — return `"corpus:<corpusId>"`.
5. **PMID** — return `"pmid:<pmid>"`.
6. **Fingerprint** — if none of the above are present, compute `SHA256(normalize_title(title) + "|" + year + "|" + normalize_author(first_author))[:16]` and return `"fp:<hex16>"`.

The fingerprint path handles papers with no identifiers at all. The 16-character SHA-256 prefix gives 2^64 possible values, making collision probability negligible for any realistic corpus.

### Merging within the same run

I maintain a dict `by_id: {paper_id -> PaperCandidate}`. When a second candidate with the same `paper_id` arrives (same paper returned by two different queries), I call `merge_candidates(primary, new)`:

- **Title**: keep the longer non-empty string.
- **Abstract**: keep the longer non-empty string.
- **Year**: fill `primary.year` from `new.year` only if `primary.year` is `None`.
- **Authors**: keep the longer list.
- **URL**: keep `primary.url` if set; otherwise take `new.url`.
- **PDF URL**: keep `primary.pdf_url` if set; **never** overwrite with `None`.
- **Identifiers**: union (fill each missing field from the new candidate; never overwrite a present identifier).
- **Citation counts**: take `max(primary, new)` for `citation_count`, `reference_count`, `influential_citation_count`.
- **Venue, publication_date, fields_of_study, publication_types**: fill if missing.
- **Sources**: append new sources not already present.

The first-seen order is preserved in an `order` list, so the output is deterministic regardless of what order queries returned results.

`dedupe_candidates` returns `(unique_candidates, intra_run_duplicate_count)`.

---

## Step 9 — Resolve Identity Against the Database (`deduper.py` + `db.py`)

### What I do

For each candidate in `unique`, I call `deduper.resolve_against_db(conn, candidate, run_id, query, source)`. This looks up whether the candidate already exists in the SQLite `papers` table.

The lookup in `db.find_existing` checks these columns in order:
1. `doi_norm = identity.normalize_doi(candidate.identifiers.doi)`
2. `arxiv_id_norm = identity.normalize_arxiv(candidate.identifiers.arxiv_id)`
3. `semantic_scholar_id = candidate.identifiers.semantic_scholar_id`
4. `corpus_id = candidate.identifiers.corpus_id`
5. `title_fingerprint = identity.title_fingerprint(candidate.title, candidate.year, first_author)`

Each is tried in sequence with a `SELECT` query. The first match wins. If all five checks return nothing, the candidate is new.

### If a match is found

I call `db.row_to_candidate(existing_row)` to reconstruct the existing `PaperCandidate` from the database row. I call `db.matched_on(conn, candidate, existing_row)` to record which field triggered the match (e.g. `"doi"`, `"arxiv_id"`, `"title_fingerprint"`). I call `merge_candidates(existing, candidate)` to update the existing record with any richer data from the new candidate. I set `merged.paper_id = existing_row["paper_id"]` to preserve the original id.

I construct a `MergeEvent`:

```json
{
  "run_id": "baseline-...",
  "existing_paper_id": "doi:10.1234/...",
  "candidate_id": "s2:abc123",
  "matched_on": "doi",
  "source": "semantic_scholar",
  "query": "Explainable AI",
  "created_at": "2026-06-17T..."
}
```

The merge event is collected in a list. It is written to SQLite later in the persist step.

### If no match is found

The candidate is new. I assign `candidate.paper_id = identity.stable_paper_id(candidate)` and mark `is_new = True`.

### What flows out of this step

For each candidate I now have:
- A `PaperCandidate` that is either merged with existing data or freshly created.
- A boolean `is_new` that tells persist whether to `INSERT` or `UPDATE`.
- Optionally a `MergeEvent`.

I still have not scored or filtered anything.

---

## Step 10 — Score Candidates (`scorer.py`)

### What I do

Immediately after resolving identity, I call `scorer.apply_score(merged, config, queries)`. This mutates the candidate in place, writing to `.score`, `.score_components`, and `.score_method`.

### How each component is calculated

**Config terms bag** — I collect all non-stopword tokens (length ≥ 2) from `topic_overview`, every `research_question`, and every `query_hint`. This produces a `Set[str]` that represents the topic universe. It is computed once and reused for every candidate.

**title_keyword_overlap** — I count how many config terms appear in the set of non-stopword tokens extracted from the candidate's title, divided by the total number of config terms. Range: `[0, 1]`.

**abstract_keyword_overlap** — Same calculation over the abstract. If the abstract is empty, this component is 0.

**query_phrase_match** — I iterate over every `GeneratedQuery`. I lowercase both the query and the concatenated `title + abstract`. If the query string appears as a substring, return `1.0` immediately. Otherwise, I tokenize the query, remove stopwords, and check whether at least half the tokens are present anywhere in the text — if so, the score is `0.5`. The best score across all queries is used.

**recency_score** — If the year is `None`, return `0.5` (uncertain, neither penalized nor rewarded). If `timeline_from_year` and `timeline_to_year` are both set and the paper's year falls inside the window, return `1.0`. If outside, apply a linear decay of `0.1` per year distance, floored at `0.0`. If no timeline is configured, return `1.0`.

**identifier_score** — Count how many of the four strong identifiers (DOI, arXiv, S2 paperId, corpusId) are present. Two or more gives `1.0`; one gives `0.5`; none gives `0.0`.

**citation_score** — Take `min(citation_count, CITATION_CAP)`. Apply `log1p(capped) / log1p(CITATION_CAP)`. A paper with zero citations scores `0.0`. A highly-cited paper near the cap (default 5000) scores close to `1.0`. Papers with extremely high citation counts are capped to avoid letting one outlier dominate.

**Final score:**

```
score = 0.35 × title_overlap
      + 0.30 × abstract_overlap
      + 0.15 × phrase_match
      + 0.10 × recency
      + 0.05 × identifier
      + 0.05 × citation
```

All components and the final score are stored on the candidate as `score_components` (a dict) and `score` (a float rounded to 4 decimal places). `score_method = "baseline_lexical_v1"` is also set so any downstream consumer knows exactly which formula produced the score.

---

## Step 11 — Apply Filters (`filters.py`)

### What I do

I call `filters.apply_filters(resolved, config, run_id)`. This returns `(accepted, reject_records)`.

I iterate over every scored candidate and apply three rejection checks in order:

**Check 1 — missing title.** `if not (c.title or "").strip()` → reject with reason `"missing_title"`. No evidence dict needed.

**Check 2 — outside timeline (strict mode only).** If `config.baseline.get("strict_timeline", False)` is `True` *and* the year is present and outside `[timeline_from_year, timeline_to_year]` → reject with reason `"outside_timeline"` and evidence `{"year": ..., "timeline_from": ..., "timeline_to": ...}`. If the year is missing, the candidate is not rejected on this check.

**Check 3 — below threshold.** `if c.score < config.min_relevance_score` → reject with reason `"below_relevance_threshold"`. For evidence, I compute the matched and missing config terms against the candidate's title+abstract (capped to 25 each) and store them alongside the actual score and threshold.

A candidate that passes all three checks goes into `accepted`. One that fails any check goes into `reject_records` as a `RejectRecord`:

```json
{
  "candidate_id": "doi:10.1234/...",
  "run_id": "baseline-...",
  "architecture": "baseline",
  "source": "semantic_scholar",
  "query": null,
  "title": "Example paper title",
  "year": 2023,
  "reason": "below_relevance_threshold",
  "score": 0.18,
  "evidence": {
    "threshold": 0.3,
    "score": 0.18,
    "matched_terms": ["explainable", "ai"],
    "missing_terms": ["uncertainty", "quantification", "interpretable", ...]
  },
  "created_at": "2026-06-17T..."
}
```

### Accepted output sort

`accepted.sort(key=lambda x: (-x.score, x.paper_id or ""))`. Score descending, then paper_id lexicographically. This deterministic sort means two runs that accept the same papers always write them in the same order.

---

## Step 12 — Persist to SQLite (`db.py`)

### What I do

I open a single SQLite transaction with `db.transaction(conn)` (a context manager that commits on exit, rolls back on exception). Inside the transaction:

**For each accepted paper:**

- If `is_new_map[paper_id]` is `True`: call `db.insert_paper(conn, p, now)`. This inserts one row into the `papers` table with all normalized fields serialized (author lists, identifiers, JSON blobs for `fields_of_study`, `publication_types`, `authors`, `external_ids`). The `doi_norm`, `arxiv_id_norm`, `title_fingerprint` columns are indexed and used for deduplication in future runs.
- If `is_new_map[paper_id]` is `False`: call `db.update_paper(conn, p, now)`. This updates metadata columns with the merged values; it never clears a column that was previously populated (the merge rules already handled this).

**Source hits:** For each accepted paper, I look up its original query and rank from `first_seen`, hash its raw response, and call `db.record_source_hit(conn, SourceHit(...))`. This inserts one row into `source_hits` linking the paper, run, query, and rank position.

**Merge events:** For each `MergeEvent` whose `existing_paper_id` is in `accepted_ids`, I call `db.record_merge_event(conn, ev)`. I only write merge events for papers that were accepted; a duplicate that was rejected is handled entirely through the rejects log.

**Reject records:** For each `RejectRecord`, I call `db.record_reject(conn, rr)`. This stores the reject in the `rejects` table with its reason, score, and evidence JSON.

If any `BaselineError` is raised during the transaction, the exception is caught, rolled back, appended to `errors`, and execution continues. The run does not stop because of a database write error.

---

## Step 13 — Target-Paper Check (`target_check.py`)

### What I do

I call `target_check.check_targets(conn, config.target_papers)`. For each entry in `target_papers` I attempt to resolve it in the database using this fallback chain:

1. Look up by `normalize_doi(target["doi"])` against `doi_norm` column.
2. Look up by `target["semantic_scholar_id"]` against `semantic_scholar_id` column.
3. Look up by `normalize_arxiv(target["arxiv_id"])` against `arxiv_id_norm` column.
4. Look up by `normalize_title(target["title"])` against `title_norm` column.

The first match wins. I build a `TargetCheckResult`:

```json
{
  "target_title": "Attention Is All You Need",
  "must_find": true,
  "found": true,
  "found_by": "doi_lookup",
  "paper_id": "doi:10.48550/arxiv.1706.03762",
  "was_accepted": true,
  "rank_position": 3,
  "rejection_reason": null
}
```

If the target was found but rejected (it exists in the `rejects` table rather than `papers`), `was_accepted` is `False` and `rejection_reason` is populated.

If the paper is not in either table, `found = False`.

I then call `target_check.target_metrics(results)` to produce summary counts:

```json
{
  "target_total": 2,
  "target_found": 1,
  "target_accepted": 1,
  "target_missed": 1,
  "target_rejected": 0
}
```

These metrics enter the run summary and are available for comparing retrieval accuracy across architectures.

---

## Step 14 — Update Query State (`loop_control.py`)

### What I do

I call `loop_control.record_query_outcomes(conn, per_query)`. For each query in the `per_query` dict, I upsert a row in the `query_state` table:

```sql
INSERT INTO query_state (query_norm, query_original, total_runs, total_candidates, 
                         total_accepted, total_duplicates, total_errors, last_run_at)
VALUES (?, ?, 1, ?, ?, ?, ?, ?)
ON CONFLICT(query_norm) DO UPDATE SET
  total_runs = total_runs + 1,
  total_candidates = total_candidates + excluded.total_candidates,
  total_accepted = total_accepted + excluded.total_accepted,
  ...
```

The `consecutive_zero_accept` counter is also managed: if this run produced at least one accepted paper for the query, the counter resets to `0`. If this run produced zero accepted papers, the counter increments. This is the feedback edge that `plan_adjustments` will read on the next run.

---

## Step 15 — Assemble Metrics and Finalize the Run

### What I do

I assemble a `RunMetrics` dataclass from all the counters collected during the run:

| Metric | Source |
|---|---|
| `runtime_seconds` | `time.perf_counter()` difference |
| `api_call_count` | `client.stats.api_call_count` |
| `cache_hit_count` | `client.stats.cache_hit_count` |
| `cache_miss_count` | `client.stats.cache_miss_count` |
| `raw_candidate_count` | total items received from API |
| `normalized_candidate_count` | total items successfully normalized |
| `deduplicated_candidate_count` | unique candidates after intra-run dedupe |
| `accepted_count` | papers that passed all filters |
| `rejected_count` | candidates that failed any filter |
| `duplicate_count` | intra-run dupes + DB merge events |
| `merge_count` | DB merge events only |
| `new_paper_count` | papers inserted for the first time |
| `updated_paper_count` | existing papers updated |
| `error_count` | length of `errors` list |
| `avg_api_latency_ms` | mean across all HTTP request durations |
| `db_write_time_ms` | wall-clock of the persist transaction |

I call `_decide_status(errors, processed)`:
- If there are errors **and** zero candidates were processed (nothing to show for it): `"failure"`.
- If there are errors **and** at least some candidates were processed: `"partial_success"`.
- If there are no errors: `"success"`.

I call `db.finish_run(conn, run_id, finished_at, status, metrics_summary, errors, summary_text)` to update the `runs` row with its final state.

---

## Step 16 — Publish to Canonical Files (`publisher.py`)

### What I do

I call `publisher.publish(conn, result, config_raw, dry_run=dry_run)`. If `dry_run` is `True`, this function returns immediately without writing anything.

The publisher loads all accepted papers from the `papers` table (`db.load_all_papers(conn)`) and builds a provenance block for each:

```json
{
  "provenance": {
    "architectures_seen": ["baseline"],
    "sources_seen": ["semantic_scholar"],
    "first_seen_by": "baseline",
    "last_seen_by": "baseline",
    "source_hits": [
      {"run_id": "...", "query": "...", "rank": 2}
    ]
  }
}
```

Then I write to every canonical location using atomic writes (write to `<file>.tmp`, then `os.replace(<file>.tmp, <file>)`). This means if any write fails mid-stream, the original file is not corrupted:

| Output file | Contents |
|---|---|
| `data/papers.ndjson` | One JSON object per line, all accepted papers with provenance |
| `data/rejects.ndjson` | All reject records |
| `data/run_history.ndjson` | Run summary appended to existing history |
| `data/changelog.md` | Human-readable update appended |
| `data/system_status.json` | Current status (`"finished"`) |
| `site/data/papers.json` | JSON array of all papers (for the static viewer) |
| `site/data/rejects.json` | JSON array of all rejects |
| `site/data/run_history.json` | JSON array of run history |
| `site/data/system_status.json` | Same as `data/system_status.json` |
| `site/data/survey_config.json` | The raw config dict (for the viewer to display) |

If the publish step raises `BaselineError`, I catch it, append to `errors`, and downgrade status to `partial_success` if it was previously `success`. The already-written canonical files are safe because each was written atomically.

---

## Step 17 — Write Per-Run Artifacts

### What I do

If not a dry run, I create the directory `data/baseline/run_artifacts/{run_id}/` and write one JSON file per artifact:

| File | Contents |
|---|---|
| `generated_queries.json` | List of `GeneratedQuery` dicts (kind, original, index) |
| `scored_candidates.json` | All candidates after scoring (accepted + rejected) |
| `accepted_candidates.json` | Accepted candidates only |
| `rejected_candidates.json` | `RejectRecord` dicts with full evidence |
| `merge_events.json` | `MergeEvent` dicts |
| `target_check.json` | `TargetCheckResult` dicts |
| `metrics.json` | `RunMetrics` summary dict |
| `errors.json` | The raw `errors` list |
| `final_report.json` | The full `ManagerRunResult` dict |

I also call `metrics_mod.write_comparison_record(run_id, "baseline", metrics_summary)`, which appends a record to `data/comparison/runs/{run_id}.json`. This file exists so that a separate comparison step can load results from baseline, single-agent, and multi-agent runs side by side and compute architecture-level summaries.

---

## Step 18 — Return

I close the database connection with `conn.close()` and return the `ManagerRunResult` to `app/manager.py`. The result is flat:

```python
ManagerRunResult(
    architecture       = "baseline",
    queries_generated  = 8,
    sources_queried    = ["semantic_scholar"],
    candidates_found   = 156,   # raw from API
    candidates_after_dedupe = 134,
    papers_accepted    = 89,
    candidates_rejected = 45,
    dry_run            = False,
    started_at         = "2026-06-17T14:30:22.123456+00:00",
    finished_at        = "2026-06-17T14:31:45.678901+00:00",
    status             = "success",
    run_id             = "baseline-20260617T143022123456",
    errors             = [],
)
```

`app/manager.py` returns this to `app/run.py`, which prints a one-line summary and exits with code 0 if `status != "failure"`, or code 1 if it does.

---

## How Information Flows: A Summary Diagram (prose)

```
survey_config.json
    │
    ▼ SurveyConfig + raw dict
[build_queries]
    │
    ▼ List[GeneratedQuery]
[plan_adjustments] ◄────────────────── query_state (SQLite)
    │ (possibly filtered list)
    ▼ List[GeneratedQuery] (adjusted)
[SemanticScholarClient.search × N]
    │  ├─ on cache hit: raw JSON from api_cache (SQLite)
    │  └─ on miss: HTTP GET → raw JSON written to api_cache + raw_cache/
    │
    ▼ List[raw dict]
[normalizer.normalize × each item]
    │
    ▼ List[PaperCandidate] (paper_id="", score=0.0)
[validator.validate × each]
    │ (sets rejection_reason on malformed)
    ▼ List[PaperCandidate] (validated)
[deduper.dedupe_candidates]
    │ (collapses same paper_id; merges metadata)
    ▼ List[PaperCandidate] (unique, ~merged)
[deduper.resolve_against_db × each]
    │  ├─ match found: merge with DB record; produce MergeEvent
    │  └─ no match: assign stable paper_id; is_new=True
    ▼ List[PaperCandidate] (resolved)
[scorer.apply_score × each]
    │ (writes .score, .score_components, .score_method)
    ▼ List[PaperCandidate] (scored)
[filters.apply_filters]
    │
    ├─▶ accepted: List[PaperCandidate] (sorted by -score, paper_id)
    └─▶ rejects:  List[RejectRecord]
         │
         ▼ SQLite transaction
    [db.insert_paper / db.update_paper]   → papers table
    [db.record_source_hit]                → source_hits table
    [db.record_merge_event]               → merge_events table
    [db.record_reject]                    → rejects table
         │
         ▼
    [target_check.check_targets]          ← papers/rejects tables
         │
         ▼
    [loop_control.record_query_outcomes]  → query_state table
         │
         ▼
    [db.finish_run]                       → runs table
         │
         ▼
    [publisher.publish]
         │  atomic writes (*.tmp → rename)
         ├─▶ data/*.ndjson
         ├─▶ data/system_status.json
         ├─▶ data/changelog.md
         └─▶ site/data/*.json
         │
         ▼
    [_write_artifacts]
         └─▶ data/baseline/run_artifacts/{run_id}/*.json
              data/comparison/runs/{run_id}.json
         │
         ▼
    ManagerRunResult  ──────────────────►  app/manager.py → app/run.py → stdout + exit code
```

---

## Status Transitions

The `system_status.json` file is updated at each stage of the run:

| Stage | `status` value written |
|---|---|
| Loading config | `loading_config` |
| Building queries | `building_queries` |
| Querying API | `querying_semantic_scholar` |
| Deduplicating | `deduplicating` |
| Resolving + scoring | `scoring` |
| Filtering | `filtering` |
| Persisting to DB | `persisting` |
| Publishing | `publishing` |
| Done (all ok) | `finished` |
| Done (with errors) | `partial_success` or `failure` |

---

## Error Taxonomy

Every error in the baseline is typed. When caught, they are turned into a string and appended to `errors: List[str]`.

| Exception class | Raised by | Caught where |
|---|---|---|
| `ConfigError` | `load_survey_config` | `pipeline.run` — hard stop |
| `SemanticScholarAPIError` | base class | — |
| `RateLimitError` | `_http_get` on 429 | `_request` retry loop; then `pipeline.run` per-query handler |
| `APIResponseError` | `_http_get` on 5xx, bad JSON | `_request` retry loop; then `pipeline.run` per-query handler |
| `CandidateValidationError` | validator | not raised; stored as `rejection_reason` |
| `IdentityResolutionError` | identity module | not raised in practice; deduper handles gracefully |
| `DatabaseWriteError` | db write functions | `pipeline.run` persist block |
| `PublishError` | publisher | `pipeline.run` publish block |
| `ExportError` | publisher file writes | `pipeline.run` publish block |

Soft handling means the pipeline always reaches the artifact-write and result-return steps, regardless of how many errors accumulated along the way.

---

## Determinism Guarantees

Given identical inputs (config file, database state, API responses or cache), every output is identical:

- `build_queries` depends only on the config. Stopwords and tie-break rules are fixed. The combined query token ranking uses `(-count, alphabetical)` — fully deterministic.
- `stable_paper_id` is a pure function of the candidate's identifiers. SHA-256 is deterministic.
- `dedupe_candidates` preserves first-seen order. `merge_candidates` rules are deterministic (keep longer, keep max, fill missing).
- `score` depends only on the candidate's fields, the config's term bag, and the query list. No randomness, no LLM, no embeddings.
- `apply_filters` checks deterministic thresholds. The accepted list is sorted by `(-score, paper_id)`.
- The `api_cache` replays the exact prior response bytes. Once a query has been cached, re-running with the same config produces the same result.
- All output files are written after sorting. `data/papers.ndjson` is sorted by `paper_id`. `site/data/papers.json` is sorted by `-score`.

The only source of non-determinism is a live network call to Semantic Scholar with no cache. Once a query's response is cached, all subsequent runs are reproducible.

---

## The Loop Across Multiple Runs

Each run improves the next one through persisted state, not through LLM inference:

```
Run 1
 ├─ Discovers 120 papers across 8 queries
 ├─ Query "AI explanation" → 15 accepted
 ├─ Query "marine biology" → 0 accepted
 └─ Writes query_state:
      "ai explanation": {consecutive_zero_accept: 0, ...}
      "marine biology": {consecutive_zero_accept: 1, ...}

Run 2
 ├─ plan_adjustments reads query_state
 │   → "marine biology" has consecutive_zero=1, below threshold 3, keep it
 ├─ Proceeds with all 8 queries
 └─ "marine biology" → 0 accepted again
      → consecutive_zero_accept now 2

Run 3
 └─ "marine biology" still below threshold (2 < 3), kept

Run 4
 ├─ plan_adjustments reads: consecutive_zero_accept=3 for "marine biology"
 │   → added to deprioritized_queries
 ├─ 7 queries run (one deprioritized)
 └─ No API call wasted on a query that has never contributed
```

This feedback loop requires no judgment call, no LLM, no human intervention. It is a counter threshold with a documented rule.

---

*This document reflects the code as of the initial baseline implementation. For the authoritative source, read the modules under `app/architectures/baseline/` directly. All decision thresholds are named constants in `app/architectures/baseline/constants.py`.*
