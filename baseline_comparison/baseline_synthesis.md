# Baseline Architecture Synthesis
# 基线架构综合分析

**Prepared / 编制日期:** 2026-06-24  
**Systems compared / 对比系统:** Dynamic-LR · PRS (cherryann518) · PF (WoosungLim01)  
**Grounded in / 依据文献:** InsightAgent (arXiv:2504.14822) · Agentic AutoSurvey (arXiv:2509.18661) · LatteReview (arXiv:2501.05468)

---

## Purpose / 目的

This document provides:
1. An exhaustive step-by-step comparison of all three baseline systems.
2. A per-step verdict on which implementation is most stable and efficient.
3. A record of which improvements have been adopted into Dynamic-LR and how the architecture was updated.

本文档提供：
1. 三个基线系统的逐步骤详尽对比。
2. 每个步骤中哪种实现最稳定、最高效的评判。
3. 哪些改进已被 Dynamic-LR 采纳，以及架构如何相应更新的记录。

---

## Part 1 — Exhaustive Comparison Table / 第一部分：详尽对比表

> Legend / 图例:  
> ✓ Fully implemented · ◑ Partial / configurable · – Not present · ★ Best in class

### 1.1 Survey Config & Initialisation / 调查配置与初始化

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Config file format / 配置文件格式 | JSON (`survey_config.json`) | JSON (`.env` + config dict) | JSON (`config.json`) |
| Required fields validated / 必填字段验证 | ★ Typed dataclass, safe defaults | Minimal checks | Minimal checks |
| Optional blocks with safe defaults / 可选块安全默认值 | ★ All optional blocks parsed safely | – | – |
| Provider sub-configs / 数据源子配置 | ★ `semantic_scholar`, `arxiv`, `openalex` blocks | `semantic_scholar` only | Hardcoded constants |
| Config versioning & hash / 配置版本与哈希 | ★ `config_hash` in run record | – | – |
| Target papers specification / 目标论文规格 | ★ DOI/S2/arXiv/OA/title per target | – | – |
| Evaluation mode flags / 评估模式标志 | ★ `frozen_corpus_mode`, `target_paper_checks` | – | – |
| Fail-fast on bad config / 配置错误快速失败 | ★ `ConfigError` stops run immediately | Implicit crash | Implicit crash |

---

### 1.2 Query Generation / 查询生成

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Topic → query / 主题→查询 | ★ Yes | ★ Yes | – |
| Research questions → queries / 研究问题→查询 | ★ Yes | – | – |
| Query hints → queries / 查询提示→查询 | ★ Yes | – | ◑ keywords only |
| Combined top-N token query / 组合 top-N 词元查询 | ★ Yes | – | – |
| LLM query refinement / LLM 查询优化 | – | ◑ Ollama, optional | – |
| ML acronym expansion / ML 缩略语扩展 | – | ★ Static lookup table | – |
| Query cleaning (whitespace, control chars) / 查询清洗 | ★ Full | Trim only | `re.sub` punctuation |
| Case-insensitive deduplication / 大小写不敏感去重 | ★ Yes | – | – |
| Query cap (`max_queries`) / 查询数量上限 | ★ Configurable | 1 initial + refinements | `len(keywords)` |
| Stable `query_id` assigned / 稳定查询 ID | ★ Before translation | – | – |
| Deterministic combined query / 确定性组合查询 | ★ Frequency + alpha sort | – | – |
| Query origin recorded / 查询来源记录 | ★ `topic`/`question`/`hint`/`combined` | – | – |

---

### 1.3 Query Translation (Provider-Specific Syntax) / 查询翻译（数据源特定语法）

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Canonical → S2 translation / 规范→S2 翻译 | ★ Separate module, versioned | Passthrough | Passthrough |
| Canonical → arXiv translation / 规范→arXiv 翻译 | ★ `all:term AND all:term` syntax | `ti:` / `all:` fields | Direct keyword |
| Canonical → OpenAlex translation / 规范→OA 翻译 | ★ `search=` + filter params | – | Direct keyword |
| Translation version recorded / 翻译版本记录 | ★ `query_translation_v1` | – | – |
| Provider query logged in artifacts / 提供商查询记录在制品中 | ★ `provider_query_plan.json` | – | – |
| Translation is deterministic / 翻译是确定性的 | ★ Yes | ◑ Yes if no Ollama | ★ Yes |

---

### 1.4 API Client — Semantic Scholar / API 客户端 — Semantic Scholar

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| HTTP library / HTTP 库 | `urllib` (stdlib) | `urllib` (stdlib) | `httpx` (async) |
| Async / 异步 | – (sync) | – (sync) | ★ `httpx.AsyncClient` |
| API key support / API 密钥支持 | ★ Yes | ★ Yes | ★ Yes |
| Retry on 429 / 429 重试 | ◑ Fixed list `[2,5,15]` | ★ Exp backoff + jitter + Retry-After | ◑ Fixed 60s sleep |
| Retry on 5xx / 5xx 重试 | ★ Yes | – | – |
| Exponential backoff / 指数退避 | – | ★ `base × 2^attempt` | – |
| Jitter / 抖动 | – | ◑ `uniform(1.0, 1.5)` (non-deterministic) | – |
| Deterministic jitter / 确定性抖动 | ★ `hash(run_id+provider+fp+attempt)` | – | – |
| Respect `Retry-After` header / 遵守 Retry-After 头 | – | ★ Yes | – |
| Request interval pacing / 请求间隔控制 | ★ Yes | ★ Yes | ★ Yes |
| Timeout / 超时 | ★ Configurable | ★ 30s | ★ 15s |
| Request logging / 请求日志 | ★ Yes | – | Logger only |
| Raw response cache / 原始响应缓存 | ★ SQLite `api_cache` + file | ◑ File per hash, no TTL | – |
| Cache TTL / 缓存 TTL | ★ Yes (`cache_ttl_seconds`) | – | – |
| Pagination / 分页 | ★ Yes, bounded | ★ Yes, `MAX_PAGES_PER_QUERY` | ★ Yes, total count |
| Fields selection / 字段选择 | ★ Configurable list | ★ Fixed set | ★ Fixed set |

