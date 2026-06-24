# Baseline Comparison: Dynamic-LR vs. Paper-Retrieval-System vs. Paper-Feed

**Prepared:** 2026-06-24  
**Purpose:** Identify differences, similarities, strengths, and gaps across three baseline implementations to inform the design of an ultimate high-performance baseline.

---

## Systems Under Comparison

| Label | Repository | Character |
|---|---|---|
| **Dynamic-LR** | This repository (`app/architectures/baseline/`) | Deterministic-only baseline, S2-only, SQLite-backed |
| **PRS** | `cherryann518/paper-retrieval-system` | Multi-source, SBERT primary, optional Ollama LLM refinement |
| **PF** | `WoosungLim01/Paper-Feed` | Multi-source async pipeline, dual TF-IDF + SBERT, no LLM |

---

## 1. Source Coverage

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Semantic Scholar | Yes | Yes | Yes |
| arXiv | No (planned) | Yes | Yes |
| OpenAlex | No (planned) | No | Yes |
| Concurrent fetch | No (sync) | Sequential | `asyncio.gather` in parallel |
| Date-range filter | Year window from config | `year` param passed to S2 | `days_back` rolling window |
| Pagination | Yes | Yes (up to `MAX_PAGES_PER_QUERY`) | Yes, breaks on old-date hit (arXiv) or total count (S2/OA) |

**Key observation:** PF has the broadest source coverage and the only concurrent multi-source fetch. PRS and Dynamic-LR are single-threaded. Dynamic-LR is the only one that does not yet include arXiv.

---

## 2. Query Generation

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Strategy | `topic + questions + hints + combined` | Single topic → optionally LLM-refined | `search_keywords` only (no expansion) |
| LLM used? | No | Yes (Ollama, optional, `--no-refine` to skip) | No |
| Deterministic? | Yes | No (Ollama introduces variance) | Yes |
| Combined query | Yes (top-N tokens from all fields) | No | No |
| Max queries | `baseline.max_queries` from config | 1 initial + refinements | `len(search_keywords)` |
| Acronym handling | No | Hardcoded ML acronym expansion table | No |
| Query cleaning | Whitespace, length, dedup | Trim + parse | `re.sub` punctuation removal |

**Key observation:** Dynamic-LR generates the most queries per run by design. PRS generates one refined query via LLM feedback. PF uses keywords directly, skipping natural-language research questions. PRS's Ollama refinement makes it non-deterministic and breaks baseline rules; however the underlying multi-round search strategy is useful.

---

## 3. Relevance Scoring

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Primary scorer | Lexical (weighted formula) | SBERT cosine (`all-MiniLM-L6-v2`) | SBERT + FAISS (`all-MiniLM-L6-v2`) |
| Secondary scorer | None | TF-IDF + recency | TF-IDF (ngram 1-2, 8000 features) |
| Semantic understanding | No | Yes | Yes |
| FAISS acceleration | No | No | Yes (IndexFlatIP, L2-normalized) |
| Embedding cache | No | No | Yes (numpy .npy per paper_id) |
| Score components stored | Yes (6 named fields) | `scores` dict per paper | `tfidf_score` + `sbert_score` both stored |
| Recency component | Yes (in formula) | Yes (separate `rank_recency` method) | Implicit (date-range fetch) |
| Citation boost | Yes | No | No |
| Identifier bonus | Yes | No | No |
| Score transparency | High (named weights) | Medium (method breakdown) | Medium (two named scores) |
| Deterministic? | Yes | SBERT is fixed-weight, yes | SBERT is fixed-weight, yes |

**Key observation:** Both PRS and PF use SBERT semantic embeddings which greatly outperform pure lexical scoring for relevance. Dynamic-LR's lexical scorer is fully deterministic and transparent but will miss semantically related papers that do not share surface tokens. PF's FAISS+embedding cache is the most performant of the three. PF also computes TF-IDF as a companion score for every paper, enabling hybrid threshold decisions.

---

