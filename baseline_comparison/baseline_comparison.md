# Baseline Comparison: Dynamic-LR · PRS · PF

**Prepared:** 2026-06-24  
**Purpose:** Identify differences, similarities, strengths, and gaps across three baseline implementations to inform the design of an ultimate high-performance deterministic baseline.

---

## Systems Under Comparison

| Label | Repository / Path | Character |
|---|---|---|
| **Dynamic-LR** | `app/architectures/baseline/` (this repo) | Fully deterministic, S2-only, SQLite-backed, lexical scoring |
| **PRS** | `cherryann518/paper-retrieval-system` | Multi-source, SBERT primary, optional Ollama LLM query refinement |
| **PF** | `WoosungLim01/Paper-Feed` | Multi-source async pipeline, dual TF-IDF + SBERT, no LLM |

---

## 1. Source Coverage

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Semantic Scholar | Yes | Yes | Yes |
| arXiv | No (planned) | Yes | Yes |
| OpenAlex | No (planned) | No | Yes |
| Concurrent fetch | No (sync) | No (sequential, per-source) | Yes (`asyncio.gather`, all 3 sources in parallel) |
| Fetch strategy | Synchronous `urllib` | Synchronous `urllib` | Async `httpx` |
| Date-range filter | Year window from config passed as API param | `year` param to S2; arXiv not date-filtered | `days_back` rolling window, stop on old-date hit |
| Pagination | Yes | Yes (up to `MAX_PAGES_PER_QUERY=2`) | Yes; arXiv stops on first old-date entry; S2/OA uses total count |
| Per-query cap | `max_results_per_query` | `SEMANTIC_SCHOLAR_FETCH_LIMIT=100` × pages | 300/arXiv, 200/S2, 200×3/OA per query |

**Observation:** PF has the broadest source coverage and the only concurrent multi-source fetch.  
Dynamic-LR is the only implementation without arXiv.  
PRS and Dynamic-LR are synchronous; PF's `asyncio` approach is significantly faster for multi-source runs.

---

## 2. Query Generation

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Strategy | `topic + research_questions + query_hints + combined` | Single topic query; optionally LLM-refined via Ollama | `search_keywords` only — research questions excluded |
| LLM used? | No | Yes (Ollama, optional via `--no-refine`) | No |
| Deterministic? | Yes | No when Ollama is enabled | Yes |
| Combined query | Yes — top-N non-stopword tokens by frequency, ties broken alphabetically | No | No |
| Source of queries | All config fields | Topic only → LLM rewrites | `search_keywords` or `query_hints` fallback |
| Max queries | Configurable `baseline.max_queries` | 1 initial + up to `MAX_REFINEMENT_ROUNDS=2` refinements | `len(search_keywords)` |
| Acronym expansion | No | Hardcoded ML acronym table (e.g. `rag → retrieval augmented generation`) | No |
| Query cleaning | Whitespace collapse, control-char strip, length cap | Strip + first-line parse | `re.sub` punctuation removal |
| Deduplication | Case-insensitive, order-preserving | None | `dict.fromkeys` on keyword list |

**Observation:** Dynamic-LR generates the most semantically varied queries (topic + per-question + per-hint + combined).  
PF uses only explicit keywords, dropping natural-language research questions entirely.  
PRS's LLM refinement is effective but non-deterministic — it cannot be used in a reproducible baseline without replacing it with a deterministic fallback rule.

---

## 3. Relevance Scoring

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Primary scorer | Lexical weighted formula | SBERT cosine (`all-MiniLM-L6-v2`) | SBERT + FAISS (`all-MiniLM-L6-v2`) |
| Secondary scorer | None | TF-IDF cosine + recency | TF-IDF (1–2 ngrams, 8 000 max features) |
| FAISS acceleration | No | No | Yes (`IndexFlatIP`, L2-normalized unit vectors) |
| Embedding persistence cache | No | No | Yes (`.npy` + `.json` per paper_id; model-change auto-reset) |
| GPU/MPS auto-detect | No | No | Yes |
| Semantic understanding | No | Yes | Yes |
| Recency component | Yes (linear decay in formula, weight 0.10) | Yes (separate `rank_recency` method, [0,1] by year range) | Implicit (date-range fetch filter, not a score component) |
| Citation score | Yes (log-normalized, capped, weight 0.05) | No | No |
| Identifier quality score | Yes (count of DOI/arXiv/S2/corpus IDs, weight 0.05) | No | No |
| Score formula | `0.35·title + 0.30·abstract + 0.15·phrase + 0.10·recency + 0.05·id + 0.05·citation` | SBERT cosine as `relevance_score`; TF-IDF + recency stored separately | SBERT as `score`; TF-IDF as companion |
| Named components stored per paper | Yes (6 named fields + `score_method`) | `scores` dict (`sbert_cosine`, `tfidf_cosine`, `recency`) | `sbert_score` + `tfidf_score` both stored |
| Deterministic? | Yes | Yes (SBERT weights are fixed; same input → same output) | Yes (same fixed weights) |
| Query text for scoring | All queries generated for this run (phrase-match check) | The single search query (or last refined query) | Concatenation of all config fields: `topic + questions + context + hints` |