---

### 1.5 API Client — arXiv / API 客户端 — arXiv

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Provider implemented / 已实现 | ★ Yes (new) | ★ Yes | ★ Yes |
| Response format / 响应格式 | Atom XML | Atom XML | Atom XML |
| XML parser / XML 解析器 | `xml.etree.ElementTree` | `feedparser` | `feedparser` |
| Async / 异步 | ★ Yes (`httpx`) | – | ★ Yes (`httpx`) |
| Retry / 重试 | ★ Exp backoff + det. jitter | – | – |
| Per-record date filter (never stop on one old entry) / 逐记录日期过滤 | ★ Yes | ◑ Stops on first old record | ◑ Stops on first old record |
| Category filter / 分类过滤 | ★ Configurable | – | – |
| Sort order / 排序方式 | ★ Configurable | `submittedDate desc` | `submittedDate desc` |
| Preserve arXiv ID + version / 保留 arXiv ID 和版本 | ★ Yes, strips version for identity | ★ Yes | ★ Yes |
| Request interval / 请求间隔 | ★ `min_request_interval_seconds` | – | ★ Fixed `asyncio.sleep` |

---

### 1.6 API Client — OpenAlex / API 客户端 — OpenAlex

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Provider implemented / 已实现 | ★ Yes (new) | – | ★ Yes |
| Cursor pagination / 游标分页 | ★ `cursor=*` → `next_cursor` | – | ★ Yes |
| Async / 异步 | ★ Yes (`httpx`) | – | ★ Yes |
| Abstract inverted-index reconstruction / 倒排索引摘要重建 | ★ Sort positions, deterministic | – | ★ Yes |
| Preserve original inverted-index ref / 保留原始倒排索引引用 | ★ Yes (audit trail) | – | – |
| Retracted/paratext filtering / 撤回/辅文过滤 | ★ Configurable | – | ★ Yes |
| Work type filter / 作品类型过滤 | ★ `article`, `preprint`, `review` | – | ◑ All types |
| Polite pool User-Agent / 礼貌池 User-Agent | ★ Yes | – | ★ Yes |
| Response cache / 响应缓存 | ★ SQLite `api_cache` | – | – |

---

### 1.7 Concurrent Multi-Source Fetch / 并发多数据源抓取

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Concurrent fetch / 并发抓取 | ★ `asyncio.gather` | – (sequential) | ★ `asyncio.gather` |
| `return_exceptions=True` (fail-soft) / 软失败 | ★ Yes | – | ★ Yes |
| Per-provider semaphore / 每提供商信号量 | ★ Yes | – | – |
| Global candidate cap / 全局候选上限 | ★ `max_candidates_per_run` | `MAX_PAPERS` | – |
| Provider failure isolation / 提供商故障隔离 | ★ Each failure is a partial error | – | ◑ Exception caught |
| Provider metrics per run / 每次运行的提供商指标 | ★ API calls, cache hits, latency | ◑ Latency only | ◑ Count only |

---

### 1.8 Normalization / 规范化

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Per-provider dispatch / 每提供商分发 | ★ Separate sub-normalizers | ◑ Mostly S2 | ◑ Per-source functions |
| S2 normalization / S2 规范化 | ★ Full (paperId, corpusId, ext IDs, citationCount) | ★ Full | ★ Full |
| arXiv normalization / arXiv 规范化 | ★ ID/version, categories, dates, DOI | ★ Full | ★ Full |
| OpenAlex normalization / OA 规范化 | ★ Work ID, inverted abstract, OA locations | – | ★ Full |
| Abstract reconstruction / 摘要重建 | ★ Sort positions, deterministic, preserve ref | – | ★ Deterministic |
| Document type mapping / 文档类型映射 | ★ `article`/`preprint`/`review` | – | ★ Yes |
| Preserve raw payload reference / 保留原始负载引用 | ★ `source_raw_ref` field | – | – |
| Source rank preserved / 数据源排名保留 | ★ `source_rank` | – | – |
| Normalization failure → typed reject / 规范化失败→类型化拒绝 | ★ `malformed_metadata` | ◑ Skip | ◑ Skip |

---

### 1.9 Validation / 验证

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Missing title → reject / 缺少标题→拒绝 | ★ Yes | ◑ Implicit skip | ★ Yes |
| Blank title → reject / 空标题→拒绝 | ★ Yes | – | – |
| Min title tokens check / 最小标题词元检查 | ★ `min_title_tokens` configurable | – | – |
| Malformed record → typed reject / 格式错误记录→类型化拒绝 | ★ `malformed_metadata` reason | ◑ Generic error | – |
| Missing abstract → retain / 缺少摘要→保留 | ★ Yes | ★ Yes | ★ Yes |
| Missing PDF → retain / 缺少 PDF→保留 | ★ Yes | ★ Yes | – (URL required) |
| Missing year → retain (soft) / 缺少年份→保留（软性） | ★ Configurable | ★ Yes | ★ Yes |
| Conservative repair (trim, collapse WS) / 保守修复 | ★ Yes | ◑ Basic | ◑ Basic |

---