## 4. Deduplication and Identity Resolution

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Identity priority | DOI > arXiv > S2 > corpusId > fingerprint | DOI > arXiv > S2 > title fingerprint | DOI > arXiv > OpenAlex > S2 > fingerprint |
| Fingerprint hash | SHA-256, title+year | SHA-256, title+year | MD5, title+year+first_author |
| Cross-session dedup | Yes (SQLite) | Yes (SQLite) | No (in-run only via NDJSON) |
| Source-hit merging | Yes | Yes | Yes |
| Completeness-based merge selection | No (keep existing) | No (keep existing) | Yes (picks the more complete record as base) |
| ID normalization | DOI lowercase, strip prefix; arXiv strip version | DOI lowercase; arXiv strip version | DOI strip URL prefix; arXiv strip URL prefix |
| Merge event log | Yes | Yes | No |
| Author used in fingerprint | Yes (first author) | No (title+year only) | Yes (first author last name) |

**Key observation:** PF's completeness-based merge selector is the most robust: it picks the richer record as the canonical version rather than blindly keeping the first seen. Dynamic-LR and PRS default to preserving the existing record. PF also includes OpenAlex ID as a fourth identity dimension, reducing the hash-fallback rate. Only Dynamic-LR has cross-session deduplication via persistent SQLite.

---

## 5. Filtering

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Minimum score threshold | Yes (`min_relevance_score`) | Yes (`SCORE_TOP_MIN` + `SCORE_GOOD` + `MIN_GOOD_PAPERS`) | Yes (`min_relevance_score`) |
| Missing title reject | Yes | Implicit (no title → no normalize) | Yes (`not title`) |
| Missing URL reject | No | No | Yes (`not url`) |
| Year / timeline filter | Yes | Yes (pass year range to API + recency score) | Yes (at fetch time by `days_back`) |
| Reject reason stored | Yes (typed enum) | No | `reject_reason` string field |
| Partial evidence stored | Yes (`evidence` dict) | No | No |
| Strict vs. soft filters | Configurable | Threshold-based | Threshold-based |

**Key observation:** Dynamic-LR has the most structured reject records. PRS uses a statistical acceptance gate (`results_acceptable`) that checks top score, good-paper count, and score gap simultaneously — this is more robust than a single threshold. PF's URL requirement is stricter than the others.

---

## 6. Persistence and Storage

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Primary store | SQLite | SQLite (`papers.db`) | NDJSON only |
| Cross-run state | Yes | Yes | No |
| Schema tables | papers, source_hits, rejects, merge_events, runs, api_cache, query_state | papers, source_hits, merge_events, rejects | NDJSON files only |
| Atomic writes | Yes (tmp+rename) | No | No |
| Raw API cache | Yes (SQLite table + file) | Yes (file per cache key) | No (embedding cache only) |
| Run artifacts | Yes (per-run directory) | Yes (`outputs/runs/{run_id}/`) | No |
| Site export | Yes | No (separate Flask app) | Yes (`site/data/*.json`) |
| NDJSON export | Yes | No | Yes |
| Changelog | Yes | No | No |

**Key observation:** Dynamic-LR has the most complete persistence design. PRS has a SQLite store with source_hits and merge tracking but no site publishing. PF publishes a static site but has no cross-run SQLite state — each run processes duplicates only within that run. PF's lack of persistent storage means it cannot detect cross-run duplicates without loading all prior NDJSON.

---

## 7. API Client Robustness

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| HTTP library | `urllib` (stdlib) | `urllib` (stdlib) | `httpx` (async) |
| Retry on 429 | Yes | Yes (with Retry-After header + jitter) | Yes (60s fixed sleep) |
| Retry on 5xx | Yes | No (only 429 special-cased) | No |
| Exponential backoff | Yes | Yes (with jitter) | No (fixed 60s for 429) |
| Timeout | Yes | Yes (30s) | Yes (15s for S2, 30s for OpenAlex) |
| Rate limit spacing | Yes | Yes (`SEMANTIC_SCHOLAR_MIN_INTERVAL`) | Yes (fixed `asyncio.sleep`) |
| API key support | Yes | Yes | Yes (S2 only; OpenAlex uses User-Agent polite pool) |
| Request logging | Yes | No | Logger only |
| Response caching | Yes (SQLite `api_cache` table) | Yes (file per hash) | No |

