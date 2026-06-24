# Dynamic-LR: Agent Context from Recent Literature-Review Systems

**Purpose.** This document converts three recent papers on AI-assisted systematic reviewing into implementation constraints and design guidance for Dynamic-LR. It is intended to be read by coding agents before they modify retrieval, screening, clustering, persistence, or evaluation code.

**Project framing.** Dynamic-LR is a literature-review system with three architectures: `baseline`, `single-agent`, and `multi-agent`. Its scientific purpose is to compare LLM-enabled sequential decision-making with a strong deterministic, API-driven baseline. The system is not merely a survey-writing chatbot. It must preserve a reusable, auditable local corpus and expose every consequential decision.

**Non-negotiable baseline constraint.** The `baseline` must remain deterministic and non-LLM. It must not use an LLM for planning, query generation, source selection, relevance verification, summarization, or publishing decisions. It reads the same `survey_config.json` fields as the agentic architectures and produces comparable artifacts. A fixed query template, transparent metadata filters, deterministic deduplication, deterministic relevance scoring, and versioned run artifacts are preferred over any hidden model-based decision.

## 1. What the three papers establish—and what they do not

The papers collectively support a few architectural claims:

1. Literature review automation benefits from separating retrieval, screening, topic organization, synthesis, and verification rather than treating the workflow as one long prompt.
2. A review system becomes more credible when it preserves provenance from every high-level claim back to paper-level evidence and when users can inspect or override consequential decisions.
3. Typed intermediate artifacts, multi-round workflows, caching, retries, and resumable runs are more reusable than an unstructured agent transcript.
4. Corpus size is not free. Flat, single-pass synthesis degrades when the corpus becomes large; hierarchical aggregation is needed.

They do **not** establish that multi-agent systems are automatically better in every domain, that title similarity alone is a safe duplicate rule, or that an LLM judge can serve as the sole quality evaluator. Their empirical settings are narrow and partly abstract-only. Treat their quantitative claims as design evidence, not as direct performance guarantees for Dynamic-LR.

## 2. Architectural stance for Dynamic-LR

### 2.1 One orchestrator; only genuine subagents

Dynamic-LR should use one orchestration authority. It owns the run state, acceptance criteria, budgets, checkpoints, and publication of artifacts. A component is a **subagent** only when it has a bounded goal, local decision authority, its own tools, a typed input/output contract, and independent failure/retry behavior. Otherwise it is a module or tool, not an agent.

Recommended topology:

```text
SurveyConfig + RunPolicy
        |
        v
Orchestrator ----------------------------------------------------+
        |                                                        |
        +--> Retrieval service / Search subagent (when agentic)  |
        +--> Normalization + deduplication service               |
        +--> Screening service / Reviewer subagent (when agentic)|
        +--> Topic-mining service or subagent                    |
        +--> Evidence & synthesis subagent                       |
        +--> Verification / quality-control subagent             |
        |                                                        |
        +--> SQLite corpus + raw snapshots + manifests <---------+
```

For the baseline, the same stages exist as deterministic services. Do not simulate agentic behavior with arbitrary pseudo-reasoning merely to make the baseline look similar.

### 2.2 Keep three layers separate

**Acquisition layer:** source queries, raw API payloads, rate limiting, caching, normalization, identifier resolution, and deduplication.

**Curation layer:** relevance decisions, inclusion/exclusion criteria, topic clusters, evidence extraction, contradiction flags, and user overrides.

**Presentation layer:** static site data, searchable corpus views, exports, survey draft, and audit reports.

No presentation artifact may become the only source of truth. The database plus immutable run artifacts are authoritative.

## 3. Canonical data contracts

All architectures should write the same durable records. The exact class names can vary, but the semantics should not.

### 3.1 `PaperRecord`