**Observation:** Both PRS and PF use SBERT semantic embeddings, which capture synonym and paraphrase matches that pure lexical scoring misses.  
Dynamic-LR's lexical scorer is fully transparent and auditable but will under-score papers that don't share surface tokens with the config.  
PF's FAISS index with embedding cache is the most performant; it only re-encodes new papers.  
PF uses the richest query text for scoring (all config fields concatenated), which tends to produce better calibration when the topic, questions, and hints are complementary.

---

## 4. Deduplication and Identity Resolution

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Identity priority | DOI > arXiv > S2 > corpusId > title+year+firstAuthor fingerprint | DOI > arXiv > S2 paperId > title+year fingerprint | DOI > arXiv > OpenAlex > S2 > title+year+firstAuthorLastName fingerprint |
| Fingerprint hash | SHA-256, `title_norm\|year` | SHA-256, `title_norm\|year` | MD5, `title_norm\|year\|first_author_last` |
| Cross-session dedup | Yes (SQLite `papers` table, all runs) | Yes (SQLite `papers.db`, all runs) | No (NDJSON `read_existing_ids` — scans entire file) |
| Merge base selection | Keep existing (primary) | Keep existing (primary) | Keep more complete record (higher completeness score) |
| Completeness score | No | No | Yes — counts non-empty fields across 10 dimensions |
| Identifier union on merge | Yes (fill all missing IDs from both) | Yes | Yes |
| Author on fingerprint | Yes (first author, first token) | No | Yes (first author last name) |
| OpenAlex ID as identity | No | No | Yes (3rd priority) |
| Intra-run dedup | Yes (`dedupe_candidates`) | Yes (`dedupe_papers` via `agent_paper_key`) | Yes (`deduplicate` function) |
| Cross-run dedup | Yes (SQLite `find_existing`) | Yes (SQLite `upsert_papers_batch`) | Read-only NDJSON ID scan |
| Merge event log | Yes (`merge_events` table + NDJSON artifact) | Yes (`merge_events` table) | No |
| Source-hit merging | Yes | Yes | Yes (merged `source_hits` list) |

**Observation:** PF's completeness-based merge selection is the most robust — it always preserves the richer record instead of blindly keeping the first-seen.  
Dynamic-LR and PRS keep the existing record as primary, which is safe but may retain a lower-quality version.  
Dynamic-LR is the only system that writes a structured merge event log for every cross-session merge, making deduplication fully auditable.  
PF has the widest identity coverage (four ID types vs. three in Dynamic-LR and PRS).

---

## 5. Filtering

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Minimum score threshold | Yes (`min_relevance_score`) | Yes (`SCORE_TOP_MIN=0.35`) + batch gate | Yes (`min_relevance_score`, default 0.05) |
| Batch acceptance gate | No | Yes (`results_acceptable`: checks top_score, good_count≥3, score_gap≥0.08) | No |
| Missing title reject | Yes | Implicit (no title → `normalize_s2` returns `None`) | Yes (explicit `not title` check) |
| Missing URL reject | No | No | Yes (explicit `not url` check) |
| Year / timeline filter | Yes (at filter stage, configurable strict/soft) | At API level + recency score component | At fetch level via `days_back` window |
| Reject reason stored | Yes (typed enum: `missing_title`, `below_relevance_threshold`, `outside_timeline`, etc.) | No | `reject_reason` string field only |
| Reject evidence stored | Yes (`evidence` dict: `threshold`, `matched_terms`, `missing_terms`) | No | No |
| Per-paper reject record written | Yes (`rejects` SQLite table + NDJSON) | `record_reject` to SQLite `rejects` table | Appended to `rejects.ndjson` |

**Observation:** Dynamic-LR has the most structured, explainable reject records.  
PRS's batch acceptance gate (`top_score` + `good_count` + `score_gap`) catches cases where a threshold alone would pass a batch of mediocre results — this is absent from the others.  
PF's `not url` reject rule is stricter than the others and may discard otherwise valid records from OpenAlex.