### 1.10 Identity Resolution / 身份解析

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| DOI normalization (lowercase, strip prefix) / DOI 规范化 | ★ Yes | ★ Yes | ★ Yes |
| arXiv ID normalization (strip version) / arXiv ID 规范化 | ★ Yes | ★ Yes | ★ Yes |
| OpenAlex ID normalization / OA ID 规范化 | ★ `W123…` uppercase | – | ★ Yes |
| S2 paperId preserved / S2 paperId 保留 | ★ Yes | ★ Yes | ★ Yes |
| S2 corpusId / 语料库 ID | ★ Yes | ★ Yes | – |
| PMID / ACL / MAG / other IDs | ★ Yes | – | – |
| Title + year fingerprint / 标题+年份指纹 | ★ SHA-256 + first author | ◑ SHA-256, no author | ★ MD5 + first author last name |
| Separate `paper_identifiers` table / 独立标识符表 | ★ Yes (indexed, unique) | – | – |
| Stable `paper_key` prefixes / 稳定 paper_key 前缀 | ★ `doi:` `arxiv:` `openalex:` `s2:` `corpus:` `fp:` | ◑ `doi:` `arxiv:` `s2:` | ◑ `doi:` `arxiv:` `s2:` |
| Priority chain (8 levels) / 优先链（8 级） | ★ DOI→arXiv→OA→S2→corpus→PMID→fingerprint→fuzzy | ◑ 4 levels | ◑ 5 levels |
| Fuzzy title = auto-merge? / 模糊标题=自动合并？ | ★ No — `possible_duplicate` flag | ◑ Auto-merge | ◑ Auto-merge |
| Identity conflict → `needs_review` / 身份冲突→需要审查 | ★ Yes | – | – |

---

### 1.11 Deduplication / 去重

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Intra-run dedup (same paper, multiple queries) / 运行内去重 | ★ Yes | ★ Yes | ★ Yes |
| Cross-session SQLite dedup / 跨会话 SQLite 去重 | ★ Yes | ★ Yes | – |
| Cross-run NDJSON scan / 跨运行 NDJSON 扫描 | – | – | ◑ O(n) full scan |
| Completeness-based merge (pick richer record) / 基于完整性的合并 | ★ Yes (new) | – | ★ Yes |
| Never overwrite non-null with null / 从不用 null 覆盖非 null | ★ Explicit per-field rules | ◑ Keep existing | ◑ Keep existing |
| Keep longer title / 保留更长标题 | ★ Yes | – | – |
| Keep longest abstract / 保留最长摘要 | ★ Yes | – | ★ Yes |
| Citation count → latest observed / 引用数→最新观测值 | ★ max() with source+timestamp | – | – |
| Merge event log / 合并事件日志 | ★ Yes (table) | ★ Yes (table) | – |
| `possible_duplicate` flagging / `possible_duplicate` 标记 | ★ Yes | – | – |
| Multi-source provenance union / 多数据源来源合集 | ★ Yes | ◑ Basic | ◑ Basic |

---

### 1.12 Relevance Scoring / 相关性评分

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Lexical weighted formula / 词法加权公式 | ★ `baseline_lexical_v1` (6 components) | – | – |
| TF-IDF cosine / TF-IDF 余弦 | – | ★ Yes (`sklearn`) | ★ Yes (`sklearn`, ngram 1-2) |
| SBERT semantic (`all-MiniLM-L6-v2`) / SBERT 语义 | – | ★ Yes | ★ Yes |
| FAISS `IndexFlatIP` acceleration / FAISS 加速 | – | – | ★ Yes |
| Embedding persistence cache / 嵌入持久化缓存 | – | – | ★ `.npy` per paper |
| GPU/MPS auto-detection / GPU/MPS 自动检测 | – | – | ★ Yes |
| Recency component / 时间新近性组件 | ★ Linear decay, configurable | ★ `rank_recency` method | ◑ Implicit (date filter) |
| Citation score (log-normalized) / 引用评分（对数规范化） | ★ Yes, capped | – | – |
| Identifier quality score / 标识符质量评分 | ★ Yes | – | – |
| All components stored per paper / 所有组件按论文存储 | ★ 6 named fields | ◑ Method dict | ◑ 2 fields |
| Both scores stored (dual output) / 存储双评分 | ★ Yes (new) | – | ★ Yes |
| Score drives accept/reject / 评分驱动接受/拒绝 | ★ Yes | ★ Yes | ★ Yes |
| Fully deterministic / 完全确定性 | ★ Yes | ★ Yes (SBERT weights fixed) | ★ Yes |
| Score transparency / 分数透明性 | ★ High (named weights) | ◑ Method breakdown | ◑ Two named fields |
| Criteria version string / 标准版本字符串 | ★ `baseline_lexical_v1` | – | – |

---

### 1.13 Filtering & Accept/Reject / 过滤与接受/拒绝

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Staged filters (metadata before score) / 分阶段过滤 | ★ `metadata_filter` → `baseline_score` | – | – |
| Minimum score threshold / 最低评分阈值 | ★ `min_relevance_score` | ★ `SCORE_TOP_MIN` | ★ `min_relevance_score` |
| Batch acceptance gate (top/good/gap) / 批次接受门 | – | ★ `results_acceptable` | – |
| Missing title → reject / 缺少标题→拒绝 | ★ Yes | ◑ Implicit | ★ Yes |
| Missing URL → reject / 缺少 URL→拒绝 | – | – | ◑ Yes (may drop valid preprints) |
| Year / timeline filter / 年份/时间窗口过滤 | ★ Configurable strict/soft | ★ API param + recency | ★ `days_back` at fetch time |
| Retracted work filter / 撤回作品过滤 | ★ Configurable | – | ★ Yes |
| Paratext filter / 辅文过滤 | ★ Configurable | – | ★ Yes |
| Typed reject reason (closed vocabulary) / 类型化拒绝原因 | ★ 10 reason codes | ◑ String only | ◑ String only |
| Reject evidence dict (threshold, terms) / 拒绝证据字典 | ★ Yes | – | – |
| `ScreeningDecision` append-only record / 追加式决策记录 | ★ Yes | – | – |
| Decision source & criteria version / 决策来源和标准版本 | ★ Yes | – | – |
| Accepted papers sorted deterministically / 接受论文确定性排序 | ★ score desc → `paper_key` | – | – |