```json
{
  "paper_key": "canonical internal UUID",
  "identifiers": {
    "doi": null,
    "arxiv_id": null,
    "semantic_scholar_id": null,
    "openalex_id": null
  },
  "title": "...",
  "abstract": "...",
  "authors": [],
  "year": null,
  "venue": null,
  "citation_count": null,
  "open_access_pdf": null,
  "source_metadata": {},
  "first_seen_run_id": "...",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

Keep raw source payloads separately, keyed by source, request fingerprint, and response hash. Normalized fields must never overwrite raw provenance.

### 3.2 `RetrievalEvent`

Every returned candidate needs an append-only retrieval event:

```json
{
  "run_id": "...",
  "query_id": "...",
  "query_text": "...",
  "query_origin": "config|deterministic_template|agent",
  "source": "semantic_scholar|arxiv|openalex",
  "source_rank": 0,
  "retrieved_at": "ISO-8601",
  "raw_payload_hash": "...",
  "cache_status": "hit|miss|stale",
  "paper_key": "..."
}
```

This makes retrieval coverage, source overlap, query effectiveness, and later debugging measurable.

### 3.3 `ScreeningDecision`

```json
{
  "paper_key": "...",
  "run_id": "...",
  "stage": "metadata_filter|baseline_score|agent_review|human_override",
  "decision": "include|exclude|needs_review|defer",
  "score": 0.0,
  "criteria_version": "...",
  "brief_rationale": "Concise evidence-tied explanation, not hidden reasoning.",
  "supporting_fields": ["title", "abstract", "year"],
  "decision_source": "rule|model|human",
  "reviewer_id": "...",
  "created_at": "ISO-8601"
}
```

Store concise, inspectable rationales and field references. Do not store or require free-form chain-of-thought.

### 3.4 `EvidenceUnit` and provenance graph

An `EvidenceUnit` is a claim-sized, paper-grounded record: finding, method, population/domain, result, limitation, or contradiction. Each unit must point to its `paper_key` and, when available, exact source span or metadata field. Higher-level cluster notes and survey statements must have explicit parent links to these units.

```text
PaperRecord --> EvidenceUnit --> ClusterSynthesis --> SurveySection --> FinalSurveyClaim
```

This is the implementation-level analogue of InsightAgent's provenance tree. It is more valuable than a polished narrative because it allows correction and regeneration without losing the corpus history.

### 3.5 `RunManifest`

Each run needs an immutable manifest containing: architecture, Git commit, config hash, provider/model metadata for agentic runs, source versions, query plan, random seed, budget, cache policy, start/end times, artifacts written, failures, retry counts, and final status. Use atomic writes and preserve failed manifests.

## 4. Retrieval, uniqueness, and local database policy

### 4.1 Retrieval is a recall-oriented stage

Use `survey_config.json` as the authoritative input: `topic_overview`, `research_questions`, `question_context`, `query_hints`, time range, and `min_relevance_score`.

- **Baseline:** create a fixed, versioned query set from these fields. Query expansion must be template/rule based and reproducible.
- **Agentic architectures:** may propose query expansions, but they must be logged as `query_origin=agent`, deduplicated, bounded by a budget, and replayable from the manifest.
- Apply cheap source-native filters first: year range, language where available, document type, open-access flag, venue constraints, and missing-abstract rules. LatteReview explicitly warns that database filters and careful queries should handle conditions that do not require AI.

### 4.2 Deduplication must be conservative

Agentic AutoSurvey uses a 90% title-similarity threshold. Do **not** copy this as the sole merge rule. It risks collapsing distinct papers with short, generic, revised, or near-identical titles.

Use this order:

1. Exact identifiers: DOI, arXiv ID, Semantic Scholar ID, OpenAlex ID.
2. Exact normalized title plus strong author/year agreement.
3. Fuzzy-title candidates with author/year/venue checks. Auto-merge only at a deliberately high, tested confidence. Otherwise label `possible_duplicate` for inspection.
4. Preserve every merged source record and merge rationale.

A false merge is usually worse than a retained duplicate because it silently destroys coverage and provenance.

### 4.3 Caching, errors, and resumability

Adopt the operational lessons of Agentic AutoSurvey:

- cache raw API responses with an explicit TTL and a request fingerprint;
- cache computed embeddings by canonical paper key plus embedding-model version;
- use exponential backoff with jitter on rate limits;
- retry transient requests under a bounded policy;
- allow a safe fallback to cached results or an alternate source;
- checkpoint after each durable stage;
- distinguish `partial_success`, `retryable_failure`, `permanent_failure`, and `skipped_by_policy`;
- never silently drop a source, query, or paper because of an exception.

The user-facing dashboard can remain minimal, but it must expose run status, candidate/accepted/rejected counts, source coverage, duplicates, and failure summaries.

## 5. Curation and agent behavior

### 5.1 Screening workflow

Model the review as rounds, following LatteReview's useful abstraction:

```text
Round 0: deterministic metadata filtering
Round 1: relevance scoring / title-abstract screening
Round 2: resolve ambiguous or conflicting records
Round 3: structured evidence extraction from included records
Round 4: cluster-level synthesis and verification
```

Agentic screening may use two reviewers plus a resolver only when disagreement resolution is genuinely useful. A fixed threshold should not be disguised as a panel of agents. The baseline should use the same status states (`include`, `exclude`, `needs_review`) so outcomes are comparable.

### 5.2 Human correction is data, not a chat aside

InsightAgent's strongest transferable idea is not its 2D interface; it is making user intervention consequential and traceable. A human override must be stored as a new decision event, never overwrite prior decisions, and invalidate or queue downstream artifacts affected by the change.

Minimum interaction support for Dynamic-LR:

- mark a paper as include/exclude/needs-review;
- change or add a criterion;
- flag a missing key work;
- correct a cluster label or evidence claim;
- rerun only the affected downstream stages.

A full visual map is deferred. Start with a transparent table, paper detail page, filters, run timeline, and evidence links.

### 5.3 Topic clustering

Cluster only after candidate normalization and screening. A practical deterministic pipeline is:

1. construct representation from title + abstract;
2. embed using a versioned model or a deterministic sparse representation;
3. choose `k` using silhouette score, elbow diagnostics, or a fixed policy documented in the manifest;
4. create stable cluster IDs and report confidence/size;
5. generate labels from transparent keywords or agentic labels with source terms saved;
6. store cross-cluster similarity edges for later synthesis.

Clustering is an organizing aid, not a relevance decision. Do not exclude papers because they occupy a small, inconvenient, or poorly separated cluster.

### 5.4 Evidence-first synthesis

Avoid direct `papers -> final survey` generation. Use hierarchical synthesis:

```text
accepted papers
  -> evidence units
  -> cluster evidence cards
  -> section drafts with citations
  -> cross-cluster comparison / conflict pass
  -> final narrative + limitations + coverage report
