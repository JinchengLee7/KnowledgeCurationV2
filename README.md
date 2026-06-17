# Dynamic-LR

Dynamic literature retrieval and survey-management system. It compares
automation architectures for literature-survey workflows and asks one research
question:

> Does LLM-based sequential decision-making improve a literature-survey workflow
> compared with a strong deterministic, API-driven baseline?

Architectures:

- `baseline` — a strong, **deterministic, non-LLM** pipeline (Semantic Scholar only).
- `single-agent` — LLM agent (placeholder in this version).
- `multi-agent` — LLM agents (placeholder in this version).

This README documents the **baseline** pipeline in depth: every stage, how it
behaves under failure, and the *loop engineering* that lets repeated runs improve
themselves without any LLM in the loop.

---

## Quick start

```bash
# Deterministic baseline, no file writes (uses an in-memory DB):
python -m app.run --architecture baseline --dry-run --verbose

# Full baseline run (writes SQLite, NDJSON, site data, and per-run artifacts):
python -m app.run --architecture baseline

# Tests (fixture API responses, no network):
pytest tests/baseline -q
```

Configuration lives in `data/survey_config.json`. Runtime is **stdlib-only**
(`urllib`, `sqlite3`, `json`, `dataclasses`); `pytest` is the only dev dependency.