**Key observation:** PRS has the most sophisticated backoff (exponential + jitter + Retry-After header respect). Dynamic-LR's client is more structured (SQLite cache, request logging). PF uses a fixed 60s wait which is blunt. PF is the only async client, which matters for multi-source parallelism.

---

## 8. Loop Engineering and Automation

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Designed for repeated runs | Yes (loop_control module planned) | Single-run with optional multi-round | Single-run pipeline |
| Query state tracking | Yes (`query_state` table) | Per-run only | No |
| Dynamic query priority | Yes (planned, rule-based) | Via LLM refinement | No |
| Target paper detection | Yes (DOI/S2/title fallback chain) | No | No |
| Date gap detection | No | No | Yes (`validate_fetch_results`) |
| Run history | Yes (SQLite `runs` table) | Artifact files only | NDJSON `run_history.ndjson` |
| System status file | Yes | No | Yes |

**Key observation:** Dynamic-LR has the most complete automation design. PF's date-gap detection is a valuable validation step absent from the others. PRS's multi-round loop is LLM-driven; it would need to be replaced with deterministic loop control for the baseline.

---

## 9. Architecture Comparability

| Dimension | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Structured run result | Yes (`ManagerRunResult`) | Yes (dict with metrics) | Partial (print summary only) |
| Named metrics | Yes (acceptance rate, duplicate rate, API latency) | Yes (latency, api_calls, score distribution) | Partial (counts only) |
| Architecture label | Yes | Implicit (agent mode) | Hardcoded `"baseline"` |
| Provenance field | Yes (per-paper) | No | `source_hits` field |
| Score stored per paper | Yes | Yes | Yes (tfidf_score + sbert_score) |

---

## 10. Dependency Footprint

| System | Key Dependencies |
|---|---|
| Dynamic-LR | `sqlite3` (stdlib), `requests` or `urllib` |
| PRS | `sentence-transformers`, `scikit-learn`, `flask` |
| PF | `sentence-transformers`, `scikit-learn`, `faiss-cpu`, `torch`, `httpx`, `feedparser`, `numpy` |

PF has the heaviest dependency footprint. PRS is lighter (no FAISS). Dynamic-LR has the lightest footprint by design — it avoids embeddings in v1 but trades semantic recall for determinism.

---

## 11. Strengths Summary

### Dynamic-LR Strengths
- Fully deterministic, auditable scoring with named components
- Most complete persistence: SQLite + NDJSON + site export + run artifacts
- Cross-session deduplication and merge event logging
- Target paper detection with fallback chain
- Loop control infrastructure for repeated automated runs
- Atomic writes and structured error types
- Architecture comparison interface built in

### PRS Strengths
- Best S2 API client (exponential backoff with jitter, Retry-After header, per-source stats)
- SBERT semantic scoring → superior recall on paraphrase/synonym variants
- Multi-round search with configurable refinement (LLM refinement is replaceable with deterministic rules)
- Clean dataclass schema (`PaperRecord`) with `to_dict` / `from_agent_dict` conversions
- SQLite store with batched upsert and chunk transactions
- Offline mode with sample papers for testing

### PF Strengths
- Three-source async fetch (arXiv + S2 + OpenAlex) run concurrently
- Dual-score output: TF-IDF + SBERT both stored on every paper
- FAISS-accelerated similarity search with embedding persistence cache
- Completeness-based duplicate merge (keeps the richer record)
- Date-gap validation after fetch
- OpenAlex integration (free, no API key, rich metadata)
- GPU/MPS acceleration auto-detection for embeddings

---

## 12. Gaps Summary

### Dynamic-LR Gaps
- No SBERT/embedding scoring → lower semantic recall
- Semantic Scholar only → narrower source coverage
- No async fetch → slower multi-source expansion
- No date-gap validation
- No completeness-based merge selection
- Lexical formula may systematically miss papers that do not repeat query tokens