```

This prevents large-corpus compression from erasing the long tail of relevant papers—the failure reported by Agentic AutoSurvey. Preserve an appendix/export listing accepted but uncited papers, with an explicit reason when a paper is not cited in the main narrative.

## 6. Quality assurance and evaluation

### 6.1 Never use a single LLM judge as the final authority

Use a layered quality check:

1. **Rule-based validation:** required fields, valid identifiers, citation targets resolve, no cited paper is excluded, no section lacks evidence, duplicate conflicts are surfaced.
2. **Model-assisted verification:** compare a claim with its linked evidence units; flag unsupported, contradictory, or overly broad claims.
3. **Human evaluation:** blind sample-based assessment when reporting research results, especially for relevance accuracy and synthesis quality.

The 12-dimensional rubric in Agentic AutoSurvey is a useful starting point. Dynamic-LR should report at least: coverage, citation/evidence traceability, factual faithfulness, cross-paper synthesis, organization, limitations/bias disclosure, and user-control/auditability.

### 6.2 Fair baseline-versus-agent comparison

A live API query is not a fair reproduction condition. Use two complementary comparisons:

**Frozen-corpus comparison.** Build one normalized, deduplicated corpus snapshot, then feed the same snapshot and criteria to baseline, single-agent, and multi-agent flows. This isolates screening, organization, and synthesis decisions.

**End-to-end retrieval comparison.** Run each architecture from the same config and time window. Record source-specific coverage, query count, unique candidates, deduplication behavior, accepted records, runtime, API calls, cache hits, retries, and failures.

Report these metrics where labels are available:

```text
Retrieval:     recall, precision, F1, source coverage, duplicate rate, false-merge rate
Screening:     include/exclude accuracy, uncertainty rate, escalation rate, false-negative rate
Synthesis:     cited-paper coverage, evidence-support precision, cluster coverage, human blind rating
Operations:    wall-clock time, API calls, tokens/cost for agentic runs, retry/failure rate, resume success
Reproducibility: manifest completeness, run replay success, artifact checksum agreement
```

Do not compare only prose quality. A system that writes a good-looking review but cannot reproduce source inclusion, citations, and run state is not a credible research pipeline.

## 7. Phased implementation priorities

### P0 — correctness and auditability

Implement canonical paper IDs, raw payload snapshots, normalization, conservative deduplication, SQLite persistence, run manifests, atomic writes, and failure taxonomy.

### P1 — a strong baseline and comparable outputs

Implement deterministic query templates, source adapters, score/filter policy, accepted/rejected/ambiguous outputs, static-site data export, and `python -m app.run --architecture baseline --dry-run`.

### P2 — agentic review rounds

Add the orchestrator, typed reviewer contracts, human overrides, evidence units, verification, and manifest-level model/provider metadata.

### P3 — semantic organization and survey production

Add versioned embeddings, topic clusters, cluster cards, hierarchical synthesis, coverage reports, and cross-cluster comparison.

### P4 — interface and optional advanced interaction

Add minimal review dashboard improvements first. Only add an interactive corpus map when the database/provenance layer already supports it and a user need is demonstrated.

## 8. Paper-specific lessons

### InsightAgent (Qiu et al., 2025)

**Adopt:** semantic partitioning before parallel work; isolated local subdomain memories; provenance graph; human correction that triggers reflection/revision; evaluation beyond final prose quality.

**Adapt carefully:** its radial map and nearest-neighbor exploration are interface/retrieval strategies, not universal defaults. Dynamic-LR should begin with searchable records and explicit pipeline state rather than a bespoke visual canvas.

**Do not overgeneralize:** the study used biomedical reviews, nine evaluators, and title/abstract-only inputs. It also acknowledges limits in quantitative analysis and evidence weighting.

### Agentic AutoSurvey (Liu et al., 2025)

**Adopt:** explicit role decomposition, multi-source retrieval, caching, retry/fallback behavior, clustering diagnostics, and a multi-dimensional quality rubric.

**Adapt carefully:** query expansion must be budgeted and logged; clustering labels need provenance; long corpora require hierarchy rather than one final compression pass.

**Do not copy:** title-similarity-only deduplication or self-reported quality scores as proof. The paper's discussion reports a 1,334-paper RLHF corpus while an earlier result figure reports 443 retrieved papers; the relationship is not clearly resolved in the text. Treat it as a reminder to make corpus accounting unambiguous in Dynamic-LR.

### LatteReview (Rouzrokh et al., 2025)

**Adopt:** provider abstraction, typed inputs/outputs, round-based workflow schema, conditional escalation of disagreements, asynchronous batch execution, and structured extraction.

**Adapt carefully:** the framework is a flexible toolkit, not a single validated workflow. Its results vary sharply by task, inclusion prevalence, and threshold; a high AUC does not eliminate low precision in rare-inclusion settings.

**Do not copy:** unnecessary agent proliferation. Let a function remain a function when it has no independent goal or local decision process.

## 9. Working rules for coding agents

1. Read existing `CLAUDE.md`, config schema, and architecture boundaries before editing.
2. Do not break `single-agent` or `multi-agent` while adding baseline functionality.
3. Do not introduce an LLM dependency into `baseline`, directly or indirectly.
4. Preserve all raw metadata and append decision history; never silently overwrite evidence or prior choices.
5. Produce typed, serializable artifacts at every stage. Persist concise decision rationales, not hidden reasoning.
6. Make every external call observable: source, query, response status, cache state, retry count, and timing.
7. Keep source-specific adapters behind stable interfaces.
8. Add tests for exact-ID merges, fuzzy duplicate candidates, failure/resume behavior, config hashing, and artifact compatibility across architectures.
9. Keep the dashboard minimal and audit-oriented. A clean table with real provenance beats a sophisticated visualization with opaque state.
10. When uncertain, favor reproducibility, reversibility, and explicit escalation over autonomous deletion or forced synthesis.

## References

1. Qiu, R., Chen, S., Su, Y., Yen, P.-Y., & Shen, H.-W. (2025). *Completing A Systematic Review in Hours instead of Months with Interactive AI Agents* (arXiv:2504.14822v2). https://arxiv.org/abs/2504.14822
2. Liu, Y., Wu, Y., Zhang, D., & Sun, L. (2025). *Agentic AutoSurvey: Let LLMs Survey LLMs* (arXiv:2509.18661v1). https://arxiv.org/abs/2509.18661v1
3. Rouzrokh, P., Khosravi, B., Rouzrokh, P., & Shariatnia, M. (2025). *LatteReview: A Multi-Agent Framework for Systematic Review Automation Using Large Language Models* (arXiv:2501.05468v2). https://arxiv.org/abs/2501.05468