> **Rate limits.** Without `SEMANTIC_SCHOLAR_API_KEY` the public Graph API
> throttles hard (HTTP 429). The pipeline degrades gracefully (see
> [Situation handling](#situation-handling)) and the SQLite response cache makes
> re-runs progressively cheaper. Set the key for full throughput.

---

## Pipeline at a glance

The baseline is an **automated loop**, not a one-off search script. Each run
reads the survey config, retrieves metadata, normalizes/deduplicates/scores it
deterministically, persists everything to a local SQLite source-of-truth,
publishes the static-site data, and records enough state (`query_state`, run
history, caches, merge/reject logs) that the **next** run can adapt by fixed
rules.

The diagram below is TikZ/LaTeX. Compile it with any LaTeX toolchain
(`pdflatex`/`lualatex` on the `standalone` document, or drop the `tikzpicture`
into an existing document with the listed libraries). Layout is top-to-bottom for
the happy path (left column), with a right-hand column of fail-soft handlers and
a dashed feedback edge that closes the loop.

```latex
\documentclass[border=8pt]{standalone}
\usepackage{tikz}
\usetikzlibrary{arrows.meta, positioning, shapes.geometric}
\begin{document}
\begin{tikzpicture}[
  font=\small\sffamily,
  node distance=7mm and 24mm,
  proc/.style ={rectangle, rounded corners=2pt, draw=blue!55, fill=blue!6,
                text width=34mm, align=center, minimum height=8mm, inner sep=3pt},
  io/.style   ={rectangle, draw=teal!60, fill=teal!10,
                text width=34mm, align=center, minimum height=8mm, inner sep=3pt},
  dec/.style  ={diamond, aspect=2.2, draw=orange!75, fill=orange!12,
                text width=17mm, align=center, inner sep=1pt},
  store/.style={cylinder, shape border rotate=90, aspect=0.28, draw=violet!60,
                fill=violet!8, text width=24mm, align=center, minimum height=12mm,
                inner sep=2pt},
  fail/.style ={rectangle, rounded corners=2pt, draw=red!60, fill=red!6,
                text width=40mm, align=center, font=\scriptsize, inner sep=3pt},
  flow/.style ={-{Stealth[length=2mm]}, thick, draw=black!75},
  soft/.style ={-{Stealth[length=2mm]}, thick, dashed, draw=red!60},
  link/.style ={{Stealth[length=1.6mm]}-{Stealth[length=1.6mm]}, dashed, draw=violet!60},
  back/.style ={-{Stealth[length=2mm]}, thick, dashed, draw=teal!70},
]
% ---- happy-path spine (top to bottom) ----
\node[io]                     (cfg) {Load \texttt{survey\_config.json}};
\node[proc, below=of cfg]     (q)   {Build deterministic queries};
\node[proc, below=of q]       (plan){Loop-control: plan adjustments};
\node[proc, below=of plan]    (api) {Query Semantic Scholar};
\node[proc, below=of api]     (nv)  {Normalize \& validate};
\node[proc, below=of nv]      (dd)  {Intra-run dedupe};
\node[proc, below=of dd]      (rs)  {Resolve identity vs.\ DB};
\node[proc, below=of rs]      (sc)  {Score \texttt{baseline\_lexical\_v1}};
\node[dec,  below=of sc]      (ft)  {score $\ge$ min?};
\node[proc, below=of ft]      (ps)  {Persist papers / rejects / merges / source hits};
\node[proc, below=of ps]      (tc)  {Target-paper check};
\node[proc, below=of tc]      (qs)  {Update \texttt{query\_state}};
\node[proc, below=of qs]      (pb)  {Publish NDJSON \& site JSON};
\node[io,   below=of pb]      (rt)  {Artifacts \& \texttt{ManagerRunResult}};
% ---- local data store ----
\node[store, left=20mm of rs] (db)  {SQLite\\\texttt{baseline.sqlite3}\\+ \texttt{api\_cache}};
% ---- fail-soft handlers (right column) ----
\node[fail, right=of cfg] (e1) {missing / invalid $\rightarrow$ status \texttt{failure}, stop};
\node[fail, right=of api] (e2) {429 / 5xx / timeout $\rightarrow$ backoff 2,5,15\,s ($\times$4) $\rightarrow$ skip query, continue};
\node[fail, right=of nv]  (e3) {malformed record $\rightarrow$ reject \texttt{malformed\_metadata}};
\node[fail, right=of ft]  (e4) {no title / below threshold / outside timeline $\rightarrow$ reject + evidence};
\node[fail, right=of ps]  (e5) {DB error $\rightarrow$ record error, continue};
\node[fail, right=of pb]  (e6) {publish error $\rightarrow$ status \texttt{partial\_success}};
% ---- main flow ----
\draw[flow] (cfg)--(q);   \draw[flow] (q)--(plan); \draw[flow] (plan)--(api);
\draw[flow] (api)--(nv);  \draw[flow] (nv)--(dd);  \draw[flow] (dd)--(rs);
\draw[flow] (rs)--(sc);   \draw[flow] (sc)--(ft);
\draw[flow] (ft)--(ps) node[midway, fill=white, font=\scriptsize] {accept};
\draw[flow] (ps)--(tc);   \draw[flow] (tc)--(qs);  \draw[flow] (qs)--(pb);
\draw[flow] (pb)--(rt);
% ---- soft / error edges ----
\draw[soft] (cfg)--(e1); \draw[soft] (api)--(e2); \draw[soft] (nv)--(e3);
\draw[soft] (ft)--(e4) node[midway, fill=white, font=\scriptsize] {reject};
\draw[soft] (ps)--(e5); \draw[soft] (pb)--(e6);
% ---- data-store links ----
\draw[link] (db.north) to[out=90,in=180]  (api.west);
\draw[link] (db.east)  --                  (rs.west);
\draw[link] (db.south) to[out=-90,in=180]  (ps.west);
% ---- feedback loop (closes the loop for the next run) ----
\draw[back] (qs.west) to[out=180,in=180,looseness=1.5]
      node[left, align=center, font=\scriptsize] {informs\\next run} (plan.west);
\end{tikzpicture}
\end{document}
```

**How to read it.** Solid black = the happy path. Dashed red = fail-soft exits
(a problem is recorded and the run keeps going wherever possible). Dashed violet
= reads/writes against the SQLite source-of-truth (including the response cache).
Dashed teal = the feedback edge: this run's per-query outcomes are written to
`query_state`, which the *next* run's loop-control reads when it plans
adjustments.

---

## Stage-by-stage

Each stage maps to one module under `app/architectures/baseline/`.

1. **Load config** (`app/config.py`). Parses `survey_config.json` into a
   `SurveyConfig`. Documented fields are first-class; optional blocks
   (`baseline`, `semantic_scholar`, `target_papers`, `evaluation`) are read with
   safe defaults so missing keys never raise. A missing/invalid file is the only
   hard-stop failure.

2. **Build queries** (`query_builder.py`). Deterministic, no LLM. Rules: the
   `topic_overview`, then each `research_question`, then each `query_hint`, then
   one **combined** query built from the top non-stopword tokens (ranked by
   frequency, ties broken alphabetically). Queries are cleaned (whitespace /
   control chars / length), deduplicated case-insensitively, and capped at
   `baseline.max_queries`. The original strings are preserved in artifacts.

3. **Loop-control: plan adjustments** (`loop_control.py`). Reads `query_state`
   from prior runs and decides deterministic adjustments before any network call
   (see [Loop engineering](#loop-engineering)).

4. **Query Semantic Scholar** (`semantic_scholar_client.py`). Synchronous
   `urllib` client with timeout, retry + exponential backoff, 429/5xx handling,
   invalid-JSON handling, optional API key, polite inter-request pacing, and a
   **raw-response cache** (SQLite `api_cache` + `data/baseline/raw_cache/`). A
   cache hit replays the exact prior response, which is what makes a run
   reproducible given a fixed cache.

5. **Normalize & validate** (`normalizer.py`, `validator.py`). Map each raw
   record to the shared `PaperCandidate` shape (never inventing data, preserving
   the raw object), then lightly repair (trim/collapse) and flag unrecoverable
   records for rejection. Missing abstract or PDF is **not** a rejection reason.

6. **Intra-run dedupe** (`deduper.py`). Collapse duplicates returned across
   queries by stable `paper_id`, merging metadata with "never overwrite good
   data with null" rules (keep the longer title/abstract, richer author list,
   fill missing identifiers, keep existing PDF URLs, take latest citation
   counts).

7. **Resolve identity vs. DB** (`deduper.py` + `db.py`). Match each candidate
   against existing papers using identity priority — **DOI → arXiv → Semantic
   Scholar id → corpusId → title/year/first-author fingerprint** — and either
   merge into the existing paper (recording a `MergeEvent`) or mark it new.

8. **Score** (`scorer.py`). Transparent lexical + metadata formula, method
   `baseline_lexical_v1`, all components normalized to `[0,1]` and stored on the
   record so any decision is explainable:

   ```text
   score = 0.35 * title_keyword_overlap
         + 0.30 * abstract_keyword_overlap
         + 0.15 * query_phrase_match
         + 0.10 * recency_score
         + 0.05 * identifier_score
         + 0.05 * citation_score   (log-normalized, capped)
   ```

9. **Filter** (`filters.py`). Accept iff title present, score ≥
   `min_relevance_score`, and (when `baseline.strict_timeline` is on) the year is
   inside the window. Every reject is written with a closed-vocabulary reason and
   evidence (threshold, matched/missing terms). Accepted papers are sorted
   deterministically (score desc, then `paper_id`).

10. **Persist** (`db.py`). One transaction: upsert accepted papers (insert new /
    update existing), append `source_hits`, record `merge_events`, and record
    `rejects`. All writes are transactional; file exports are atomic
    (`*.tmp` + `os.replace`).

11. **Target-paper check** (`target_check.py`). For each configured target,
    resolve by DOI → S2 id → arXiv → exact normalized title and report whether it
    was found/accepted. Produces `target_*` metrics for accuracy evaluation.

12. **Update `query_state`** (`loop_control.py`). Persist this run's per-query
    outcomes (candidates / accepted / duplicates / errors and the
    consecutive-zero-accept counter) — the feedback edge in the diagram.

13. **Publish** (`publisher.py`). Export the canonical SQLite state to
    `data/*.ndjson`, `data/changelog.md`, `data/system_status.json`, and
    `site/data/*.json`, attaching a `provenance` block per paper (which
    architectures/sources/queries observed it).

14. **Artifacts & result** (`pipeline.py`, `metrics.py`). Write per-run artifacts
    under `data/baseline/run_artifacts/{run_id}/` and a comparison record under
    `data/comparison/runs/`, then return a flat `ManagerRunResult`.

---

## Situation handling

The baseline **fails soft**: one bad query or candidate must never kill the run,
and publishing problems must never corrupt existing output. Errors are classified
(`app/architectures/baseline/errors.py`) and handled by policy.

| Situation | Detection | Response | Run status effect |
|---|---|---|---|
| Config missing / invalid JSON | `ConfigError` at load | Stop immediately; emit a failure result | `failure` |
| No queries generated | empty query list | Stop with a clear error | `failure` |
| Rate limited (HTTP 429) | `RateLimitError` | Backoff `2s, 5s, 15s` across up to 4 attempts; if still failing, **skip that query** and continue | `partial_success` |
| Server error (5xx) / timeout / network | `APIResponseError`, `URLError`, `TimeoutError` | Same retry/backoff, then skip the query | `partial_success` |
| Invalid JSON body | `APIResponseError` | Treated as a failed attempt; retried then skipped | `partial_success` |
| Malformed / unrecoverable record | validator verdict | Reject as `malformed_metadata` (kept with evidence); continue | unaffected if other data processed |
| Missing title / below threshold / outside timeline | `filters` | Reject with reason + evidence; continue | normal |
| Duplicate of an existing paper | identity match in `db` | Merge (no new row), record a `MergeEvent` | normal |
| Candidate cap reached (`MAX_CANDIDATES_PER_RUN`) | counter | Stop crawling further queries, log it (no silent truncation) | `partial_success` |
| SQLite write error | `DatabaseWriteError` | Record the error, continue | `partial_success` |
| Publish/export error | `PublishError` / `ExportError` | Report; never overwrite good files (atomic writes) | `partial_success` |

Final status is one of `success`, `partial_success` (some data processed but
recoverable errors occurred), or `failure`. A summary is always written, even on
partial failure. Cache hits and per-query/error counts are recorded in metrics so
a throttled run is still auditable.

---

## Loop engineering

The baseline is engineered as a **repeatable, self-improving loop** governed by a
transparent state machine — explicitly *not* a hidden agent. State persists
across runs in SQLite:

- `query_state` — per query: totals (candidates / accepted / duplicates /
  errors), `consecutive_zero_accept`, and `last_run_at`.
- `runs` — per run: generated queries, metrics, errors, summary.
- `api_cache` — raw responses keyed by a hash of (endpoint + params).
- `merge_events` / `source_hits` — duplicate and provenance history.

**The loop (one turn of the diagram's feedback edge):**

```text
plan_adjustments(query_state)   # before crawling — adapt this run
        │
        ▼
   run the pipeline             # crawl → … → persist
        │
        ▼
record_query_outcomes(...)      # after persisting — write query_state
        │
        └────────────► feeds the next run's plan_adjustments
```

**Deterministic rules** (`loop_control.py`; thresholds are named constants):

- **Dead-query deprioritization** *(active)* — a query with
  `consecutive_zero_accept ≥ 3` is dropped from the upcoming run's plan (with a
  guard so the run is never left with zero queries). This stops wasting API calls
  on queries that never contribute accepted papers.
- **Prefer recency when duplicate-heavy** *(reserved hook)* — when a run's
  duplicate rate exceeds `0.80`, favor newer publication-date filtering next time.
- **Enable hints + combined when yield is low** *(reserved hook)* — when accepted
  count falls below the expected minimum, ensure the hint and combined queries
  are included.
- **Throttle on frequent 429s** *(reserved hook)* — when rate-limit events exceed
  the threshold in a run, reduce request rate / concurrency.
- **Target fallback lookups** — when configured `target_papers` are not found,
  fall back to DOI / S2-id / arXiv / exact-title / quoted-title lookups.

Every rule is a simple threshold check with a human-readable note attached to the
run's adjustments, so a contributor can always explain *why* a run behaved as it
did. New rules belong here, never scattered through the pipeline.

---

## Determinism

Given the same config, the same database state, and the same API responses, the
baseline produces the same decisions:

- query generation, scoring, filtering, and identity/`paper_id` are pure
  functions of their inputs (fixed weights, fixed stopwords, deterministic
  tie-breaks);
- outputs are deterministically sorted before every write;
- the `api_cache` replays identical responses, removing network nondeterminism on
  re-runs;
- IDs are stable (`doi:` / `arxiv:` / `s2:` / `corpus:` / `fp:` prefixes).

No LLM is used for planning, query expansion, relevance judgment, summarization,
tool selection, publishing, or error recovery. No embeddings are used in v1 (a
fixed, non-LLM embedding scorer may be added later strictly as a scoring
function).

---

## Outputs

Canonical, shared across architectures:

```text
data/papers.ndjson          data/run_history.ndjson     data/system_status.json
data/rejects.ndjson         data/changelog.md
site/data/*.json            site/data/changelog.md
```

Baseline-specific (debugging / evaluation):

```text
data/baseline/baseline.sqlite3
data/baseline/raw_cache/{hash}.json
data/baseline/run_artifacts/{run_id}/
    generated_queries.json   scored_candidates.json    accepted_candidates.json
    rejected_candidates.json merge_events.json         target_check.json
    metrics.json             errors.json               final_report.json
data/comparison/runs/{run_id}.json
```

Open `site/index.html` to browse accepted papers (filter by title / architecture;
reads `site/data/papers.json` and `system_status.json`).

---

## Configuration reference

`data/survey_config.json` — used fields:

| Field | Meaning |
|---|---|
| `topic_overview` | Primary topic; seeds a query and the combined query |
| `research_questions` | One query each |
| `question_context` | Free-text context (not used for hard filtering) |
| `query_hints` | One query each |
| `timeline_from_year` / `timeline_to_year` | Recency scoring; strict filter when enabled |
| `min_relevance_score` | Accept threshold |
| `target_papers` | Optional accuracy targets (`title`/`doi`/`arxiv_id`/`semantic_scholar_id`/`must_find`) |
| `baseline.*` | `max_queries`, `max_results_per_query`, `min_title_tokens`, `strict_timeline`, `enable_raw_cache`, … |
| `semantic_scholar.fields` | Fields requested from the API |

Environment variables (all optional):

```text
SEMANTIC_SCHOLAR_API_KEY     SEMANTIC_SCHOLAR_BASE_URL     REQUEST_TIMEOUT_S=30
MAX_CANDIDATES_PER_RUN=200   TOP_K_PER_QUERY=50            BASELINE_SQLITE_PATH=data/baseline/baseline.sqlite3
```

---

## CLI & dry-run semantics

```bash
python -m app.run --architecture {baseline|single-agent|multi-agent} \
    [--config data/survey_config.json] [--dry-run] [--verbose]
```

`--dry-run` runs the full pipeline against an **in-memory** database and writes
no files (artifacts, NDJSON, and site data are all skipped) — useful for testing
logic and confirming determinism without side effects. The baseline never commits
or pushes to git.

---

See `CLAUDE.md` for the full specification. The baseline is intended to be
**strong, transparent, reproducible, and boring** — so that any improvement from
the agent architectures has to be earned rather than assumed.
