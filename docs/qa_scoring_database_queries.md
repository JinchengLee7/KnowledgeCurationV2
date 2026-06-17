# Q&A: Scoring, Database, and Deterministic Query Generation

This document answers common questions about three core subsystems of the Dynamic-LR baseline pipeline. All answers are grounded in the actual implementation under `app/architectures/baseline/`.

---

## Part 1 — Deterministic Query Generation

### Q1. Where do the search queries come from? Does any LLM generate them?

No LLM is involved at any stage of query generation. Every query is derived mechanically from the survey config file (`data/survey_config.json`) by `query_builder.py` using fixed rules. The rules run in a fixed order and produce the same output for the same config every time.

---

### Q2. What is the exact order in which queries are built?

`build_queries(config)` assembles a raw list in this order:

1. **Topic query** — the `topic_overview` string from the config, cleaned and added as a single query with `kind="topic"`.
2. **Question queries** — each string in `research_questions`, cleaned, added with `kind="research_question"`.
3. **Hint queries** — each string in `query_hints`, cleaned, added with `kind="query_hint"`.
4. **Combined query** — one query built from the most frequent non-stopword tokens across all of the above, added with `kind="combined"`.

After assembling, the list is deduplicated (case-insensitively, first occurrence wins) and capped at `baseline.max_queries` (default 12). The combined query is last, so it is the first to be dropped when the cap is tight.

---

### Q3. How exactly is the combined query built?

`_combined_query(config, max_tokens)` does the following:

1. Concatenates `topic_overview`, all `research_questions`, and all `query_hints` into one pool.
2. Tokenizes each text: extracts sequences matching `[a-z0-9]+` after lowercasing.
3. Discards stopwords (a fixed frozenset in `constants.py`) and tokens shorter than 2 characters.
4. Counts how many times each surviving token appears across all texts.
5. Sorts tokens by `(-count, token_alphabetically)` — higher frequency first; alphabetical order breaks ties deterministically.
6. Takes the top `max_tokens` tokens (default 10, configurable as `combined_query_tokens` in the config).
7. Joins them with spaces.

Example: if `"explainable"` appears 4 times and `"uncertainty"` appears 4 times too, `"explainable"` comes first because `"e" < "u"` alphabetically.

---

### Q4. What does query cleaning do?

`clean_query(text)` applies three transformations in order:

1. Removes ASCII control characters (bytes 0x00–0x08, 0x0b, 0x0c, 0x0e–0x1f). Tab and newline are intentionally preserved but collapsed in the next step.
2. Collapses all whitespace (spaces, tabs, newlines) to single spaces, then strips leading and trailing whitespace.
3. Truncates to `DEFAULT_MAX_QUERY_LEN` characters (300), stripping any trailing partial word.

The original, uncleaned query string is stored in `GeneratedQuery.original` and preserved in the run artifacts. The API always receives the cleaned version.

---

### Q5. How is deduplication of queries handled?

A `seen` set of lowercased query strings is maintained as the list is assembled. Before adding any query to `deduped`, its `.lower()` is checked against `seen`. If it is already there, the query is silently skipped. Order is preserved: the first occurrence of a query string wins.

This means if `topic_overview` is `"Explainable AI"` and one of the `research_questions` is also `"explainable AI"`, only the topic query survives.

---

### Q6. Can the query list change between two runs on the same config?

Yes, but only if loop control deprioritizes a query. `loop_control.plan_adjustments(conn)` reads `query_state` from SQLite before the query list is finalized. Any query whose normalized form (`consecutive_zero_accept >= 3`) is in the deprioritized set is removed from the current run's plan.

If no deprioritization applies — which is always the case on the first run, when `query_state` is empty — the query list is identical across runs on the same config. The query-building step itself is a pure function of the config.

---

### Q7. What is `query_norm` and why does it exist?

`query_norm(q)` collapses whitespace and lowercases the query string:

```python
def query_norm(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").lower()).strip()
```

It is used as the primary key in `query_state`. Without normalization, the same conceptual query could appear in `query_state` as multiple rows if minor formatting changed between runs (e.g., extra trailing space). The normalized form is the stable, comparison-safe version.

---

### Q8. What stopwords are used?

A fixed `frozenset` in `constants.py`:

```
a an and are as at be by for from has have how in into is it its of on or
that the their them then there these this to was were what when where which
who will with how do does did using used use based via toward towards we our
can could should would may might more most than such between within across
been being also only over under about against among per
```

These are applied only during combined query token counting and scoring — not during the cleaning of individual query strings, which are sent to the API verbatim (after whitespace and length normalization).

---

### Q9. How many queries are actually sent to Semantic Scholar per run?

At most `baseline.max_queries` (default 12), minus any deprioritized by loop control. On the first-ever run, the exact count is `min(len(raw), max_queries)` where `raw` is: 1 topic + N questions + M hints + 1 combined (minus any case-insensitive duplicates).

For the default `survey_config.json` (3 questions, 3 hints): that is 1 + 3 + 3 + 1 = 8 raw queries, all distinct, so 8 are sent.

---

## Part 2 — Scoring

### Q10. What is the scoring formula?

```
score = 0.35 × title_keyword_overlap
      + 0.30 × abstract_keyword_overlap
      + 0.15 × query_phrase_match
      + 0.10 × recency_score
      + 0.05 × identifier_score
      + 0.05 × citation_score
```

All six components are normalized to `[0, 1]`. The weights are named constants (`W_TITLE`, `W_ABSTRACT`, `W_PHRASE`, `W_RECENCY`, `W_IDENTIFIER`, `W_CITATION`) in `constants.py`. The final score is rounded to 4 decimal places.

The scoring method is tagged on every record as `"baseline_lexical_v1"` so downstream consumers always know exactly which formula produced a score.

---

### Q11. What is `title_keyword_overlap` and how is it computed?

The config terms bag is built once per run: all non-stopword tokens of length ≥ 2 from `topic_overview`, `research_questions`, and `query_hints` are unioned into a `Set[str]`.

`title_keyword_overlap` is then:

```python
len(config_terms ∩ title_tokens) / len(config_terms)
```

where `title_tokens` is the set of non-stopword, length ≥ 2 tokens extracted from the candidate's title. If the config terms bag or the title is empty, the component is `0.0`.

Example: if the config has 20 unique content terms and 14 of them appear in the title, `title_keyword_overlap = 14/20 = 0.70`.

---

### Q12. What if a paper has no abstract?

`abstract_keyword_overlap` is computed as `_overlap(config_terms, candidate.abstract or "")`. An empty or absent abstract gives `abstract_keyword_overlap = 0.0`, contributing nothing to the score via that component. The paper is not rejected solely for lacking an abstract — validator.py explicitly does not apply that check.

---

### Q13. How does `query_phrase_match` work?

The function `_phrase_match(queries, title, abstract)` concatenates the lowercased title and abstract into one haystack string. It then iterates over every `GeneratedQuery` in the run:

- **Exact match**: if the full lowercased query string is a substring of the haystack → return `1.0` immediately.
- **Partial match**: tokenize the query, remove stopwords; if ≥ 50% of those tokens appear anywhere in the haystack → candidate score `0.5`.

The best score across all queries is returned. A single query that fully appears in the title immediately short-circuits the loop with `1.0`.

---

### Q14. What happens to the recency score if a paper has no year?

`_recency(year=None, config)` returns `0.5`. This is a deliberate neutral value: the paper is neither rewarded nor penalized for having an unknown publication date. It contributes `0.10 × 0.5 = 0.05` to the total score via the recency weight.

---

### Q15. How does the recency score decay for papers outside the timeline?

If `timeline_from_year` and `timeline_to_year` are both configured:

- Year inside `[from, to]`: `recency_score = 1.0`
- Year before `from`: `recency_score = max(0.0, 1.0 - 0.1 × (from - year))`
- Year after `to`: `recency_score = max(0.0, 1.0 - 0.1 × (year - to))`

The decay is 0.1 per year of distance, floored at 0.0. A paper 10 years outside the window scores `0.0` on recency. If no timeline is configured (both fields are `None`), every paper scores `1.0` on recency.

Note: this decay only affects the score. Actual hard rejection based on year only happens when `baseline.strict_timeline = true` in the config, which triggers a separate filter in `filters.py`.

---

### Q16. How is `identifier_score` calculated?

```python
present = count of {doi, arxiv_id, semantic_scholar_id, corpus_id} that are non-None
identifier_score = min(1.0, present / 2.0)
```