---

### 1.14 Persistence & Storage / 持久化与存储

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| SQLite primary store / SQLite 主存储 | ★ Yes | ★ Yes | – |
| NDJSON as primary store / NDJSON 作为主存储 | – | – | ◑ (violates provenance rule) |
| `papers` table / papers 表 | ★ Yes | ★ Yes | – |
| `paper_identifiers` table (separate) / 独立标识符表 | ★ Yes (indexed) | – | – |
| `retrieval_events` table / 检索事件表 | ★ Yes | – | – |
| `source_hits` table / 数据源命中表 | ◑ Legacy | ★ Yes | – |
| `screening_decisions` table / 筛选决策表 | ★ Yes (append-only) | – | – |
| `rejects` table / 拒绝记录表 | ◑ Legacy → screening_decisions | ★ Yes | – |
| `merge_events` table / 合并事件表 | ★ Yes | ★ Yes | – |
| `runs` table + `config_hash` + `manifest_json` / 运行表 | ★ Yes | ◑ No manifest | – |
| `api_cache` table (BLOB + content_type) / API 缓存表 | ★ Yes | ◑ File only, no TTL | – |
| `query_state` table / 查询状态表 | ★ Yes | – | – |
| Transactional writes / 事务性写入 | ★ Yes | ★ Batched chunks | – |
| Atomic file exports (tmp + rename) / 原子文件导出 | ★ Yes | – | – |
| Per-run artifact directory / 每次运行制品目录 | ★ `run_artifacts/{run_id}/` | ◑ `outputs/runs/{run_id}/` | – |

---

### 1.15 Publishing & Site Export / 发布与站点导出

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Static site export / 静态站点导出 | ★ `site/data/*.json` | – (Flask only) | ★ Yes |
| NDJSON exports / NDJSON 导出 | ★ Yes | – | ★ Yes |
| Atomic publish (tmp + rename) / 原子发布 | ★ Yes | – | – |
| Changelog / 变更日志 | ★ `data/changelog.md` | – | – |
| System status JSON / 系统状态 JSON | ★ `data/system_status.json` | – | ★ Yes |
| Run history NDJSON / 运行历史 | ★ Yes | – | ★ Yes |
| Per-paper provenance block / 每篇论文来源块 | ★ `architectures_seen`, `sources_seen` | – | ◑ `source_hits` |
| Retro-scoring on publish / 发布时回溯评分 | – | – | ★ Yes |
| Deterministic sort before write / 写入前确定性排序 | ★ Yes | – | – |
| Canonical exports shared across architectures / 跨架构共享规范导出 | ★ Yes | – | – |

---

### 1.16 Loop Control & Automation / 循环控制与自动化

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Designed for repeated runs / 为重复运行设计 | ★ Yes | ◑ Single-run with LLM loop | – |
| State machine (not hidden agent) / 状态机（非隐藏智能体） | ★ Yes | – | – |
| Query priority demotion / 查询优先级降级 | ★ `consecutive_zero_accept ≥ 3` | – | – |
| Duplicate-rate recency filter / 重复率时间新近性过滤 | ★ Hook implemented | – | – |
| Low-yield hint enablement / 低产出提示启用 | ★ Hook implemented | – | – |
| Provider throttle rule / 提供商限流规则 | ★ Hook implemented | – | – |
| LLM-driven refinement / LLM 驱动优化 | – | ★ Ollama (non-deterministic) | – |
| Deterministic multi-round fallback / 确定性多轮回退 | ★ Yes (replaces LLM intent) | – | – |
| Target paper detection chain / 目标论文检测链 | ★ 5-level fallback | – | – |
| Date-gap validation / 日期间隙验证 | ★ Post-fetch check (adapted) | – | ★ `validate_fetch_results` |
| `query_state` tracking / 查询状态追踪 | ★ Cross-run, per-query stats | – | – |
| Loop rule versioning / 循环规则版本化 | ★ `loop_policy_version` on every event | – | – |

---

### 1.17 Metrics & Run Artifacts / 指标与运行制品

| Sub-step / 子步骤 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Structured run result / 结构化运行结果 | ★ `ManagerRunResult` | ◑ Dict | – |
| API call count by source / 按数据源的 API 调用数 | ★ Yes | ◑ Total only | – |
| Cache hit/miss rate by source / 按数据源的缓存命中率 | ★ Yes | – | – |
| Duplicate / merge / possible-duplicate counts / 重复/合并/疑似重复数 | ★ Yes | ◑ Basic | – |
| Cross-source overlap / 跨数据源重叠 | ★ Yes | – | – |
| Target paper found rate / 目标论文查找率 | ★ Yes | – | – |
| Provider latency (ms) / 提供商延迟 | ★ Yes | ◑ Total only | ◑ Total only |
| Score distribution / 评分分布 | ◑ Planned | ★ Yes | ◑ Basic |
| Architecture comparison artifact / 架构对比制品 | ★ `data/comparison/runs/` | – | – |
| Run manifest with git commit / 包含 git commit 的运行清单 | ★ `run_manifest.json` | – | – |
| Frozen corpus snapshot / 冻结语料库快照 | ★ Publisher stub | – | – |

---

## Part 2 — Per-Step Best-Implementation Verdict / 第二部分：每步骤最佳实现评判

The following table summarises which system provides the best implementation at
each high-level stage, and why.