### PRS Gaps
- LLM dependency (Ollama) makes it non-deterministic without `--no-refine`
- No OpenAlex source
- No site export pipeline
- No date-based fetch filter (relies only on year parameter)
- No loop state or repeated-run engineering
- Backoff jitter is good, but 5xx retries are not implemented
- Completeness-based merge not implemented

### PF Gaps
- No cross-session SQLite state → cannot deduplicate against prior runs without full NDJSON scan
- No structured reject records with typed reasons and evidence
- No target paper detection
- No loop control or query priority state
- No run artifacts directory
- Query generation uses only `search_keywords` — drops topic, research questions, and combined query
- No API response cache (only embedding cache)
- Fixed 60s 429 wait is blunt compared to exponential backoff

---

## 13. Recommended Synthesis for Ultimate Baseline

The strongest baseline would combine the best element from each system:

### Source Layer
- Adopt PF's `asyncio`-based concurrent multi-source fetch (arXiv + S2 + OpenAlex)
- Adopt PRS's S2 API client robustness: exponential backoff with jitter, Retry-After header, per-source error isolation
- Keep Dynamic-LR's SQLite `api_cache` table for response caching

### Query Layer
- Keep Dynamic-LR's comprehensive query generation: topic + questions + hints + combined
- Add PRS's ML acronym expansion table as a lightweight, non-LLM pre-processing step
- Apply PF's query sanitization (`re.sub` punctuation removal) before sending to APIs

### Scoring Layer
- Add SBERT (`all-MiniLM-L6-v2`) + FAISS from PF as the primary semantic scorer
- Keep Dynamic-LR's lexical components (title overlap, abstract overlap, phrase match, recency, citation, identifier) as a secondary explainable score
- Keep PF's embedding persistence cache for efficiency
- Adopt PF's dual-output pattern: store both semantic and lexical scores on every paper
- Consider PRS's statistical acceptance gate (`top_score >= threshold AND good_count >= N AND score_gap >= delta`) as an additional batch-quality check

### Deduplication Layer
- Adopt PF's completeness-based merge selection (prefer the richer record)
- Keep Dynamic-LR's four-dimension identity priority (DOI > arXiv > S2 > corpusId > fingerprint)
- Add OpenAlex ID as a fifth identity dimension
- Keep Dynamic-LR's cross-session SQLite deduplication and merge event logging

### Persistence Layer
- Keep Dynamic-LR's full schema (papers, source_hits, rejects, merge_events, runs, api_cache, query_state)
- Keep Dynamic-LR's atomic writes and run artifact directories
- Keep PF's site export pipeline

### Validation Layer
- Add PF's date-gap detection as a post-fetch validation step
- Keep Dynamic-LR's structured reject records with typed reasons and evidence

### Loop Layer
- Keep Dynamic-LR's loop_control module design (state machine, not LLM)
- Keep Dynamic-LR's target paper detection
- Keep Dynamic-LR's query_state table for tracking per-query performance across runs

### Non-Negotiable Constraints
- All scoring, query generation, and accept/reject decisions must remain deterministic
- No LLM calls (Ollama or otherwise) in the baseline path
- SBERT embeddings are allowed because the model weights are fixed — given the same input, output is identical

---

## 14. Implementation Priority Order

1. Add SBERT + FAISS scoring to Dynamic-LR (`app/architectures/baseline/scorer.py`) — highest impact on recall
2. Add arXiv source adapter and integrate into baseline fetch loop
3. Add OpenAlex source adapter
4. Upgrade S2 client with PRS-style exponential backoff + jitter
5. Implement async fetch orchestration (or parallel thread pool for S2/arXiv/OA)
6. Adopt PF's completeness-based merge selection in `deduper.py`
7. Persist embedding cache (numpy) for SBERT vectors
8. Add PF-style date-gap validation to the post-fetch step
9. Add PRS's ML acronym expansion to `query_builder.py` as a static lookup table
10. Store both semantic and lexical scores per paper for cross-architecture comparison