- 0 identifiers → `0.0`
- 1 identifier → `0.5`
- 2 or more identifiers → `1.0`

The intent is to give higher credence to papers that are well-identified in multiple systems, as those are more likely to be correctly resolved and not mislabeled.

---

### Q17. How is `citation_score` calculated? What is the cap?

```python
capped = min(citation_count, CITATION_CAP)   # CITATION_CAP = 1000
citation_score = log1p(capped) / log1p(CITATION_CAP)
```

`math.log1p(x)` computes `ln(1 + x)`, which gives 0 for 0 citations and grows slowly. Dividing by `log1p(1000)` normalizes the range to `[0, 1]`. The cap prevents a paper with 50,000 citations from scoring dramatically higher than one with 2,000 — both are well-cited; the cap compresses the tail.

A paper with 0 citations: `log1p(0) / log1p(1000) = 0 / 6.908 = 0.0`.  
A paper with 100 citations: `log1p(100) / log1p(1000) ≈ 4.615 / 6.908 ≈ 0.667`.  
A paper with 1000+ citations: `1.0`.

---

### Q18. Where are the score components stored?

`scorer.apply_score(candidate, config, queries)` writes directly onto the `PaperCandidate` object:

- `candidate.score` — the total float (4 decimal places)
- `candidate.score_components` — a dict with keys `title_keyword_overlap`, `abstract_keyword_overlap`, `query_phrase_match`, `recency_score`, `identifier_score`, `citation_score`
- `candidate.score_method` — the string `"baseline_lexical_v1"`

These are persisted to SQLite in the `papers` table (`score`, `score_components_json`, `score_method` columns) and appear in every reject record, every artifact JSON file, and the site's `papers.json`.

---

### Q19. Can two papers receive the exact same score?

Yes. Two papers with identical title overlap, abstract overlap, year, identifier count, and citation count will produce an identical score. When they appear in the accepted list, the secondary sort key (`paper_id` lexicographically) breaks the tie deterministically. The output order is therefore stable across runs.

---

### Q20. What is the default acceptance threshold and where is it set?

`config.min_relevance_score`, read from `survey_config.json`. The default seed config sets `0.3`. Any candidate with `score < 0.3` is rejected with reason `"below_relevance_threshold"`. The threshold can be changed in the config without touching the code.

---

### Q21. Why do rejected records include `matched_terms` and `missing_terms`?

For every below-threshold rejection, `filters.py` computes which config terms appeared in the candidate's title+abstract and which did not:

```python
matched = sorted(config_terms ∩ text_tokens)    # up to 25 shown
missing = sorted(config_terms − text_tokens)    # up to 25 shown
```

This makes every rejection decision explainable without having to re-run scoring. A contributor can open `rejected_candidates.json` and immediately see what terms the paper was missing.

---

## Part 3 — Database

### Q22. What database engine is used and why?

SQLite, accessed via Python's `sqlite3` standard library module — no third-party database driver or ORM. The reasons:

- Stdlib-only dependency keeps the project lightweight.
- A single file (`data/baseline/baseline.sqlite3`) is easy to inspect, copy, and back up.
- SQLite handles identity resolution queries (indexed exact-match lookups) efficiently enough for the corpus sizes this pipeline targets.
- WAL mode (`PRAGMA journal_mode=WAL`) allows concurrent readers without blocking writers.

---

### Q23. What are the seven tables and what does each store?

| Table | Purpose |
|---|---|
| `papers` | One row per accepted paper; the primary source of truth |
| `source_hits` | One row per (paper × run × query); records how each paper was found |
| `rejects` | One row per rejected candidate, with reason and evidence |
| `merge_events` | One row per intra-DB duplicate resolution event |
| `runs` | One row per pipeline run; records queries, metrics, errors, and status |
| `api_cache` | Cached raw API responses, keyed by a hash of (endpoint + params) |
| `query_state` | Per-query running totals and consecutive-zero-accept counter across all runs |

---

### Q24. How is the `papers` table primary key chosen?

The `paper_id` column is the stable identifier computed by `identity.stable_paper_id(candidate)`. Its format depends on which identifiers are present:

| Priority | Format |
|---|---|
| 1. DOI | `doi:<normalized_doi>` |
| 2. arXiv id | `arxiv:<normalized_arxiv>` |
| 3. S2 paperId | `s2:<semantic_scholar_id>` |
| 4. corpusId | `corpus:<corpus_id>` |
| 5. PMID | `pmid:<pmid>` |
| 6. Fingerprint | `fp:<sha256_hex16>` |

The fingerprint is a 16-character SHA-256 prefix over `normalize_title(title) + "|" + year + "|" + normalize_author(first_author)`. It is used only when no formal identifier exists.

---

### Q25. How does the database detect whether a candidate is a duplicate?

`db.find_existing(conn, candidate)` executes up to five sequential `SELECT` queries:

1. `WHERE doi_norm = ?` — uses index `idx_papers_doi`
2. `WHERE arxiv_id_norm = ?` — uses index `idx_papers_arxiv`
3. `WHERE semantic_scholar_id = ?` — uses index `idx_papers_s2`
4. `WHERE corpus_id = ?` — no dedicated index (uses table scan or rowid scan)
5. `WHERE title_fingerprint = ?` — uses index `idx_papers_title_fingerprint`

The first query that returns a row short-circuits the rest. The matched column is recorded in `merge_events.matched_on` so the specific field that triggered the match is always auditable.

---

### Q26. What happens when a duplicate is detected?

The pipeline does not create a new row. Instead:

1. The existing row is loaded from the database with `db.row_to_candidate`.
2. `deduper.merge_candidates(existing, new)` updates the existing object with any richer data from the new candidate (longer title/abstract, missing identifiers, newer citation counts, etc.), always under a "never overwrite good data with null" rule.
3. The merged object is scored and filtered like any other candidate.
4. If accepted, `db.update_paper` replaces the row's fields with the merged values and updates `last_seen_at`.
5. A `MergeEvent` is written to the `merge_events` table recording the existing paper id, the candidate id, the matched field, and the query that found the duplicate.

---

### Q27. What does the "never overwrite good data with null" merge rule mean precisely?

In `deduper.merge_candidates(primary, new)`:

- **Title**: only replaced if `new.title` is longer and non-empty. A blank new title cannot overwrite a real existing title.
- **Abstract**: keep whichever is longer and non-empty.
- **Year**: only filled in if `primary.year is None`.
- **Authors**: keep whichever list is longer.
- **URL**: `primary.url = primary.url or new.url` — existing value is kept unless it is falsy.
- **PDF URL**: same pattern; specifically never replaced with `None`.
- **Identifiers**: each field is `a.field or b.field` — if the primary already has a DOI, the new candidate cannot change it.
- **Citation counts**: `max(primary_val, new_val)` — the higher observation wins (treated as the more recent).

---

### Q28. What does a row in `source_hits` look like and what is it used for?

```
paper_id        TEXT    — references papers.paper_id
run_id          TEXT    — which run found this paper
architecture    TEXT    — always "baseline" for this pipeline
source          TEXT    — always "semantic_scholar" for this pipeline
query           TEXT    — the query that returned this paper
rank            INT     — position in the result list (0-indexed)
retrieved_at    TEXT    — ISO 8601 timestamp
raw_json_hash   TEXT    — SHA-256 of the raw API response for this paper
```

Source hits are used by the publisher to build the `provenance` block attached to each paper in `site/data/papers.json`. They allow the viewer to show which queries discovered a paper and in what rank position. Across runs, source hits accumulate — a paper discovered by three different queries across two runs will have three source-hit rows.

---

### Q29. What is the `api_cache` table and how does it work?

Each entry stores one complete API response:

```
cache_key       TEXT PRIMARY KEY  — SHA-256 of (endpoint + sorted params)
source          TEXT              — "semantic_scholar"
endpoint        TEXT              — e.g. "/paper/search"
request_json    TEXT              — the params dict serialized as JSON
response_json   TEXT              — the full parsed JSON response body
status_code     INT               — HTTP status (200)
created_at      TEXT              — when first fetched
expires_at      TEXT              — NULL (expiry not implemented in v1)
```

Before any HTTP call, `SemanticScholarClient._request` computes the cache key and calls `db.cache_get(conn, cache_key)`. If a row exists with a non-null `response_json`, the stored JSON is returned immediately — no network call is made. This makes the pipeline reproducible: the same query on the same config always replays the same bytes.