以下表格总结了在每个高层级阶段哪个系统提供了最佳实现，以及原因。

| Stage / 阶段 | Best / 最佳 | Reasoning / 依据 |
|---|---|---|
| **Config loading** / 配置加载 | **Dynamic-LR** | Typed dataclass with safe defaults for all optional blocks; config hash recorded; hard-stop on bad config. / 带有所有可选块安全默认值的类型化数据类；记录配置哈希；配置错误时立即停止。 |
| **Query generation** / 查询生成 | **Dynamic-LR** | Broadest coverage (topic + questions + hints + combined); stable query IDs; deterministic combined query algorithm. / 覆盖最广（主题+问题+提示+组合）；稳定的查询 ID；确定性组合查询算法。 |
| **Query translation** / 查询翻译 | **Dynamic-LR** | Only system with a dedicated provider-syntax translation layer; versioned and artifact-logged. / 唯一具有专用数据源语法翻译层的系统；版本化并记录在制品中。 |
| **S2 API client robustness** / S2 API 客户端健壮性 | **PRS** | Exponential backoff with jitter + `Retry-After` header respect. Dynamic-LR adopts this pattern but adds deterministic jitter on top. / 带抖动的指数退避 + 遵守 `Retry-After` 头。Dynamic-LR 采用此模式但在此基础上增加了确定性抖动。 |
| **arXiv client** / arXiv 客户端 | **Dynamic-LR** | Per-record date filtering (never prematurely stops pagination); configurable categories; deterministic jitter. PF/PRS stop on first old record. / 逐记录日期过滤（不过早停止分页）；可配置类别；确定性抖动。PF/PRS 在遇到第一条旧记录时停止。 |
| **OpenAlex client** / OA 客户端 | **Dynamic-LR / PF tie** | Both implement cursor pagination and abstract reconstruction. Dynamic-LR adds SQLite caching and deterministic jitter; PF adds retro-scoring but no caching. / 两者均实现游标分页和摘要重建。Dynamic-LR 增加了 SQLite 缓存和确定性抖动；PF 增加了回溯评分但无缓存。 |
| **Concurrent multi-source fetch** / 并发多数据源抓取 | **Dynamic-LR / PF tie** | Both use `asyncio.gather` with `return_exceptions=True`. Dynamic-LR adds per-provider semaphore and global candidate cap. / 两者都使用带 `return_exceptions=True` 的 `asyncio.gather`。Dynamic-LR 增加了每提供商信号量和全局候选上限。 |
| **Normalization** / 规范化 | **Dynamic-LR** | Per-provider sub-normalizers with raw payload reference; structured reject on failure; OpenAlex inverted-index reconstruction with audit trail. / 带原始负载引用的每提供商子规范器；失败时结构化拒绝；带审计追踪的 OA 倒排索引重建。 |
| **Identity resolution** / 身份解析 | **Dynamic-LR** | 8-level priority chain including all providers; separate indexed `paper_identifiers` table; fuzzy match → flag only, never auto-merge. / 包含所有提供商的 8 级优先链；独立的索引化 `paper_identifiers` 表；模糊匹配→仅标记，从不自动合并。 |
| **Deduplication** / 去重 | **Dynamic-LR** | Cross-session SQLite (unlike PF) + completeness-based merge (adopted from PF) + per-field explicit rules + `possible_duplicate` safety. / 跨会话 SQLite（与 PF 不同）+ 基于完整性的合并（来自 PF）+ 逐字段显式规则 + `possible_duplicate` 安全机制。 |
| **Relevance scoring** / 相关性评分 | **Dynamic-LR (new)** | Dual output: SBERT primary (adopted from PF) + lexical explainability companion (Dynamic-LR's own). PF stores both; Dynamic-LR adds criteria version and component breakdown. / 双输出：SBERT 主评分（来自 PF）+ 词法可解释性辅助（Dynamic-LR 自有）。PF 存储两者；Dynamic-LR 增加了标准版本和组件分解。 |
| **Filtering** / 过滤 | **Dynamic-LR** | Two-stage `ScreeningDecision` records; 10 typed reject reasons; evidence dict; configurable strict/soft modes; PRS's batch acceptance gate adopted as a metric. / 两阶段 `ScreeningDecision` 记录；10 种类型化拒绝原因；证据字典；可配置严格/软性模式；PRS 的批次接受门作为指标被采用。 |
| **Persistence** / 持久化 | **Dynamic-LR** | Most complete schema (10 tables); atomic writes; `paper_identifiers` table; `retrieval_events` and `screening_decisions` as append-only audit log; `query_state` for loop feedback. / 最完整的架构（10 张表）；原子写入；`paper_identifiers` 表；`retrieval_events` 和 `screening_decisions` 作为追加式审计日志；用于循环反馈的 `query_state`。 |
| **Publishing** / 发布 | **Dynamic-LR** | Atomic writes; canonical exports shared across architectures; provenance block per paper; deterministic sort. PF's retro-scoring is a useful pattern but not applicable to Dynamic-LR's SQLite-primary design. / 原子写入；跨架构共享规范导出；每篇论文来源块；确定性排序。PF 的回溯评分是有用的模式，但不适用于 Dynamic-LR 以 SQLite 为主的设计。 |
| **Loop control** / 循环控制 | **Dynamic-LR** | Only system with a documented state machine; `query_state` cross-run feedback; deterministic fallback rules replacing PRS's LLM loop; date-gap validation adopted from PF. / 唯一拥有文档化状态机的系统；`query_state` 跨运行反馈；替代 PRS 的 LLM 循环的确定性回退规则；从 PF 采用的日期间隙验证。 |
| **Metrics & artifacts** / 指标与制品 | **Dynamic-LR** | Structured `ManagerRunResult`; per-source API metrics; run manifest with git commit; architecture comparison artifacts; frozen corpus support. / 结构化 `ManagerRunResult`；每数据源 API 指标；包含 git commit 的运行清单；架构对比制品；冻结语料库支持。 |

---

## Part 3 — Improvements Adopted and Architecture Updates / 第三部分：已采纳的改进与架构更新

This section records exactly which patterns were borrowed from PRS or PF, what
motivated each decision, and how Dynamic-LR's architecture was updated.

本节准确记录了从 PRS 或 PF 借鉴了哪些模式、每个决策的动机，以及 Dynamic-LR 架构如何相应更新。

---

### 3.1 Three-Provider Coverage / 三数据源覆盖

**Borrowed from / 借鉴自:** PF  
**Motivation / 动机:** PF demonstrated that concurrent three-source fetch increases coverage without proportionally increasing wall-clock time. Semantic Scholar alone misses arXiv preprints and the long tail covered by OpenAlex's free, keyless API.  
PF 证明了并发三数据源抓取可以在不成比例增加挂钟时间的情况下扩大覆盖率。仅靠 Semantic Scholar 会遗漏 arXiv 预印本以及 OpenAlex 免费、无密钥 API 覆盖的长尾论文。

**Architecture update / 架构更新:**
```text
BEFORE: semantic_scholar_client.py  (single sync client)
AFTER:  providers/
          base.py            LiteratureProvider protocol
          semantic_scholar.py  async httpx client
          arxiv.py           Atom XML, per-record date filter
          openalex.py        cursor pagination, inverted-index abstract
          cache.py           BLOB-aware TTL cache
          rate_limit.py      per-provider semaphore
        query_translation.py  canonical → provider-specific syntax
```

---

### 3.2 Async Concurrent Fetch / 异步并发抓取

**Borrowed from / 借鉴自:** PF  
**Motivation / 动机:** PF's `asyncio.gather` pattern with `return_exceptions=True` achieves 2–3× speedup on multi-source runs while guaranteeing that one provider failure never aborts the others.  
PF 的带 `return_exceptions=True` 的 `asyncio.gather` 模式在多数据源运行中实现了 2–3 倍的加速，同时保证一个提供商的失败不会中止其他提供商。

**Architecture update / 架构更新:**
```python
# BEFORE: sequential single-source loop
for query in queries:
    results = s2_client.search(query)

# AFTER: concurrent three-source gather
results = await asyncio.gather(
    s2_provider.search(req_s2),
    arxiv_provider.search(req_arxiv),
    openalex_provider.search(req_oa),
    return_exceptions=True,
)
```

---

### 3.3 Exponential Backoff + Retry-After / 指数退避 + Retry-After

**Borrowed from / 借鉴自:** PRS  
**Motivation / 动机:** PRS's S2 client is the most robust of the three. Its `Retry-After` header handling prevents wasted retry attempts when the server specifies the exact wait time. Exponential backoff prevents synchronized retry storms from parallel workers.  
PRS 的 S2 客户端是三者中最健壮的。其 `Retry-After` 头处理防止了在服务器指定精确等待时间时浪费重试尝试。指数退避防止了并行工作者的同步重试风暴。

**Architecture update / 架构更新:**
```python
# BEFORE: fixed backoff list [2, 5, 15]
# AFTER: PRS pattern + deterministic jitter on top
wait = min(base * (2 ** attempt), max_wait)
jitter = int(sha256(f"{run_id}:{provider}:{fp}:{attempt}".encode())
             .hexdigest(), 16) % max_jitter_ms
await asyncio.sleep(wait + jitter / 1000)
```

The deterministic jitter replaces PRS's `uniform(1.0, 1.5)` random jitter to
preserve full reproducibility.  
确定性抖动替换了 PRS 的 `uniform(1.0, 1.5)` 随机抖动，以保持完整的可重复性。

---

### 3.4 SBERT + FAISS Semantic Scoring / SBERT + FAISS 语义评分

**Borrowed from / 借鉴自:** PF (FAISS + embedding cache), PRS (SBERT model choice)  
**Motivation / 动机:** The lexical formula alone misses semantically related papers that do not share surface tokens ("neural network" vs "deep learning"). SBERT (`all-MiniLM-L6-v2`) is fixed-weight, producing identical vectors for identical input — it does not violate determinism. PF's FAISS `IndexFlatIP` is 10–100× faster than PRS's `cos_sim` on large candidate sets.  
单独的词法公式会遗漏不共享表面词元的语义相关论文（"neural network" vs "deep learning"）。SBERT（`all-MiniLM-L6-v2`）是固定权重的，对相同输入产生相同向量——不违反确定性。PF 的 FAISS `IndexFlatIP` 在大型候选集上比 PRS 的 `cos_sim` 快 10–100 倍。

**Architecture update / 架构更新:**
```text
BEFORE: scorer.py  baseline_lexical_v1 only
AFTER:  scorer.py  SBERT primary score  +  baseline_lexical_v1 explainability companion
        Both scores stored per paper:
          sbert_score        (drives accept/reject)
          lexical_score      (drives reject evidence and audit trail)
          score_components   (6 named lexical fields)
          criteria_version   "baseline_lexical_v1" / "sbert_v1"
```

---

### 3.5 Completeness-Based Merge Selection / 基于完整性的合并选择

**Borrowed from / 借鉴自:** PF  
**Motivation / 动机:** PF's `_completeness_score` (counts non-null fields) picks the richer of two matching records as the merge base, then fills missing fields from the other. Dynamic-LR previously always kept the existing record as canonical, which silently preserved poorer metadata if the first-seen record happened to be sparse.  
PF 的 `_completeness_score`（统计非空字段）将两条匹配记录中较丰富的一条作为合并基础，然后从另一条填充缺失字段。Dynamic-LR 之前总是保留现有记录作为规范，如果第一次看到的记录恰好很稀疏，则会静默保留较差的元数据。

**Architecture update / 架构更新:**
```python
# BEFORE: keep existing record, fill missing fields from candidate
# AFTER: pick base by completeness, fill missing fields from the other
def _completeness_score(record) -> int:
    return sum(1 for f in COMPLETENESS_FIELDS if getattr(record, f, None))

if _completeness_score(candidate) > _completeness_score(existing):
    base, filler = candidate, existing
else:
    base, filler = existing, candidate
canonical = _fill_missing(base, filler)
```

---

### 3.6 Separate `paper_identifiers` Table / 独立 `paper_identifiers` 表

**Motivation / 动机:** Storing identifiers as flat columns on the `papers` table made it impossible to index them independently, add new identifier types without schema changes, or query "all papers with a given DOI" efficiently. A separate table with a unique constraint on `(id_type, id_normalized)` solves all three problems.  
将标识符作为 `papers` 表上的平面列存储使得无法独立对其建立索引，无法在不更改架构的情况下添加新标识符类型，也无法高效查询"具有给定 DOI 的所有论文"。一个在 `(id_type, id_normalized)` 上有唯一约束的独立表解决了所有三个问题。

**Architecture update / 架构更新:**
```sql
-- BEFORE: doi TEXT, arxiv_id TEXT, openalex_id TEXT, ... on papers table
-- AFTER:
CREATE TABLE paper_identifiers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_key TEXT NOT NULL,
  id_type TEXT NOT NULL,          -- doi, arxiv, openalex, s2, corpus, pmid, ...
  id_normalized TEXT NOT NULL,
  source TEXT,
  first_seen_at TEXT NOT NULL,
  UNIQUE(id_type, id_normalized),
  FOREIGN KEY (paper_key) REFERENCES papers(paper_key)
);
CREATE INDEX idx_identifiers_paper ON paper_identifiers(paper_key);
```

---

### 3.7 `retrieval_events` and `screening_decisions` / 检索事件和筛选决策

**Motivation / 动机:** The old `source_hits` and `rejects` tables conflated distinct concerns. `retrieval_events` records one event per provider result occurrence (before any identity resolution), making it possible to audit which queries found which papers across which providers. `screening_decisions` is an append-only, staged audit log that lets baseline, agent, and human decisions coexist without overwriting each other.  
旧的 `source_hits` 和 `rejects` 表混淆了不同的关注点。`retrieval_events` 记录每次数据源结果出现时的一个事件（在任何身份解析之前），使得审计哪些查询通过哪些提供商找到了哪些论文成为可能。`screening_decisions` 是一个追加式、分阶段的审计日志，让基线、智能体和人工决策可以共存而不相互覆盖。

**Architecture update / 架构更新:**
```text
BEFORE:  source_hits (paper_key, source, query, rank)
         rejects (paper_key, run_id, reason)

AFTER:   retrieval_events (event_id, run_id, architecture, paper_key,
                           candidate_id, query_id, source, source_rank,
                           request_fingerprint, cache_status, retrieved_at)

         screening_decisions (decision_id, paper_key, run_id, architecture,
                              stage,        -- metadata_filter | baseline_score
                              decision,     -- include | exclude | needs_review
                              score, criteria_version, decision_source,
                              rationale, evidence_json, created_at)
```

---

### 3.8 `api_cache` Schema — BLOB Support / `api_cache` 架构——BLOB 支持

**Motivation / 动机:** The original `api_cache` stored `response_json TEXT`, which excluded arXiv's Atom XML responses. The BLOB column with a `content_type` field supports any response format and allows byte-perfect replay.  
原始 `api_cache` 存储 `response_json TEXT`，排除了 arXiv 的 Atom XML 响应。带有 `content_type` 字段的 BLOB 列支持任何响应格式并允许字节级完整重放。

**Architecture update / 架构更新:**
```sql
-- BEFORE: response_json TEXT
-- AFTER:
ALTER TABLE api_cache ADD COLUMN response_body BLOB;
ALTER TABLE api_cache ADD COLUMN content_type TEXT;
ALTER TABLE api_cache ADD COLUMN payload_hash TEXT;
ALTER TABLE api_cache ADD COLUMN last_accessed_at TEXT;
```

---

### 3.9 arXiv Per-Record Date Filter / arXiv 逐记录日期过滤

**Borrowed the problem from / 发现问题来自:** PRS and PF both stop pagination when they encounter the first record outside the date window. This is wrong: arXiv does not guarantee strict date ordering within a results page.  
PRS 和 PF 都在遇到日期窗口之外的第一条记录时停止分页。这是错误的：arXiv 不保证结果页面内的严格日期排序。

**Architecture update / 架构更新:**
```python
# BEFORE (PRS/PF pattern — wrong):
for entry in page:
    if entry.published < cutoff:
        break   # ← stops entire pagination on one old record

# AFTER (Dynamic-LR):
for entry in page:
    if entry.published < cutoff:
        continue   # ← skip this record, keep paginating
# stop only at page budget or total count limit
```

---

### 3.10 Date-Gap Validation / 日期间隙验证

**Borrowed from / 借鉴自:** PF  
**Motivation / 动机:** PF's `validate_fetch_results` surfaces days in the configured window that have zero papers, flagging possible coverage gaps. Dynamic-LR adapts this to check coverage by year (not day) for year-window pipelines.  
PF 的 `validate_fetch_results` 显示配置窗口中没有论文的日期，标记可能的覆盖间隙。Dynamic-LR 将其调整为按年（而非按天）检查年份窗口流水线的覆盖率。

**Architecture update / 架构更新:**
```text
Added to pipeline.py post-fetch validation step:
  validate_year_coverage(results, timeline_from_year, timeline_to_year)
  → returns {year: count} dict
  → years with count == 0 are logged as coverage_gaps in run metrics
  → included in run_manifest.json and ManagerRunResult
```

---

### 3.11 ML Acronym Expansion / ML 缩略语扩展

**Borrowed from / 借鉴自:** PRS  
**Motivation / 动机:** PRS maintains a static `ML_ACRONYM_EXPANSIONS` dict (`rag → retrieval augmented generation`, `llm → large language model`, etc.) applied before query generation. This recovers retrieval coverage on common abbreviations without any LLM call.  
PRS 维护了一个静态 `ML_ACRONYM_EXPANSIONS` 字典（`rag → retrieval augmented generation`、`llm → large language model` 等），在查询生成前应用。无需任何 LLM 调用即可恢复常见缩略语的检索覆盖率。

**Architecture update / 架构更新:**
```python
# Added to query_builder.py as a pre-processing step:
ML_ACRONYM_EXPANSIONS = {
    "rag": "retrieval augmented generation",
    "llm": "large language model",
    "rlhf": "reinforcement learning from human feedback",
    "cot": "chain of thought",
    # ... (full table from PRS)
}

def expand_acronyms(text: str) -> str:
    tokens = text.lower().split()
    return " ".join(ML_ACRONYM_EXPANSIONS.get(t, t) for t in tokens)
```

---

### 3.12 Frozen Corpus Comparison / 冻结语料库比较

**Motivation / 动机:** To separate retrieval quality from screening quality, all three architectures must be able to receive the same normalized, deduplicated paper set and apply only their own screening logic. This is impossible without a shared snapshot format.  
为了将检索质量与筛选质量分开，所有三种架构必须能够接收相同的规范化、去重后的论文集，并仅应用自己的筛选逻辑。没有共享快照格式，这是不可能的。

**Architecture update / 架构更新:**
```text
Added to publisher.py:
  publish_frozen_corpus_snapshot(corpus_id, papers) →
    data/comparison/frozen_corpora/{corpus_id}/
      manifest.json    (corpus_id, created_at, source_run_id, paper_count)
      papers.ndjson    (normalized PaperRecord objects)

Added to data/comparison/metrics/:
  architecture_summary.json
  baseline_vs_single_agent.json
  baseline_vs_multi_agent.json
```

---

## Part 4 — Summary: What Dynamic-LR Gained From Each System / 第四部分：Dynamic-LR 从每个系统获得了什么

### From PRS / 来自 PRS

| Borrowed / 借鉴 | Applied as / 应用为 |
|---|---|
| Exponential backoff with `Retry-After` | Provider retry policy; deterministic jitter added on top |
| ML acronym expansion table | `query_builder.py` pre-processing step |
| `results_acceptable` batch gate | Metric recorded in run summary (not a retrieval-abort trigger) |
| arXiv XML fetcher structure | Reference for `providers/arxiv.py` |
| SQLite batched upsert | `db.py` transaction pattern |

### From PF / 来自 PF

| Borrowed / 借鉴 | Applied as / 应用为 |
|---|---|
| `asyncio.gather` concurrent fetch | `pipeline.py` three-provider orchestration |
| SBERT + FAISS scoring | `scorer.py` primary semantic score |
| FAISS `IndexFlatIP` with L2 normalization | Scoring backend |
| Numpy embedding cache | `providers/cache.py` embedding persistence |
| OpenAlex cursor pagination | `providers/openalex.py` |
| Abstract inverted-index reconstruction | `normalizer/openalex.py` |
| Completeness-based merge selection | `deduper.py` merge base selection |
| Dual-score storage (semantic + lexical) | Both scores persisted per paper |
| Date-gap validation | Post-fetch coverage check (year-adapted) |
| Static site export pipeline | `publisher.py` (already present; refined) |

### Dynamic-LR originals / Dynamic-LR 原创

| Feature / 功能 | Description / 描述 |
|---|---|
| `paper_identifiers` table | Separate indexed identifier store; unique constraint per type+value |
| `retrieval_events` table | One event per provider result occurrence, pre-identity-resolution |
| `screening_decisions` table | Append-only, staged, architecture-specific audit log |
| 8-level identity chain | DOI→arXiv→OpenAlex→S2→corpus→PMID→fingerprint→fuzzy (flag only) |
| Deterministic jitter | `hash(run_id+provider+fingerprint+attempt) % max_jitter_ms` |
| Query translation layer | Canonical query → provider-specific syntax, versioned |
| `query_state` cross-run table | Per-query statistics feeding loop-control feedback |
| Typed reject evidence dict | Threshold + matched/missing terms per rejected paper |
| `ScreeningDecision` contract | Stage + decision + score + criteria_version + rationale |
| Run manifest with git commit | `run_manifest.json` per run artifact directory |
| Architecture comparison artifacts | `data/comparison/` structure |
| Frozen corpus snapshot | Shared evaluation corpus for cross-architecture comparison |
| Loop-control state machine | Documented, versioned, deterministic rules with named constants |
| Target paper detection chain | 5-level fallback with `must_find` flag |
| Changelog + system status | `data/changelog.md`, `data/system_status.json` |

---

*This document is grounded in the `baseline_comparison/baseline_comparison.html` full comparison report and the `CLAUDE.md` specification. For implementation details, see the module docstrings under `app/architectures/baseline/`.*

*本文档以 `baseline_comparison/baseline_comparison.html` 完整对比报告和 `CLAUDE.md` 规范为依据。有关实现细节，请参见 `app/architectures/baseline/` 下的模块文档字符串。*