---

## 6. Persistence and Storage

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Primary store | SQLite (`baseline.sqlite3`) | SQLite (`papers.db`) | NDJSON only |
| Cross-run state | Yes | Yes | No (NDJSON ID scan only) |
| SQLite tables | `papers`, `source_hits`, `rejects`, `merge_events`, `runs`, `api_cache`, `query_state` | `papers`, `source_hits`, `merge_events`, `rejects` | None |
| Per-query performance tracking | Yes (`query_state` table: runs, accepted, duplicates, error counts) | No | No |
| API response cache | Yes (SQLite `api_cache` table + TTL) | Yes (one file per request hash under `outputs/cache/`) | No |
| Embedding cache | No | No | Yes (numpy `.npy`, persists across runs) |
| Atomic writes | Yes (tmp + rename on export files) | No | No |
| Run artifacts directory | Yes (`data/baseline/run_artifacts/{run_id}/`) | Yes (`outputs/runs/{run_id}/`) | No |
| Site export | Yes (`site/data/`) | No (Flask serves from SQLite) | Yes (`site/data/`) |
| NDJSON export | Yes (`data/papers.ndjson`, `rejects.ndjson`, `run_history.ndjson`) | No | Yes (primary storage) |
| Changelog | Yes (`data/changelog.md`) | No | Yes (`data/changelog.md`) |
| System status JSON | Yes | No | Yes |

**Observation:** Dynamic-LR has the most complete and structured persistence design.  
PRS has a solid SQLite core but no site publishing or run artifacts.  
PF has a complete publish pipeline but no cross-session SQLite state — duplicate detection degrades as the NDJSON file grows.  
Dynamic-LR is the only system with a `query_state` table for tracking per-query performance across runs.

---

## 7. API Client Robustness

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| HTTP library | `urllib` (stdlib) | `urllib` (stdlib) | `httpx` (async) |
| 429 handling | Yes (configurable wait) | Yes — reads `Retry-After` header; falls back to jitter-multiplied exponential backoff | Yes — fixed 60 s wait |
| Exponential backoff | Yes | Yes (base 2.0 s, up to 60 s, × uniform jitter 1.0–1.5) | No |
| Jitter | No | Yes (uniform random, prevents thundering herd) | No |
| 5xx retry | Yes | No | No |
| Timeout | Yes (env `REQUEST_TIMEOUT_S`) | Yes (30 s) | Yes (15 s for S2; 30 s for OA; one retry on OA timeout) |
| API key support | Yes (`SEMANTIC_SCHOLAR_API_KEY`) | Yes (`SEMANTIC_SCHOLAR_API_KEY`) | Yes for S2; OA uses polite-pool `User-Agent` |
| Request logging | Yes | Print-only | Logger |
| Response cache | Yes (SQLite `api_cache` with TTL) | Yes (file cache, no TTL) | No |

**Observation:** PRS has the most sophisticated backoff (exponential + jitter + `Retry-After` header respect).  
PF's fixed 60 s wait is blunt and may over-throttle or under-throttle depending on the actual rate-limit window.  
Dynamic-LR is the only one with TTL-aware response caching in SQLite, which avoids re-fetching stable results within a cache window.  
Only PF handles 5xx network timeouts with a single retry at the OpenAlex level.

---

## 8. Loop Engineering and Automation

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Designed for repeated runs | Yes (`loop_control.py` state-machine module) | Single-run with multi-round fetch | Single-run pipeline |
| Loop control mechanism | Deterministic rules in `loop_control.py` | LLM-driven query refinement | None |
| Query priority adjustment | Yes (planned in `loop_control`) | Via LLM refinement | No |
| Low-yield query demotion | Yes (rule: 0 accepted for N consecutive runs → lower priority) | No | No |
| High duplicate-rate response | Yes (rule: enable recency filter when dup rate > 0.80) | No | No |
| Target paper detection | Yes — DOI > S2 ID > arXiv > exact title > quoted search > fuzzy | No | No |
| Date gap detection | No | No | Yes (`validate_fetch_results`, visual bar chart output) |
| Run history | Yes (SQLite `runs` table + `run_history.ndjson`) | Artifact files only | `run_history.ndjson` |
| System status | Yes (`data/system_status.json`, updated per pipeline stage) | No | Yes |
| Architecture comparison metrics | Yes (structured `ManagerRunResult` with all sub-results) | Yes (dict with metrics) | Print summary only |

**Observation:** Dynamic-LR has the most complete automation infrastructure.  
PF's date-gap detection is a valuable quality check absent from the other two.  
PRS's multi-round loop is powerful but LLM-driven; replacing Ollama with a deterministic rule (e.g. widen query if `good_count < N`) would make it baseline-compatible.