A parallel flat-file copy of each response is also written to `data/baseline/raw_cache/{cache_key}.json` for easy manual inspection. If that write fails for any OS reason, it is silently ignored — the SQLite copy is the authoritative cache.

---

### Q30. What is the `query_state` table and how does it feed back into future runs?

`query_state` has one row per normalized query string, accumulating stats across all runs:

```
query_norm              TEXT PRIMARY KEY  — lowercased, whitespace-collapsed query
query_original          TEXT              — original string from the first run that used it
total_runs              INT               — total number of runs that included this query
total_candidates        INT               — total raw candidates returned
total_accepted          INT               — total candidates accepted across all runs
total_duplicates        INT               — total duplicates attributed to this query
total_errors            INT               — total API/processing errors
consecutive_zero_accept INT               — runs in a row with zero accepted papers
last_run_at             TEXT              — timestamp of most recent run using this query
```

At the start of each run, `loop_control.plan_adjustments(conn)` reads this table. Any query with `consecutive_zero_accept >= 3` is added to the deprioritized list and removed from the current run's query plan.

At the end of each run, `loop_control.record_query_outcomes(conn, per_query)` upserts every query's row: increments cumulative totals, and either resets `consecutive_zero_accept` to 0 (if any papers were accepted for that query this run) or increments it by 1.

---

### Q31. How are database writes made safe against partial failures?

All writes to `papers`, `source_hits`, `merge_events`, and `rejects` happen inside a single SQLite transaction managed by `db.transaction(conn)`:

```python
@contextmanager
def transaction(conn):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

If any write inside the block raises an exception, `conn.rollback()` undoes every change made so far in that transaction. The database is never left in a half-written state. The pipeline catches `BaselineError` from this block, records it in `errors`, and continues to the next stage rather than crashing the run.

File exports (NDJSON, site JSON) use atomic writes: content is written to `<file>.tmp` first, then `os.replace(<file>.tmp, <file>)` renames it. On most operating systems this rename is atomic at the filesystem level, so a crash mid-write can never corrupt the existing published file.

---

### Q32. What happens to the database during a `--dry-run`?

The database connection string is `":memory:"` instead of the file path. SQLite opens a completely in-memory database. All schema creation, queries, inserts, and reads work identically — there is no code path that behaves differently. When the process exits, the in-memory database is discarded entirely.

This means `--dry-run` exercises the full pipeline logic, including identity resolution and deduplication, without leaving any file on disk: no `.sqlite3` file, no NDJSON files, no site data updates, no run artifacts.

---

### Q33. How can I inspect the database between runs?

The file is a standard SQLite3 database at `data/baseline/baseline.sqlite3`. Any SQLite client can open it:

```bash
# Command line
sqlite3 data/baseline/baseline.sqlite3

# Useful queries
SELECT paper_id, title, score, year FROM papers ORDER BY score DESC LIMIT 20;
SELECT reason, COUNT(*) FROM rejects GROUP BY reason;
SELECT query_norm, total_runs, total_accepted, consecutive_zero_accept FROM query_state;
SELECT matched_on, COUNT(*) FROM merge_events GROUP BY matched_on;
```

GUI tools such as DB Browser for SQLite or any IDE with a SQLite plugin also work directly on the file.

---

### Q34. Are there foreign key constraints between tables?

`PRAGMA foreign_keys=ON` is set on every connection (in `db.connect`), so constraints are enforced. The only declared foreign key in the current schema is in `source_hits`:

```sql
FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
```

This means a source-hit row cannot reference a paper that does not exist in the `papers` table. In practice, the pipeline only records source hits for papers that have already been upserted, so violations should never occur — but the constraint is there as a correctness guard.

---

### Q35. How does the database schema evolve between versions?

The current implementation uses `CREATE TABLE IF NOT EXISTS` for all tables and `CREATE INDEX IF NOT EXISTS` for all indexes. This is idempotent: running `init_schema` on an existing database adds nothing and removes nothing.

Adding a new column to an existing table requires an explicit `ALTER TABLE ... ADD COLUMN` migration step, which is not yet automated. For the first version this is intentional: schema migrations are a future addition once the baseline design is stable.

---

*For the authoritative source of truth, read `app/architectures/baseline/scorer.py`, `db.py`, `query_builder.py`, `identity.py`, `deduper.py`, and `constants.py` directly.*