---

## 9. Dependency Footprint

| System | Core Extra Dependencies |
|---|---|
| Dynamic-LR | `sqlite3` (stdlib), `requests`/`urllib` — no ML packages in v1 |
| PRS | `sentence-transformers≥2.2`, `scikit-learn≥1.3`, `flask≥3.0` |
| PF | `sentence-transformers==2.7`, `scikit-learn==1.4.2`, `faiss-cpu==1.7.4`, `torch==2.3.0`, `numpy≥1.24`, `httpx==0.27`, `feedparser==6.0.11` |

Dynamic-LR has the lightest footprint; PF has the heaviest. For a cloud-scheduled pipeline, PF's PyTorch dependency adds ~500 MB to the install size.

---

## 10. Strengths Summary

### Dynamic-LR
- Fully deterministic and auditable — every score component is named and stored
- Most complete persistence schema: SQLite across all pipeline stages
- Cross-session deduplication and per-run merge event log
- `query_state` table for tracking per-query performance over time
- Target paper detection with fallback chain
- Loop control module designed as an explicit state machine
- Atomic writes on export; structured error hierarchy
- Architecture comparison interface built in; `ManagerRunResult` feeds directly into comparison artifacts

### PRS
- Best Semantic Scholar API client: exponential backoff + jitter + `Retry-After` header
- SBERT semantic scoring: strong recall on synonym/paraphrase variants
- Multi-round search loop (LLM-driven; replaceable with deterministic rules)
- Clean `PaperRecord` dataclass with `to_dict` / `from_agent_dict`
- Batched SQLite upsert with chunked transactions
- Offline fixture mode for unit testing without API calls
- ML acronym expansion table as a lightweight, LLM-free enrichment step

### PF
- Three-source async concurrent fetch (arXiv + S2 + OpenAlex) via `asyncio.gather`
- SBERT + FAISS with GPU/MPS auto-detect — fastest inference path
- Embedding persistence cache (numpy) — only encodes new papers on repeat runs
- Dual-score output: both `tfidf_score` and `sbert_score` stored on every paper
- Completeness-based duplicate merge selection (picks the richer record)
- OpenAlex as a free, no-key, high-coverage third source
- Date-gap detection and source-distribution validation after fetch
- Full site publishing pipeline with changelog and retro-scoring of existing papers

---

## 11. Gaps Summary

### Dynamic-LR
- No SBERT/embedding scoring → lower semantic recall; misses paraphrases and synonyms
- Semantic Scholar only → narrower coverage than PRS (2 sources) or PF (3 sources)
- Synchronous single-threaded fetch → slower as sources are added
- No date-gap validation after fetch
- Completeness-based merge not implemented (always keeps existing as primary)
- Backoff is present but lacks jitter; no `Retry-After` header parsing
- No embedding persistence cache (relevant once SBERT is added)

### PRS
- LLM dependency (Ollama) makes it non-deterministic by default; `--no-refine` disables refinement but leaves no deterministic fallback for weak batches
- No OpenAlex source
- No site export pipeline (Flask UI is separate)
- No date-based rolling window filter — relies entirely on the year parameter
- No loop state or repeated-run query tracking
- 5xx retries not implemented
- Completeness-based merge not implemented
- No per-query performance metrics across runs

### PF
- No cross-session SQLite state — duplicate detection requires a full NDJSON scan every run
- No structured reject records with typed reasons and evidence dicts
- No target paper detection
- No loop control or query priority adjustment
- No run artifacts directory per run
- Query generation uses only `search_keywords` — topic, research questions, and combined query all dropped
- No API response cache — identical queries re-fetch every run
- Fixed 60 s 429 wait has no jitter and ignores `Retry-After` header
- URL required for acceptance may discard valid records that lack a landing page

---

## 12. Feature Matrix

| Feature | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Semantic Scholar | ✓ | ✓ | ✓ |
| arXiv | – | ✓ | ✓ |
| OpenAlex | – | – | ✓ |
| Async concurrent fetch | – | – | ✓ |
| SBERT scoring | – | ✓ | ✓ |
| TF-IDF scoring | – | ✓ | ✓ |
| FAISS index | – | – | ✓ |
| Embedding cache | – | – | ✓ |
| Lexical weighted formula | ✓ | – | – |
| Citation score component | ✓ | – | – |
| Identifier quality score | ✓ | – | – |
| Phrase-match component | ✓ | – | – |
| Batch acceptance gate | – | ✓ | – |
| Completeness-based merge | – | – | ✓ |
| Cross-session SQLite dedup | ✓ | ✓ | – |
| Merge event log | ✓ | ✓ | – |
| Per-query state tracking | ✓ | – | – |
| Target paper detection | ✓ | – | – |
| Loop control module | ✓ | – | – |
| Date-gap validation | – | – | ✓ |
| API response cache (TTL) | ✓ | ✓ (no TTL) | – |
| Exponential backoff + jitter | – | ✓ | – |
| Retry-After header | – | ✓ | – |
| 5xx retry | ✓ | – | – |
| Structured reject records | ✓ | partial | partial |
| Run artifacts per run | ✓ | ✓ | – |
| Site export pipeline | ✓ | – | ✓ |
| Changelog | ✓ | – | ✓ |
| System status JSON | ✓ | – | ✓ |
| Architecture comparison result | ✓ | ✓ | – |
| LLM-free | ✓ | Optional | ✓ |
| Fully deterministic | ✓ | When `--no-refine` | ✓ |

---

## 13. Recommended Synthesis for an Ultimate Baseline

The best possible baseline combines the proven elements from all three systems into a single deterministic pipeline.

### Source Layer
- Add arXiv and OpenAlex sources to Dynamic-LR, adopting PF's three-source structure
- Replace the synchronous fetch loop with `asyncio`-based concurrent fetch, adopting PF's `asyncio.gather` pattern
- Upgrade the S2 API client with PRS's exponential backoff, jitter, and `Retry-After` header logic
- Retain Dynamic-LR's SQLite `api_cache` table with TTL for response caching

### Query Layer
- Keep Dynamic-LR's comprehensive query generation: `topic + questions + hints + combined`
- Add PRS's ML acronym expansion table (`rag → retrieval augmented generation`) as a static deterministic pre-processing step — no LLM required
- Apply PF's query sanitization (`re.sub` punctuation removal) before sending to APIs

### Scoring Layer
- Add SBERT (`all-MiniLM-L6-v2`) + FAISS from PF as the primary semantic scorer
- Retain Dynamic-LR's lexical components (title overlap, abstract overlap, phrase match, recency, citation, identifier) as a fully explainable secondary score
- Adopt PF's embedding persistence cache (numpy `.npy`) and model-change auto-reset
- Adopt PF's dual-output pattern: store both `sbert_score` and `lexical_score` on every paper
- Add PRS's batch acceptance gate as a run-level quality metric (`top_score`, `good_count`, `score_gap`)

### Deduplication Layer
- Adopt PF's completeness-based merge selection (prefer the richer record as primary)
- Add OpenAlex ID as a fifth identity dimension in the priority chain
- Keep Dynamic-LR's cross-session SQLite deduplication and merge event logging

### Filtering Layer
- Keep Dynamic-LR's structured reject records with typed reasons and evidence dicts
- Retain the `not title` filter from all three
- Consider PRS's batch acceptance gate as a soft run-level alert (not a hard reject)

### Persistence Layer
- Keep Dynamic-LR's full schema (papers, source_hits, rejects, merge_events, runs, api_cache, query_state)
- Keep Dynamic-LR's atomic writes and per-run artifact directories
- Keep PF's site publishing pipeline including retro-scoring

### Validation Layer
- Add PF's date-gap detection as a post-fetch validation step

### Loop Layer
- Keep Dynamic-LR's `loop_control.py` state-machine design
- Implement a deterministic multi-round fallback rule to replace PRS's LLM refinement:
  - If `good_count < 3` after scoring: widen query by adding adjacent terms from config
  - If `duplicate_rate > 0.80`: add publication-date filter to future queries
  - If query returns zero results: fall back to combined query

---

## 14. Implementation Priority Order

Priority is ordered by expected improvement in retrieval quality and coverage.

1. **Add SBERT + FAISS scoring** to `app/architectures/baseline/scorer.py` — highest single impact on semantic recall
2. **Add arXiv source adapter** and integrate into pipeline
3. **Add OpenAlex source adapter** and integrate
4. **Implement async concurrent fetch** via `asyncio` or `concurrent.futures`
5. **Upgrade S2 client** with PRS-style exponential backoff + jitter + `Retry-After`
6. **Adopt completeness-based merge selection** in `deduper.py`
7. **Add embedding persistence cache** (numpy) for SBERT vectors
8. **Add PF-style date-gap validation** as a post-fetch check
9. **Add ML acronym expansion** to `query_builder.py` as a static lookup table
10. **Implement deterministic multi-round fallback rule** in `loop_control.py` to replace LLM refinement
