# How Dynamic-LR Works — Explained for Everyone
# Dynamic-LR 工作原理——人人都能看懂的解释

**Level / 级别:** Primary school friendly, but fully detailed  
**Audience / 读者:** Anyone who wants to understand every step  
**Coverage / 覆盖:** Every substep, every data transformation, every error case, three-model comparison at every step

> **Three systems compared / 三个对比系统:**  
> **Dynamic-LR** (this project) · **PRS** (cherryann518) · **PF** (WoosungLim01)  
> Legend / 图例: ★ Best-in-class · ✓ Fully implemented · ◑ Partial · – Not present

---

## The Big Picture First / 先看全局

Imagine you are a very careful student who needs to write a report on a topic.
You go to three different libraries, ask each librarian the same question, collect
every book they give you, remove duplicates, grade each book on how relevant it
is, and only keep the best ones. Then you write down everything you found in a
notebook, and next week you use that notebook to do the same thing again but
smarter.

想象你是一个非常认真的学生，需要就某个主题写一份报告。你去了三个不同的图书馆，向每位图书管理员提出相同的问题，收集他们给你的每一本书，去掉重复的，给每本书按相关性打分，只保留最好的。然后你把所有发现都记在一个本子里，下周用这个本子再做一次，但做得更聪明。

That is exactly what Dynamic-LR does, except:
- The "libraries" are called **providers** (Semantic Scholar, arXiv, OpenAlex).
- The "questions" are called **queries**.
- The "books" are called **papers**.
- The "grading" is called **scoring**.
- The "notebook" is a **SQLite database**.

这正是 Dynamic-LR 所做的，只是：
- "图书馆"被称为**数据源**（Semantic Scholar、arXiv、OpenAlex）。
- "问题"被称为**查询**。
- "书"被称为**论文**。
- "打分"被称为**评分**。
- "本子"是一个 **SQLite 数据库**。

---

## Step 0 — Before Anything Starts / 第零步：一切开始之前

The moment you type `python -m app.run --architecture baseline`, the program
wakes up and does three tiny things instantly, before reading a single file.

当你输入 `python -m app.run --architecture baseline` 的那一刻，程序立即醒来，在读取任何文件之前做三件小事。

### 0.1 Record the exact start time / 记录精确开始时间

```python
started_at = datetime.utcnow().isoformat() + "Z"
# Example result: "2026-06-24T09:15:33.441882Z"
```

This timestamp is stored on every single thing that happens during the run.
That way, if you look at any record in the database, you always know exactly
which run created it.

这个时间戳存储在运行期间发生的每一件事上。这样，如果你查看数据库中的任何记录，你总是能知道是哪次运行创建了它。

### 0.2 Start a wall-clock timer / 启动计时器

```python
wall_start = time.perf_counter()
```

This is like pressing "start" on a stopwatch. At the very end, the pipeline
subtracts the start time from the current time to know how many seconds the
whole run took.

这就像按下秒表上的"开始"。在最后，流水线用当前时间减去开始时间，知道整个运行花了多少秒。

### 0.3 Create the run ID / 创建运行 ID

```python
run_id = "baseline-" + datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
# Example: "baseline-20260624T091533441882"
```

This is the name of this specific run. Think of it like a unique receipt number
at a store. Every future run gets its own receipt number. No two runs ever have
the same ID because time always moves forward.

这是这次特定运行的名称。把它想象成商店里唯一的收据号码。每次未来的运行都有自己的收据号码。任何两次运行都不会有相同的 ID，因为时间总是向前走。

### 0.4 Create an empty error bag / 创建空错误袋

```python
errors: List[str] = []
```

This is a list that starts completely empty. Every time something goes wrong
during the run (but not badly enough to stop everything), the pipeline writes a
short description into this list. At the end, if the bag has anything in it,
the run is marked `partial_success` instead of `success`.

这是一个完全空的列表。每次运行期间出现问题（但不严重到需要停止一切），流水线就在这个列表中写一个简短描述。最后，如果袋子里有任何东西，运行就会被标记为 `partial_success` 而不是 `success`。

---

> ### 📊 Step 0 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Run ID format / 运行 ID 格式 | ★ Timestamp-based, no randomness: `baseline-20260624T...` | ◑ UUID (`str(uuid4())`) | ◑ Timestamp string |
> | Structured error bag / 结构化错误袋 | ★ Typed `List[str]` collected throughout run | ◑ Implicit exceptions | ◑ Logger only |
> | `partial_success` status / 部分成功状态 | ★ Yes — distinguishes "some worked" from "all failed" | – | – |
> | Wall-clock timer / 挂钟计时器 | ★ `time.perf_counter()` (high precision) | ◑ `time.time()` | ◑ `time.time()` |
> | System status file updated / 系统状态文件更新 | ★ Every phase writes `system_status.json` | – | ◑ End of run only |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS uses UUID for run IDs — these are random and unordered, so sorting runs by ID tells you nothing about time order. Dynamic-LR's timestamp-based ID means files, database rows, and artifact folders sort chronologically with no extra metadata. The structured error bag means a run that partially fails still writes a complete result rather than crashing silently.
>
> PRS 使用 UUID 作为运行 ID——这些是随机且无序的，所以按 ID 排序运行不能告诉你任何时间顺序信息。Dynamic-LR 基于时间戳的 ID 意味着文件、数据库行和制品文件夹在没有额外元数据的情况下按时间顺序排序。结构化的错误袋意味着部分失败的运行仍然写入完整的结果，而不是静默崩溃。

---

## Step 1 — Load the Instructions / 第一步：加载指令

### What the instructions file looks like / 指令文件长什么样

The file is `data/survey_config.json`. It is a plain text file written in JSON
format. Here is what a real one might look like:

文件是 `data/survey_config.json`。它是一个用 JSON 格式编写的纯文本文件。真实的文件可能长这样：

```json
{
  "topic_overview": "Explainable AI",
  "research_questions": [
    "What methods make AI explainable?",
    "How is uncertainty used to explain AI decisions?"
  ],
  "query_hints": ["XAI", "interpretability", "uncertainty quantification"],
  "timeline_from_year": 2022,
  "timeline_to_year": 2026,
  "min_relevance_score": 0.30,
  "baseline": {
    "max_queries": 12,
    "max_results_per_query": 50
  }
}
```

### 1.1 Write "I am loading" to the status file / 写入"正在加载"到状态文件

```python
write_system_status({
    "status": "loading_config",
    "run_id": run_id,
    "updated_at": started_at
})
```

This writes a small file called `data/system_status.json`. Anyone watching the
pipeline (a dashboard, a script, a human) can read this file any time to see
what the pipeline is doing right now.

这会写一个叫做 `data/system_status.json` 的小文件。任何观察流水线的人（仪表盘、脚本、人类）都可以随时读取这个文件，了解流水线现在在做什么。

### 1.2 Open and parse the JSON file / 打开并解析 JSON 文件

```python
with open(config_path, "r", encoding="utf-8") as f:
    raw_dict = json.load(f)
```

`json.load(f)` turns the text file into a Python dictionary. If the file does
not exist, Python raises `FileNotFoundError`. If the text is broken JSON (like
a missing closing brace), Python raises `json.JSONDecodeError`. Both of these
get caught and turned into a `ConfigError`.

`json.load(f)` 将文本文件转换为 Python 字典。如果文件不存在，Python 会引发 `FileNotFoundError`。如果文本是损坏的 JSON（比如缺少结束大括号），Python 会引发 `json.JSONDecodeError`。这两种情况都会被捕获并转换为 `ConfigError`。

### 1.3 Extract each field with a safe default / 用安全默认值提取每个字段

The pipeline reads each field like this:

流水线像这样读取每个字段：

```python
topic_overview       = raw_dict["topic_overview"]             # required
research_questions   = raw_dict.get("research_questions", []) # optional → []
query_hints          = raw_dict.get("query_hints", [])        # optional → []
timeline_from_year   = raw_dict.get("timeline_from_year")     # optional → None
timeline_to_year     = raw_dict.get("timeline_to_year")       # optional → None
min_relevance_score  = raw_dict.get("min_relevance_score", 0.3)
baseline_config      = raw_dict.get("baseline", {})
```

### 1.4 What happens if the config is broken / 如果配置损坏会发生什么

If anything goes wrong during config loading — file missing, invalid JSON,
required field absent — the pipeline immediately:

```python
errors.append(f"Config error: {str(e)}")
write_system_status({"status": "failed", "run_id": run_id, ...})
return ManagerRunResult(success=False, status="failure", ...)
```

This is the **only** place where the whole run stops immediately.

这是整个运行立即停止的**唯一**地方。

---

> ### 📊 Step 1 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Config format / 配置格式 | ★ `survey_config.json` with typed dataclass | `.env` + config dict | `config.json`, hardcoded constants |
> | Required field validation / 必填字段验证 | ★ Typed dataclass, fail-fast `ConfigError` | Minimal — implicit crash | Minimal — implicit crash |
> | Optional provider sub-configs / 可选子配置 | ★ `semantic_scholar`, `arxiv`, `openalex` blocks | `semantic_scholar` only | Hardcoded constants |
> | Config hash stored / 配置哈希存储 | ★ `config_hash` in run record, enables replay | – | – |
> | Target papers spec / 目标论文规格 | ★ DOI/arXiv/S2/OA/title per target paper | – | – |
> | Evaluation mode flags / 评估模式标志 | ★ `frozen_corpus_mode`, `target_paper_checks` | – | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS and PF treat missing or bad config as a generic Python crash — you get a traceback instead of a clear error message. Dynamic-LR catches every config failure as a typed `ConfigError` and writes a structured failure result. The `config_hash` field means you can run the pipeline twice with the same config and prove the results are comparable. PRS and PF have no such guarantee.
>
> PRS 和 PF 将缺失或错误的配置视为通用 Python 崩溃——你得到的是回溯信息而不是清晰的错误消息。Dynamic-LR 将每个配置失败捕获为类型化的 `ConfigError` 并写入结构化的失败结果。`config_hash` 字段意味着你可以用相同的配置运行流水线两次并证明结果是可比较的。PRS 和 PF 没有这样的保证。

---

## Step 2 — Build the Shopping List (Queries) / 第二步：建立购物清单（查询）

A query is like a question you write on a piece of paper and hand to a librarian.
The pipeline builds several of them from the config.

查询就像你写在纸上然后交给图书管理员的一个问题。流水线从配置中建立几个查询。

### 2.1 Update the status file / 更新状态文件

```python
write_system_status({"status": "building_queries", ...})
```

### 2.2 Add the topic as the first query / 将主题作为第一个查询

```
Input:  "Explainable AI"
After clean_query():  "Explainable AI"
kind:   "topic"
```

Cleaning does three things to the text:

清洗对文本做三件事：

```
1. Remove invisible control characters
   "Explainable\x00 AI" → "Explainable AI"

2. Collapse all whitespace (multiple spaces, tabs, newlines) to one space
   "Explainable   AI" → "Explainable AI"

3. Truncate if longer than 300 characters
```

### 2.3 Add each research question / 添加每个研究问题

```
"What methods make AI explainable?"          → kind: "research_question"
"How is uncertainty used to explain AI decisions?" → kind: "research_question"
```

### 2.4 Add each query hint / 添加每个查询提示

```
"XAI"                        → kind: "query_hint"
"interpretability"           → kind: "query_hint"
"uncertainty quantification" → kind: "query_hint"
```

### 2.5 Build the combined query — every micro-step / 构建组合查询——每个微步骤

**Step 2.5.1 — Pool all text / 汇集所有文本**
```
text_pool = topic + " " + all questions + " " + all hints
```

**Step 2.5.2 — Lowercase / 转小写**

**Step 2.5.3 — Extract tokens (letters and numbers only) / 提取词元**
```python
tokens = re.findall(r"[a-z0-9]+", text_pool_lower)
```

**Step 2.5.4 — Remove stopwords and tokens shorter than 2 chars / 移除停用词和短词元**
```
STOPWORDS = {"a","an","the","is","are","to","of","what","how","used","make",...}
```

**Step 2.5.5 — Count each surviving token / 统计每个存活词元**
```
explainable:2  ai:2  uncertainty:2  methods:1  explain:1  decisions:1 ...
```

**Step 2.5.6 — Sort by (-count, alphabetical) / 按(-频次, 字母顺序)排序**
```
(-2,"ai") (-2,"explainable") (-2,"uncertainty") (-1,"decisions") (-1,"explain") ...
```

**Step 2.5.7 — Take top 10, join with spaces / 取前10，用空格连接**
```
"ai explainable uncertainty decisions explain interpretability methods quantification xai"
```

### 2.6 Deduplicate case-insensitively / 大小写不敏感去重

```python
seen = set()
for q in raw_list:
    key = q.query.lower()
    if key not in seen:
        seen.add(key); deduped.append(q)
```

### 2.7 Cap at max_queries / 限制到 max_queries

```python
final_queries = deduped[:max_queries]   # default: 12
```

### 2.8 Assign stable query IDs / 分配稳定查询 ID

```python
q.query_id = f"q_{i:03d}"   # "q_000", "q_001", ...
```

### 2.9 Save the query plan artifact / 保存查询计划制品

```json
[
  {"query_id": "q_000", "kind": "topic",             "query": "Explainable AI"},
  {"query_id": "q_001", "kind": "research_question", "query": "What methods make AI explainable?"},
  {"query_id": "q_006", "kind": "combined",          "query": "ai explainable uncertainty ..."}
]
```

---

> ### 📊 Step 2 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Query sources / 查询来源 | ★ Topic + questions + hints + combined | Topic only (+ LLM refinement) | Keywords only |
> | Research questions → queries / 研究问题→查询 | ★ Yes, one query per question | – | – |
> | Combined top-N token query / 组合 top-N 词元查询 | ★ Frequency+alpha sort, deterministic | – | – |
> | LLM query refinement / LLM 查询优化 | – (deterministic only) | ◑ Ollama optional | – |
> | ML acronym expansion / ML 缩略语扩展 | – (planned) | ★ Static lookup table | – |
> | Case-insensitive dedup + query cap / 去重+上限 | ★ Yes | – | `len(keywords)` only |
> | Stable `query_id` before translation / 翻译前稳定 ID | ★ Yes | – | – |
> | Query origin recorded / 查询来源记录 | ★ `topic`/`question`/`hint`/`combined` | – | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS starts with one topic query and optionally uses an LLM to refine it — non-deterministic and model-dependent. PF uses only keyword lists. Dynamic-LR generates queries from every structural element of the config (topic, each individual research question, each hint) plus a deterministic combined query. The combined query uses frequency-weighted token selection so the most important concepts across all questions dominate, even if no single question mentions all of them. The stable `query_id` assigned before any provider translation is what makes cross-provider and cross-run traceability possible.
>
> PRS 从一个主题查询开始，可选地使用 LLM 来优化它——非确定性且依赖模型。PF 只使用关键词列表。Dynamic-LR 从配置的每个结构元素（主题、每个研究问题、每个提示）生成查询，加上一个确定性的组合查询。组合查询使用频率加权词元选择，因此所有问题中最重要的概念占主导地位，即使没有单个问题提到所有这些。在任何数据源翻译之前分配的稳定 `query_id` 使跨数据源和跨运行的可追溯性成为可能。

---

## Step 3 — Translate Queries for Each Provider / 第三步：为每个数据源翻译查询

Each library (provider) has its own query syntax. You can't hand the same sentence to all three — you need to translate it.

每个图书馆（数据源）都有自己的查询语法。你不能把同样的句子交给所有三个——你需要翻译它。

### 3.1 Semantic Scholar translation / Semantic Scholar 翻译

Plain natural language; strip unsupported punctuation:

```
Canonical:  "What methods make AI explainable?"
S2 query:   "What methods make AI explainable"
```

### 3.2 arXiv translation / arXiv 翻译

Split into terms, join with `AND` using `all:` field code:

```
Canonical:     "What methods make AI explainable?"
After cleanup: "methods make AI explainable"
arXiv query:   "all:methods AND all:make AND all:AI AND all:explainable"
```

Short hints use simple `all:term`:
```
Canonical:  "XAI"
arXiv:      "all:XAI"
```

### 3.3 OpenAlex translation / OpenAlex 翻译

Plain text for `search=` plus filter parameters:

```
Canonical:  "What methods make AI explainable?"
OA search:  "What methods make AI explainable"
OA filter:  publication_year:2022-2026, type:article|preprint|review,
            is_retracted:false, is_paratext:false
```

### 3.4 Save the provider query plan / 保存数据源查询计划

```json
{
  "q_000": {
    "canonical": "Explainable AI",
    "semantic_scholar": {"query": "Explainable AI"},
    "arxiv": {"search_query": "all:Explainable AND all:AI"},
    "openalex": {"search": "Explainable AI", "filter": "..."}
  }
}
```

Saved to `data/baseline/run_artifacts/{run_id}/provider_query_plan.json`.

---

> ### 📊 Step 3 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Separate translation module / 独立翻译模块 | ★ `query_translation.py`, versioned | Passthrough (S2 syntax to all) | Direct keyword passthrough |
> | arXiv-specific syntax / arXiv 特定语法 | ★ `all:term AND all:term` | ◑ `ti:`/`all:` fields | Direct keyword |
> | OpenAlex-specific syntax / OA 特定语法 | ★ `search=` + filter block | – | Direct keyword |
> | Translation version recorded / 翻译版本记录 | ★ `query_translation_v1` | – | – |
> | Provider query logged in artifacts / 数据源查询记录在制品中 | ★ `provider_query_plan.json` | – | – |
> | Deterministic output / 确定性输出 | ★ Yes | ◑ Yes if no LLM | ★ Yes |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS passes the same query string to every provider — Semantic Scholar syntax sent to arXiv can produce zero results or misleading results because the field codes and Boolean operators are different systems. PF does keyword passthrough with no translation. Dynamic-LR's separate translation module converts canonical intent to each provider's documented query syntax. The translated queries are saved in an artifact file so a future engineer can audit exactly what was sent to each API call.
>
> PRS 将相同的查询字符串传递给每个数据源——将 Semantic Scholar 语法发送给 arXiv 可能会产生零结果或误导性结果，因为字段代码和布尔运算符是不同的系统。PF 进行不带翻译的关键词传递。Dynamic-LR 的独立翻译模块将规范意图转换为每个数据源的文档化查询语法。翻译后的查询保存在制品文件中，这样未来的工程师可以准确审计发送给每个 API 调用的内容。

---

## Step 4 — Open the Database / 第四步：打开数据库

Think of the database as a very organized filing cabinet with many labeled drawers.

把数据库想象成一个有很多标签抽屉的非常有组织的文件柜。

### 4.1 Normal run vs. dry run / 正常运行与演习运行

```python
if dry_run:
    conn = sqlite3.connect(":memory:")  # RAM only, nothing saved to disk
else:
    conn = sqlite3.connect("data/baseline/baseline.sqlite3")
```

### 4.2 Create tables if they don't exist / 如果表不存在则创建

`CREATE TABLE IF NOT EXISTS` for every table — first run creates them, later runs do nothing.

每个表运行 `CREATE TABLE IF NOT EXISTS`——第一次运行创建它们，以后的运行不执行任何操作。

```
papers              — One row per unique accepted paper / 每篇唯一接受论文一行
paper_identifiers   — All known IDs per paper (DOI, arXiv, etc.) / 每篇论文的所有已知 ID
retrieval_events    — One row every time any provider returned a paper / 数据源每次返回论文一行
screening_decisions — Accept/reject verdict for each candidate / 每个候选的接受/拒绝裁决
merge_events        — When two records turned out to be the same paper / 两条记录是同一论文时
runs                — One row per pipeline run / 每次流水线运行一行
api_cache           — Saved provider responses / 保存的数据源响应
query_state         — Cross-run per-query statistics / 跨运行每查询统计
```

### 4.3 Record that this run has started / 记录此次运行已开始

```sql
INSERT INTO runs (run_id, architecture, status, config_hash, started_at, ...)
VALUES ('baseline-20260624T...', 'baseline', 'running', 'abc123...', ...)
```

The `status` column starts as `"running"` and is updated to `"success"`,
`"partial_success"`, or `"failure"` at the very end.

`status` 列以 `"running"` 开始，在最后被更新为 `"success"`、`"partial_success"` 或 `"failure"`。

---

> ### 📊 Step 4 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Primary store / 主存储 | ★ SQLite `baseline.sqlite3` | ★ SQLite | NDJSON files (no atomic guarantee) |
> | `paper_identifiers` table (separate, indexed) / 独立标识符表 | ★ Yes | – | – |
> | `retrieval_events` table / 检索事件表 | ★ Yes (one row per provider occurrence) | – | – |
> | `screening_decisions` table / 筛选决策表 | ★ Append-only, staged | – | – |
> | `api_cache` with BLOB + TTL / BLOB 缓存+TTL | ★ Yes | ◑ File-per-hash, no TTL | – |
> | `query_state` cross-run stats / 跨运行查询统计 | ★ Yes | – | – |
> | `config_hash` in runs table / 运行表中的配置哈希 | ★ Yes | – | – |
> | Transactional writes / 事务性写入 | ★ Yes | ★ Batched chunks | – |
> | In-memory mode for dry-run / 内存模式用于演习 | ★ `:memory:` | – | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PF uses NDJSON files as its primary store — file writes are not atomic, so a mid-run crash can corrupt the output. Dynamic-LR uses SQLite with transactions: either all writes in a batch succeed together or none of them do. The separate `paper_identifiers` table (not present in PRS or PF) is what enables fast identity lookup across all identifier types without scanning the `papers` table row-by-row. The `api_cache` BLOB column (vs. PRS's file-per-hash approach) supports both JSON and Atom XML with TTL-based expiry, so cached arXiv responses don't become stale silently.
>
> PF 使用 NDJSON 文件作为主存储——文件写入不是原子的，所以运行中途崩溃可能会损坏输出。Dynamic-LR 使用带事务的 SQLite：批次中的所有写入要么一起成功，要么都不成功。独立的 `paper_identifiers` 表（PRS 或 PF 中不存在）使跨所有标识符类型的快速身份查找成为可能，无需逐行扫描 `papers` 表。`api_cache` BLOB 列（vs. PRS 的每哈希文件方法）支持带 TTL 过期的 JSON 和 Atom XML，因此缓存的 arXiv 响应不会静默过期。

---

## Step 5 — Check What We Learned Last Time (Loop Control) / 第五步：检查上次学到了什么（循环控制）

### 5.1 Read the query state table / 读取查询状态表

```python
query_history = db.get_query_state(conn)
# {"xai": {"total_runs": 5, "consecutive_zero_accept": 3, ...}}
```

### 5.2 Check the "three strikes" rule / 检查"三次失败"规则

```python
for q in queries:
    if query_history.get(q.query.lower(), {}).get("consecutive_zero_accept", 0) >= 3:
        deprioritized.add(q.query.lower())
```

### 5.3 Safety guard: never remove everything / 安全保护：永不移除所有内容

```python
filtered = [q for q in queries if q.query.lower() not in deprioritized]
queries = filtered or queries   # if nothing survives, keep all
```

### 5.4 On the very first run / 在第一次运行时

`get_query_state` returns `{}`. All rules produce no effect. All queries run.

`get_query_state` 返回 `{}`。所有规则不产生任何效果。所有查询运行。

---

> ### 📊 Step 5 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Designed for repeated runs / 为重复运行设计 | ★ Yes — loop is the primary mode | ◑ One run + optional LLM re-search | – |
> | Query demotion rule / 查询降级规则 | ★ `consecutive_zero_accept ≥ 3` | – | – |
> | Deterministic multi-round fallback / 确定性多轮回退 | ★ Yes (replaces LLM intent) | – | – |
> | LLM-driven refinement / LLM 驱动优化 | – | ★ Ollama (non-deterministic) | – |
> | Loop rule versioning / 循环规则版本化 | ★ `loop_policy_version` on every event | – | – |
> | Safety guard (never remove all queries) / 安全保护 | ★ Yes | – | – |
> | `query_state` cross-run stats / 跨运行统计 | ★ Per-query, per-source, per-run | – | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS uses an LLM (Ollama) to decide whether to search again — this introduces model variance, API dependency, and cost. PF has no loop at all. Dynamic-LR's loop is a pure state machine: it reads the `query_state` table, applies versioned deterministic rules, and logs every decision. The "three strikes" rule is transparent and reproducible — you can look at the `query_state` table and understand exactly why a query was dropped.
>
> PRS 使用 LLM（Ollama）来决定是否再次搜索——这引入了模型方差、API 依赖和成本。PF 根本没有循环。Dynamic-LR 的循环是一个纯状态机：它读取 `query_state` 表，应用版本化的确定性规则，并记录每个决定。"三次失败"规则是透明且可重现的——你可以查看 `query_state` 表并准确理解为什么一个查询被删除。

---

## Step 6 — Ask Three Libraries at the Same Time / 第六步：同时问三个图书馆

### 6.1 The asyncio.gather pattern / asyncio.gather 模式

```python
results = await asyncio.gather(
    s2_provider.search_all_queries(queries, config),
    arxiv_provider.search_all_queries(queries, config),
    openalex_provider.search_all_queries(queries, config),
    return_exceptions=True,
)
```

`return_exceptions=True` means: if one provider crashes or times out, don't crash
everything — put the error object in the results list. Even if arXiv is down,
we still get results from Semantic Scholar and OpenAlex.

`return_exceptions=True` 意味着：如果一个数据源崩溃或超时，不要让一切崩溃——将错误对象放入结果列表中。即使 arXiv 宕机，我们仍然可以从 Semantic Scholar 和 OpenAlex 获得结果。

---

> ### 📊 Step 6 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Concurrent fetch / 并发抓取 | ★ `asyncio.gather` all three | – (sequential, S2 only) | ★ `asyncio.gather` (S2 + arXiv) |
> | Provider coverage / 数据源覆盖 | ★ S2 + arXiv + OpenAlex | S2 only | S2 + arXiv |
> | `return_exceptions=True` fail-soft / 软失败 | ★ Yes | – | ★ Yes |
> | Per-provider semaphore / 每数据源信号量 | ★ Yes | – | – |
> | Global candidate cap / 全局候选上限 | ★ `max_candidates_per_run` | `MAX_PAPERS` | – |
> | Provider failure → `partial_success` / 数据源失败→部分成功 | ★ Each failure is a structured partial error | – | ◑ Exception caught but not recorded |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS queries only Semantic Scholar — one library instead of three. This means it misses papers that are on arXiv but not yet indexed by S2, and papers covered by OpenAlex but not S2. PF queries S2 + arXiv concurrently but misses OpenAlex's broader coverage and metadata enrichment. Dynamic-LR's three-provider approach increases recall by design. The per-provider semaphore prevents one slow provider from starving others or overwhelming the API with burst requests.
>
> PRS 只查询 Semantic Scholar——一个图书馆而不是三个。这意味着它会错过在 arXiv 上但尚未被 S2 索引的论文，以及 OpenAlex 覆盖但 S2 没有的论文。PF 并发查询 S2 + arXiv，但错过了 OpenAlex 更广泛的覆盖和元数据丰富。Dynamic-LR 的三数据源方法在设计上增加了召回率。每数据源信号量防止一个慢数据源耗尽其他数据源或以突发请求压垮 API。

---

## Step 7 — Fetching from Semantic Scholar / 第七步：从 Semantic Scholar 获取

### 7.1 Build the request URL / 构建请求 URL

```
URL: https://api.semanticscholar.org/graph/v1/paper/search
     ?query=Explainable+AI
     &fields=paperId,corpusId,title,abstract,year,authors,url,...
     &limit=50&offset=0
```

### 7.2 Compute a cache key / 计算缓存键

```python
cache_input = "semantic_scholar|/graph/v1/paper/search|" + sorted_params_string
cache_key = hashlib.sha256(cache_input.encode()).hexdigest()[:32]
```

### 7.3 Cache check / 缓存检查

```python
row = db.execute("SELECT response_body FROM api_cache WHERE cache_key=?", (cache_key,)).fetchone()
if row:
    return parse_response(row["response_body"])   # no network call!
```

If there is a cache hit, zero bytes travel over the network. Re-running the
pipeline 100 times produces identical results without consuming any API quota.

如果有缓存命中，零字节通过网络传输。重新运行流水线100次产生相同的结果，不消耗任何 API 配额。

### 7.4 Send the HTTP request / 发送 HTTP 请求

```python
headers = {"User-Agent": "Dynamic-LR/1.0"}
if api_key:
    headers["x-api-key"] = api_key
response = urllib.request.urlopen(request, timeout=30)
```

### 7.5 Retry logic — attempt by attempt / 重试逻辑

```
Attempt 1: send request
  HTTP 200 → parse JSON → cache → return  ✓
  HTTP 429 → read Retry-After header → deterministic jitter → sleep → Attempt 2
  HTTP 5xx → sleep 2s + jitter → Attempt 2
  Bad JSON → sleep 2s + jitter → Attempt 2
  Timeout  → sleep 2s + jitter → Attempt 2

Attempt 2: same, sleep = 5s + jitter on failure
Attempt 3: same, sleep = 15s + jitter on failure
Attempt 4: last chance — if fails: log error, return [], continue to next query
```

**Deterministic jitter formula:**
```python
jitter_ms = int(
    sha256(f"{run_id}:s2:{cache_key}:{attempt}".encode()).hexdigest(), 16
) % max_jitter_ms
```

For the same run ID, provider, request, and attempt number, this always produces
the same jitter value. Unlike `random.uniform()`, it never introduces variance.

对于相同的运行 ID、数据源、请求和尝试次数，这总是产生相同的抖动值。与 `random.uniform()` 不同，它从不引入方差。

### 7.6 Rate-limit pacing / 速率限制间隔

```python
time.sleep(RATE_LIMIT_SLEEP_S)   # 0.5s between every successful request
```

### 7.7 Pagination / 分页

```python
offset = 0
while offset < total and offset < max_results:
    fetch page at offset=0, 50, 100, ...
    # Stop at max_pages_per_query (default 3)
```

### 7.8 Cache the response / 缓存响应

```python
db.execute("""
    INSERT OR REPLACE INTO api_cache
    (cache_key, source, response_body, content_type, payload_hash, created_at, expires_at)
    VALUES (?, 'semantic_scholar', ?, 'application/json', ?, ?, ?)
""", (cache_key, body_bytes, sha256(body_bytes), now, now + ttl))
```

---

> ### 📊 Step 7 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | HTTP library / HTTP 库 | `urllib` (stdlib) | `urllib` (stdlib) | `httpx` (async) |
> | Retry on 429 / 429 重试 | ★ Exp backoff + det. jitter + Retry-After | ★ Exp backoff + random jitter | ◑ Fixed 60s sleep |
> | Retry on 5xx / 5xx 重试 | ★ Yes | – | – |
> | **Deterministic jitter / 确定性抖动** | ★ `hash(run_id+provider+fp+attempt)` | ◑ `random.uniform(1.0,1.5)` | – |
> | Raw response cache / 原始响应缓存 | ★ SQLite BLOB + TTL | ◑ File per hash, no TTL | – |
> | Cache key includes fields + pagination / 缓存键包含字段+分页 | ★ Yes | ◑ Query text only | – |
> | Pagination bounded / 分页有界 | ★ `max_pages_per_query` | ★ `MAX_PAGES_PER_QUERY` | ★ Total count |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS uses `random.uniform()` for jitter — two runs of the identical pipeline produce different sleep durations, which makes replay non-deterministic. Dynamic-LR derives jitter from a hash of the run ID and request fingerprint: the same inputs always produce the same sleep duration. PF has no retry on 5xx errors at all. Dynamic-LR's SQLite BLOB cache (vs. PRS's one-file-per-hash) centralizes cache management, supports TTL expiry, and works for both JSON and binary responses.
>
> PRS 使用 `random.uniform()` 进行抖动——相同流水线的两次运行产生不同的睡眠时长，这使得重放不确定性。Dynamic-LR 从运行 ID 和请求指纹的哈希中推导抖动：相同的输入总是产生相同的睡眠时长。PF 根本没有 5xx 错误的重试。Dynamic-LR 的 SQLite BLOB 缓存（vs. PRS 的每哈希一个文件）集中化缓存管理，支持 TTL 过期，适用于 JSON 和二进制响应。

---

## Step 8 — Fetching from arXiv / 第八步：从 arXiv 获取

arXiv returns **Atom XML**, not JSON:

arXiv 返回 **Atom XML**，而不是 JSON：

```xml
<feed xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>1523</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2301.04567v2</id>
    <title>Explaining Neural Network Decisions with Uncertainty</title>
    <summary>In this paper we propose...</summary>
    <published>2023-01-11T18:00:00Z</published>
    <author><name>Alice Chen</name></author>
    <link href="http://arxiv.org/pdf/2301.04567v2" rel="related" title="pdf"/>
  </entry>
</feed>
```

### 8.1 Build the arXiv request URL / 构建 arXiv 请求 URL

```
https://export.arxiv.org/api/query
  ?search_query=all:explainable+AND+all:AI
  &start=0&max_results=100
  &sortBy=submittedDate&sortOrder=descending
```

### 8.2 Parse Atom XML with stdlib / 用标准库解析 Atom XML

```python
root = ET.fromstring(xml_body)
ns = {"atom": "http://www.w3.org/2005/Atom"}
for entry in root.findall("atom:entry", ns):
    raw_id    = entry.find("atom:id", ns).text
    title     = entry.find("atom:title", ns).text.strip()
    summary   = entry.find("atom:summary", ns).text.strip()
    published = entry.find("atom:published", ns).text
    authors   = [a.find("atom:name", ns).text
                 for a in entry.findall("atom:author", ns)]
```

### 8.3 The critical rule: per-record date filtering / 关键规则：逐记录日期过滤

arXiv does not guarantee strict date ordering. A page of 50 results might
contain 48 papers from 2025 and 2 papers from 2020 scattered anywhere.

arXiv 不保证严格的日期排序。50 个结果的一页可能包含 48 篇 2025 年的论文和 2 篇散布在任何位置的 2020 年论文。

```python
for entry in page_entries:
    year = int(entry.published[:4])
    if year < timeline_from_year or year > timeline_to_year:
        continue   # skip this record, but KEEP PAGINATING
    candidates.append(entry)
# Stop only at max_pages_per_query, never at one old record
```

---

> ### 📊 Step 8 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | XML parser / XML 解析器 | `xml.etree.ElementTree` (stdlib) | `feedparser` (dependency) | `feedparser` (dependency) |
> | Async / 异步 | ★ Yes (`httpx`) | – | ★ Yes (`httpx`) |
> | Retry + deterministic jitter / 重试+确定性抖动 | ★ Yes | – | – |
> | **Per-record date filter (never stop on one old entry) / 逐记录日期过滤** | ★ `continue` (skip record, keep paginating) | ◑ `break` (STOPS on first old record — bug) | ◑ `break` (STOPS on first old record — bug) |
> | Request interval / 请求间隔 | ★ `min_request_interval_seconds` | – | ★ Fixed `asyncio.sleep` |
> | Category filter / 分类过滤 | ★ Configurable | – | – |
> | arXiv ID version stripped for identity / 版本号剥离用于身份 | ★ Yes | ★ Yes | ★ Yes |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> This is the most important correctness difference in arXiv handling. Both PRS and PF stop pagination the moment they see one result older than the configured date window — they use `break` to exit the loop. But arXiv does not sort results perfectly by date. One old preprint scattered in a page of new results should not end the search; all subsequent pages might contain relevant new papers. Dynamic-LR uses `continue` (skip the old record, process the next one) and only stops at the page budget limit. In practice this means PRS and PF silently miss papers that come after any scattered old entry.
>
> 这是 arXiv 处理中最重要的正确性差异。PRS 和 PF 一旦看到比配置日期窗口更旧的结果就停止分页——它们使用 `break` 退出循环。但 arXiv 不能完美地按日期排序结果。散布在新结果页面中的一篇旧预印本不应该结束搜索；所有后续页面可能包含相关的新论文。Dynamic-LR 使用 `continue`（跳过旧记录，处理下一条）并且只在页面预算限制处停止。实际上这意味着 PRS 和 PF 静默地错过了任何散布旧条目后面的论文。

---

## Step 9 — Fetching from OpenAlex / 第九步：从 OpenAlex 获取

OpenAlex uses **cursor pagination** — "give me the next batch after this bookmark":

OpenAlex 使用**游标分页**——"给我这个书签后的下一批"：

### 9.1 First request — start cursor / 第一个请求——开始游标

```
GET https://api.openalex.org/works
    ?search=explainable+AI
    &filter=publication_year:2022-2026,type:article|preprint|review,...
    &per-page=100
    &cursor=*
```

Response:
```json
{
  "meta": {"count": 8523, "next_cursor": "IyIgZXhwbGFpbm..."},
  "results": [...]
}
```

### 9.2 Follow the cursor / 跟随游标

```python
cursor = "*"
while cursor and pages_fetched < max_pages:
    response = fetch(url, params={..., "cursor": cursor})
    cursor = response["meta"]["next_cursor"]
    pages_fetched += 1
    candidates.extend(response["results"])
    if not cursor:
        break
```

### 9.3 Abstract reconstruction from inverted index / 从倒排索引重建摘要

OpenAlex sometimes provides abstracts as an inverted index:

```json
"abstract_inverted_index": {
  "In": [0], "this": [1], "paper": [2], "we": [3], "propose": [4],
  "explainable": [9, 15], "AI": [10, 16]
}
```

To reconstruct:

```python
def reconstruct_abstract(inverted_index: dict) -> str:
    position_word = []
    for word, positions in inverted_index.items():
        for pos in positions:
            position_word.append((pos, word))
    position_word.sort(key=lambda x: x[0])   # deterministic sort
    return " ".join(word for _, word in position_word)
```

The original `abstract_inverted_index` is always kept in `raw["openalex"]` for audit.

原始 `abstract_inverted_index` 始终保存在 `raw["openalex"]` 中以供审计。

---

> ### 📊 Step 9 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Provider implemented / 已实现 | ★ Yes | – | ★ Yes |
> | Cursor pagination / 游标分页 | ★ `cursor=*` → `next_cursor` | – | ★ Yes |
> | Abstract inverted-index reconstruction / 倒排索引摘要重建 | ★ Deterministic sort, preserve ref | – | ★ Deterministic |
> | **Preserve original inverted-index for audit / 保留原始倒排索引供审计** | ★ Yes (`raw["openalex"]`) | – | – |
> | Retracted/paratext filtering / 撤回/辅文过滤 | ★ Configurable | – | ★ Yes |
> | Work type filter / 作品类型过滤 | ★ `article`/`preprint`/`review` | – | ◑ All types |
> | Response cache / 响应缓存 | ★ SQLite BLOB + TTL | – | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS has no OpenAlex support at all. PF implements OpenAlex but does not preserve the original inverted-index payload — once the abstract is reconstructed, the raw data is gone and cannot be re-audited. Dynamic-LR stores the original inverted-index in `raw["openalex"]` alongside the reconstructed text, so a future engineer can verify the reconstruction, update the algorithm, or spot encoding issues. The configurable work-type filter prevents book chapters, editorial notes, and other non-research records from entering the pipeline.
>
> PRS 根本没有 OpenAlex 支持。PF 实现了 OpenAlex 但不保留原始倒排索引负载——一旦摘要被重建，原始数据就消失了，无法重新审计。Dynamic-LR 将原始倒排索引存储在 `raw["openalex"]` 中，与重建文本并存，这样未来的工程师可以验证重建、更新算法或发现编码问题。可配置的作品类型过滤器防止书籍章节、编辑注释和其他非研究记录进入流水线。

---

## Step 10 — Normalize Every Raw Result / 第十步：规范化每个原始结果

Each provider returns data in its own format. Normalization converts everything
into one shared `PaperCandidate` shape.

每个数据源以自己的格式返回数据。规范化将所有内容转换为一种共享的 `PaperCandidate` 形状。

### 10.1 What a raw Semantic Scholar record looks like / 原始 S2 记录

```json
{
  "paperId": "4b16d4a5f9c2e83a1d0f7c85b62a0e91f3d8bc7a",
  "corpusId": "219687912",
  "title": "Explaining Neural Network Decisions via Calibrated Uncertainty",
  "abstract": "We propose a post-hoc explanation method...",
  "year": 2023,
  "authors": [{"authorId": "12345", "name": "Alice Chen"}],
  "externalIds": {"DOI": "10.1145/3580305.3599572", "ArXiv": "2301.04567"},
  "citationCount": 47,
  "venue": "KDD",
  "openAccessPdf": {"url": "https://arxiv.org/pdf/2301.04567.pdf"}
}
```

### 10.2 After normalization / 规范化后

```python
PaperCandidate(
    title          = "Explaining Neural Network Decisions via Calibrated Uncertainty",
    abstract       = "We propose a post-hoc explanation method...",
    year           = 2023,
    authors        = ["Alice Chen"],
    url            = "https://www.semanticscholar.org/paper/4b16d4a...",
    pdf_url        = "https://arxiv.org/pdf/2301.04567.pdf",
    identifiers    = PaperIdentifiers(
        doi                 = "10.1145/3580305.3599572",
        arxiv_id            = "2301.04567",
        semantic_scholar_id = "4b16d4a5f9c2e83a...",
        corpus_id           = "219687912",
    ),
    citation_count = 47,
    venue          = "KDD",
    sources        = ["semantic_scholar"],
    source_rank    = 3,
    raw            = {"semantic_scholar": {... original dict ...}},
)
```

### 10.3 Per-provider normalizer dispatch / 每数据源规范化器分发

```python
if source == "semantic_scholar":
    candidate = normalize_s2(raw_item)
elif source == "arxiv":
    candidate = normalize_arxiv(atom_entry)    # parses XML fields
elif source == "openalex":
    candidate = normalize_openalex(work_dict)  # reconstructs abstract
```

### 10.4 Normalization failure / 规范化失败

```python
try:
    candidate = normalize(raw_item, source)
except Exception as e:
    errors.append(f"Normalization failed: {e}")
    continue   # skip this paper, keep processing the rest
```

---

> ### 📊 Step 10 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Per-provider separate normalizer / 每数据源独立规范化器 | ★ `semantic_scholar.py`, `arxiv.py`, `openalex.py` | ◑ Mostly S2 | ◑ Per-source functions |
> | S2 full field extraction / S2 完整字段提取 | ★ paperId, corpusId, extIDs, citationCount, OA PDF | ★ Full | ★ Full |
> | arXiv field extraction / arXiv 字段提取 | ★ ID/version, categories, published/updated, DOI | ★ Full | ★ Full |
> | OA inverted-abstract preserved raw / OA 倒排摘要保留原始 | ★ Yes (audit trail) | – | – |
> | Document type mapping / 文档类型映射 | ★ `article`/`preprint`/`review` | – | ★ Yes |
> | **Raw payload reference preserved / 原始负载引用保留** | ★ `source_raw_ref` + `raw` dict | – | – |
> | Source rank preserved / 数据源排名保留 | ★ `source_rank` | – | – |
> | Normalization failure → typed reject / 失败→类型化拒绝 | ★ `malformed_metadata` reason code | ◑ Skip silently | ◑ Skip silently |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS and PF normalize failures by silently skipping records — you never know how many papers were lost due to a bad API response field or an unexpected data shape. Dynamic-LR writes a `malformed_metadata` reject record for every failure, so the count of lost candidates is always visible in the reject log. The `source_raw_ref` field in every `PaperCandidate` preserves a reference back to the original provider payload, so any field value can be traced to its exact source record at any time in the future.
>
> PRS 和 PF 通过静默跳过记录来处理规范化失败——你永远不知道有多少论文因为错误的 API 响应字段或意外的数据形状而丢失。Dynamic-LR 为每次失败写一个 `malformed_metadata` 拒绝记录，因此丢失候选的数量在拒绝日志中始终可见。每个 `PaperCandidate` 中的 `source_raw_ref` 字段保留对原始数据源负载的引用，因此任何字段值都可以在未来任何时候追溯到其确切的源记录。

---

## Step 11 — Validate Every Candidate / 第十一步：验证每个候选

### 11.1 Repair first, then check / 先修复，再检查

```python
candidate.title    = " ".join(candidate.title.split()).strip()
candidate.abstract = " ".join(candidate.abstract.split()).strip() if candidate.abstract else None
```

`"  Explaining  Neural  \n Network  "` → `"Explaining Neural Network"`

### 11.2 Apply rejection rules / 应用拒绝规则

```python
if not candidate.title:
    return ValidationResult(ok=False, reason="missing_title")

if len(candidate.title.split()) < min_title_tokens:
    return ValidationResult(ok=False, reason="missing_title")

# Everything else passes:
# missing abstract → OK    missing PDF → OK    missing year → OK (soft mode)
return ValidationResult(ok=True)
```

Validation failures are not silently discarded — they get a `rejection_reason`
and are formally rejected in the filtering step, so they appear in the reject log.

验证失败不会被静默丢弃——它们得到一个 `rejection_reason` 并在过滤步骤中被正式拒绝，所以它们出现在拒绝日志中。

---

> ### 📊 Step 11 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Missing title → reject / 缺少标题→拒绝 | ★ Yes, logged | ◑ Implicit skip | ★ Yes |
> | Blank/short title → reject / 空/短标题→拒绝 | ★ `min_title_tokens` configurable | – | – |
> | Missing abstract → retain / 缺少摘要→保留 | ★ Yes | ★ Yes | ★ Yes |
> | Missing URL → retain / 缺少 URL→保留 | ★ Yes | ★ Yes | – (rejects valid preprints) |
> | Conservative whitespace repair / 保守空白修复 | ★ Full (split+join) | ◑ Basic trim | ◑ Basic `re.sub` |
> | Typed reject reason / 类型化拒绝原因 | ★ `malformed_metadata` code | ◑ Generic string | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PF requires a URL to accept a paper — this causes valid preprints from arXiv (which sometimes lack a permanent URL at query time) to be silently rejected. Dynamic-LR's conservative policy retains papers with missing optional fields; only a missing or degenerate title triggers rejection. The `min_title_tokens` guard catches junk records like a title of just "AI" or a single symbol, which other systems would keep.
>
> PF 要求 URL 才能接受论文——这会导致来自 arXiv 的有效预印本（有时在查询时缺乏永久 URL）被静默拒绝。Dynamic-LR 的保守策略保留缺少可选字段的论文；只有缺失或退化的标题才会触发拒绝。`min_title_tokens` 保护捕获垃圾记录，比如只有"AI"或单个符号的标题，而其他系统会保留这些记录。

---

## Step 12 — Assign Stable Identity to Every Paper / 第十二步：为每篇论文分配稳定身份

### 12.1 Priority order for choosing the paper key / 选择论文键的优先顺序

```
Level 1: DOI          → "doi:10.1145/3580305.3599572"
  normalize: lowercase, strip "https://doi.org/" and "doi:" prefixes

Level 2: arXiv ID     → "arxiv:2301.04567"
  normalize: lowercase, strip URL and "arxiv:" prefixes, strip version (v1, v2...)

Level 3: OpenAlex ID  → "openalex:W2964645445"
  normalize: strip URL prefix, uppercase "W"

Level 4: S2 paperId   → "s2:4b16d4a5f9c2e83a..."
  normalize: whitespace cleanup only

Level 5: S2 corpusId  → "corpus:219687912"

Level 6: PMID / ACL / MAG → "pmid:37312543"

Level 7: Title fingerprint → "fp:a3f7c91b2d04e85a"
  formula: SHA-256(title_norm + "|" + year + "|" + first_author_norm)[:16]
  where:
    title_norm       = unicode_normalize → lowercase → remove punctuation → collapse spaces
    first_author_norm = unicode_normalize → lowercase → collapse spaces

Level 8: Fuzzy title   → flag as possible_duplicate ONLY, never auto-merge
```

### 12.2 Example: same paper from two providers / 同一篇论文来自两个数据源

```
From Semantic Scholar:
  doi = "10.1145/3580305.3599572"    → paper_key = "doi:10.1145/3580305.3599572"

From arXiv:
  doi = None,  arxiv_id = "2301.04567"  → paper_key = "arxiv:2301.04567"

→ Different keys. The deduplication step finds they share an arXiv ID and merges them.
```

---

> ### 📊 Step 12 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Identity priority chain depth / 优先链深度 | ★ 8 levels (DOI→arXiv→OA→S2→corpus→PMID→fp→fuzzy) | ◑ 4 levels | ◑ 5 levels |
> | OpenAlex ID in chain / OA ID 在链中 | ★ Level 3 | – | ★ Yes |
> | S2 corpusId / S2 语料库 ID | ★ Level 5 | ★ Yes | – |
> | PMID / ACL / MAG | ★ Level 6 | – | – |
> | Title fingerprint includes first author / 指纹包含第一作者 | ★ SHA-256 + first author | ◑ SHA-256, no author | ★ MD5 + first author last name |
> | Separate `paper_identifiers` table / 独立标识符表 | ★ Indexed, unique per (type, value) | – | – |
> | **Fuzzy title → flag only, never auto-merge / 模糊标题→仅标记，永不自动合并** | ★ `possible_duplicate` flag | ◑ Auto-merge | ◑ Auto-merge |
> | `paper_key` prefix format / 键前缀格式 | ★ `doi:` `arxiv:` `openalex:` `s2:` `corpus:` `fp:` | ◑ `doi:` `arxiv:` `s2:` | ◑ `doi:` `arxiv:` `s2:` |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> The most critical improvement is the fuzzy-title rule. PRS and PF auto-merge two papers if their titles are ≥90% similar — this is a correctness bug. A 2020 paper and a 2023 paper about the same topic can have nearly identical titles but be completely different works. Dynamic-LR never auto-merges on title similarity; it emits a `possible_duplicate` flag and lets a human or a future algorithm decide. The separate `paper_identifiers` table (absent from both PRS and PF) also means identifier lookups are O(1) index scans rather than O(n) full-table scans.
>
> 最关键的改进是模糊标题规则。PRS 和 PF 在标题相似度 ≥90% 时自动合并两篇论文——这是一个正确性错误。关于同一主题的 2020 年论文和 2023 年论文可以有几乎相同的标题，但完全是不同的作品。Dynamic-LR 从不根据标题相似性自动合并；它发出一个 `possible_duplicate` 标记，让人类或未来的算法来决定。独立的 `paper_identifiers` 表（PRS 和 PF 都没有）也意味着标识符查找是 O(1) 索引扫描而不是 O(n) 全表扫描。

---

## Step 13 — Deduplicate: Spot the Same Book Twice / 第十三步：去重

### 13.1 Phase A: Intra-run deduplication / 阶段 A：运行内去重

```python
for id_type in ["doi","arxiv_id","openalex_id","semantic_scholar_id","corpus_id"]:
    value = getattr(candidate.identifiers, id_type)
    if value:
        key = f"{id_type}:{normalize(value)}"
        if key in seen_by_id:
            merge_candidates(seen_by_id[key], candidate)
            break
```

### 13.2 Phase B: Cross-session dedup against database / 阶段 B：跨会话对比数据库去重

```python
for id_type, id_value in candidate.identifiers.as_pairs():
    row = db.execute(
        "SELECT paper_key FROM paper_identifiers WHERE id_type=? AND id_normalized=?",
        (id_type, normalize(id_value))
    ).fetchone()
    if row:
        existing_paper_key = row["paper_key"]
        record_merge_event(candidate, existing_paper_key, matched_on=id_type)
        candidate.status = "merged"
        break
```

### 13.3 Completeness-based merge / 基于完整性的合并

```python
COMPLETENESS_FIELDS = ["title","abstract","year","authors","url","pdf_url","venue","doi","arxiv_id"]

def completeness_score(record) -> int:
    return sum(1 for f in COMPLETENESS_FIELDS if getattr(record, f, None))

if completeness_score(candidate) > completeness_score(existing):
    base, filler = candidate, existing
else:
    base, filler = existing, candidate

for field in COMPLETENESS_FIELDS:
    if not getattr(base, field) and getattr(filler, field):
        setattr(base, field, getattr(filler, field))
```

### 13.4 Fuzzy matching — flag only / 模糊匹配——仅标记

```python
if title_similarity > 0.90 and abs(candidate.year - existing.year) <= 1:
    candidate.possible_duplicate_of = existing.paper_key
    record_screening_decision(decision="needs_review",
                              rationale=f"Title similarity {title_similarity:.2f}")
    # Never auto-merge here
```

---

> ### 📊 Step 13 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Intra-run dedup / 运行内去重 | ★ Yes | ★ Yes | ★ Yes |
> | Cross-session SQLite dedup / 跨会话 SQLite 去重 | ★ Yes | ★ Yes | – |
> | Cross-run NDJSON full scan / NDJSON 全量扫描 | – | – | ◑ O(n) scan |
> | **Completeness-based merge (pick richer record) / 基于完整性的合并** | ★ Yes | – | ★ Yes |
> | Keep longer abstract / 保留更长摘要 | ★ Yes | – | ★ Yes |
> | Citation count → max observed / 引用数→最大观测值 | ★ max() with source+timestamp | – | – |
> | Merge event log table / 合并事件日志表 | ★ Yes (SQLite) | ★ Yes (SQLite) | – |
> | `possible_duplicate` flagging / 可能重复标记 | ★ Yes | – | – |
> | Multi-source provenance union / 多数据源来源合集 | ★ Yes (`sources_seen`) | ◑ Basic | ◑ Basic |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PF uses NDJSON as its dedup store — cross-run dedup requires a full O(n) scan of all previously accepted papers on every run. As the corpus grows this gets slower and slower. Dynamic-LR's `paper_identifiers` table with a unique index makes cross-run dedup a constant-time lookup regardless of corpus size. The completeness-based merge (borrowed from PF, improved with field-level audit trail) ensures that when the same paper appears in two sources, the version with more fields filled in becomes the canonical record rather than arbitrarily picking one.
>
> PF 使用 NDJSON 作为去重存储——跨运行去重需要在每次运行时对所有之前接受的论文进行完整的 O(n) 扫描。随着语料库增长，这变得越来越慢。Dynamic-LR 的 `paper_identifiers` 表带有唯一索引，使跨运行去重成为恒定时间查找，不受语料库大小影响。基于完整性的合并（从 PF 借用，通过字段级审计跟踪改进）确保当同一篇论文出现在两个数据源时，填写了更多字段的版本成为规范记录，而不是任意选择一个。

---

## Step 14 — Score Every Paper / 第十四步：为每篇论文打分

### 14.1 Build the vocabulary from the config / 从配置建立词汇表

```python
config_text = topic_overview + " " + " ".join(research_questions) + " " + " ".join(hints)
config_tokens = set(
    t for t in re.findall(r"[a-z0-9]+", config_text.lower())
    if t not in STOPWORDS and len(t) > 1
)
# {"explainable","ai","uncertainty","methods","interpretability","xai",...}
```

### 14.2 Six score components / 六个评分组件

**Component 1 — Title keyword overlap (0.35)**
```python
title_tokens = set(re.findall(r"[a-z0-9]+", candidate.title.lower()))
overlap = config_tokens & title_tokens
title_keyword_overlap = len(overlap) / len(config_tokens)   # e.g. 3/10 = 0.30
```

**Component 2 — Abstract keyword overlap (0.30)**
```python
abstract_tokens = set(re.findall(r"[a-z0-9]+", (candidate.abstract or "").lower()))
abstract_keyword_overlap = len(config_tokens & abstract_tokens) / len(config_tokens)
```

**Component 3 — Query phrase match (0.15)**
```python
full_text = (candidate.title + " " + (candidate.abstract or "")).lower()
best = 0.0
for q in queries:
    if q.query.lower() in full_text:
        best = 1.0; break
    phrase_tokens = q.query.lower().split()
    matches = sum(1 for t in phrase_tokens if t in full_text)
    if matches / len(phrase_tokens) >= 0.5:
        best = max(best, 0.5)
query_phrase_match = best
```

**Component 4 — Recency score (0.10)**
```python
if paper_year is None:
    recency_score = 0.5
elif from_year <= paper_year <= to_year:
    recency_score = 1.0
else:
    years_outside = min(abs(paper_year - from_year), abs(paper_year - to_year))
    recency_score = max(0.0, 1.0 - 0.1 * years_outside)
```

**Component 5 — Identifier score (0.05)**
```python
score = 0.0
if candidate.identifiers.doi:              score += 0.40
if candidate.identifiers.arxiv_id:         score += 0.30
if candidate.identifiers.openalex_id:      score += 0.20
if candidate.identifiers.semantic_scholar_id: score += 0.10
identifier_score = min(score, 1.0)
```

**Component 6 — Citation score (0.05)**
```python
if candidate.citation_count and candidate.citation_count > 0:
    citation_score = min(1.0, math.log(candidate.citation_count + 1) / math.log(100))
else:
    citation_score = 0.0
```

### 14.3 Combine into final score / 合并为最终评分

```python
score = (
    0.35 * title_keyword_overlap      +  # 0.35 × 0.30 = 0.105
    0.30 * abstract_keyword_overlap   +  # 0.30 × 0.70 = 0.210
    0.15 * query_phrase_match         +  # 0.15 × 1.00 = 0.150
    0.10 * recency_score              +  # 0.10 × 1.00 = 0.100
    0.05 * identifier_score           +  # 0.05 × 0.70 = 0.035
    0.05 * citation_score             )  # 0.05 × 0.84 = 0.042
# score = 0.642
```

### 14.4 Store all six components / 存储所有六个组件

```json
{
  "score": 0.642,
  "score_components": {
    "title_keyword_overlap": 0.30,
    "abstract_keyword_overlap": 0.70,
    "query_phrase_match": 1.00,
    "recency_score": 1.00,
    "identifier_score": 0.70,
    "citation_score": 0.84
  },
  "method": "baseline_lexical_v1",
  "criteria_version": "baseline_lexical_v1"
}
```

---

> ### 📊 Step 14 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Scoring method / 评分方法 | ★ Lexical formula, 6 named components | TF-IDF cosine + SBERT (`sklearn`) | TF-IDF (ngram 1-2) + SBERT + FAISS |
> | Citation score (log-norm) / 引用评分（对数规范化） | ★ Yes, capped at log(100) | – | – |
> | Identifier quality score / 标识符质量评分 | ★ Yes (rewards DOI/arXiv presence) | – | – |
> | Recency decay / 时间新近性衰减 | ★ Linear decay, configurable | ★ `rank_recency` method | ◑ Implicit date filter only |
> | **All 6 components stored per paper / 所有6组件按论文存储** | ★ Named fields in JSON | ◑ Method dict | ◑ 2 fields only |
> | Criteria version string / 标准版本字符串 | ★ `baseline_lexical_v1` | – | – |
> | Fully deterministic / 完全确定性 | ★ Yes (no model weights) | ★ Yes (SBERT weights fixed) | ★ Yes |
> | LLM-free / 无 LLM | ★ Yes | ★ Yes | ★ Yes |
> | Score transparency for audit / 分数透明性供审计 | ★ High — each weight and term is inspectable | ◑ Method breakdown available | ◑ Two named fields |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS and PF use SBERT embeddings — this requires a model download, GPU/CPU inference time, and produces scores that are difficult to explain ("this paper scored 0.71 — why?"). Dynamic-LR's lexical formula is completely transparent: you can look at a rejected paper, see `title_keyword_overlap: 0.10`, count the matching words yourself, and verify the score in your head. The criteria version string (`baseline_lexical_v1`) means the scoring formula is versioned like code — if you change the weights, you change the version string, and old and new scores remain comparable.
>
> PRS 和 PF 使用 SBERT 嵌入——这需要模型下载、GPU/CPU 推理时间，并产生难以解释的分数（"这篇论文得了0.71——为什么？"）。Dynamic-LR 的词法公式完全透明：你可以查看一篇被拒绝的论文，看到 `title_keyword_overlap: 0.10`，自己数匹配的词，并在脑子里验证分数。标准版本字符串（`baseline_lexical_v1`）意味着评分公式像代码一样版本化——如果你改变权重，你改变版本字符串，旧的和新的分数仍然可以比较。

---

## Step 15 — Filter: Accept or Reject / 第十五步：过滤：接受或拒绝

### 15.1 Stage 0: Metadata eligibility filters / 阶段 0：元数据资格过滤

```python
if not candidate.title:
    reject(candidate, reason="missing_title")
elif len(candidate.title.split()) < min_title_tokens:
    reject(candidate, reason="missing_title")
elif candidate.is_retracted and config.exclude_retracted:
    reject(candidate, reason="retracted_work")
elif candidate.is_paratext and config.exclude_paratext:
    reject(candidate, reason="paratext_work")
```

### 15.2 Stage 1: Relevance score filter / 阶段 1：相关性评分过滤

```python
if candidate.score < min_relevance_score:
    reject(candidate, reason="below_relevance_threshold",
           evidence={"threshold": 0.30, "actual_score": candidate.score,
                     "matched_terms": [...], "missing_terms": [...]})
elif strict_timeline and paper_outside_window:
    reject(candidate, reason="outside_timeline")
elif candidate.status == "merged":
    reject(candidate, reason="duplicate_merged")
else:
    accept(candidate)
```

### 15.3 What a ScreeningDecision looks like / ScreeningDecision 长什么样

For an accepted paper:
```json
{
  "decision_id": "sdec-20260624T091533-q000-s2-4b16d4",
  "paper_key": "doi:10.1145/3580305.3599572",
  "stage": "baseline_score", "decision": "include",
  "score": 0.642, "criteria_version": "baseline_lexical_v1",
  "decision_source": "rule",
  "rationale": "Score 0.642 >= threshold 0.30"
}
```

For a rejected paper:
```json
{
  "decision_id": "sdec-20260624-...",
  "stage": "baseline_score", "decision": "exclude",
  "score": 0.18,
  "rationale": "Score 0.18 < threshold 0.30",
  "evidence_json": "{\"threshold\":0.30,\"matched_terms\":[\"neural\"],\"missing_terms\":[\"uncertainty\",\"xai\"]}"
}
```

---

> ### 📊 Step 15 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Staged filters (metadata before score) / 分阶段过滤 | ★ `metadata_filter` → `baseline_score` | – | – |
> | Minimum score threshold / 最低分数阈值 | ★ `min_relevance_score` configurable | ★ `SCORE_TOP_MIN` | ★ `min_relevance_score` |
> | Batch acceptance gate / 批次接受门 | – | ★ `results_acceptable` (top/good/gap logic) | – |
> | Retracted/paratext filter / 撤回/辅文过滤 | ★ Configurable | – | ★ Yes |
> | Missing URL → reject / 缺少 URL→拒绝 | – | – | ◑ Yes (drops valid preprints) |
> | **Typed reject reason (10 codes) / 类型化拒绝原因（10 个代码）** | ★ Closed vocabulary | ◑ Free string | ◑ Free string |
> | **Reject evidence dict / 拒绝证据字典** | ★ threshold, score, matched/missing terms | – | – |
> | `ScreeningDecision` append-only record / 追加式决策记录 | ★ Yes — architecture-specific, never overwritten | – | – |
> | Decision source & criteria version / 决策来源和标准版本 | ★ `decision_source: "rule"`, `criteria_version` | – | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS uses a batch acceptance gate (`results_acceptable`) that inspects the distribution of scores across a batch and adjusts acceptance globally — this makes the accept/reject decision for one paper depend on what other papers happened to be in the same batch, which is non-deterministic across different query orderings. Dynamic-LR applies a fixed threshold independently to each paper. The `ScreeningDecision` record with its `evidence_json` field is unique: a future engineer can open any rejected paper and read exactly which vocabulary terms were matched and which were missed.
>
> PRS 使用批量接受门（`results_acceptable`），它检查批次中分数的分布并全局调整接受——这使得一篇论文的接受/拒绝决定取决于其他论文碰巧在同一批次中，这在不同查询排序中是不确定的。Dynamic-LR 对每篇论文独立应用固定阈值。带有 `evidence_json` 字段的 `ScreeningDecision` 记录是独特的：未来的工程师可以打开任何被拒绝的论文，准确读取哪些词汇词语匹配了，哪些没有匹配。

---

## Step 16 — Save Everything to the Database / 第十六步：将所有内容保存到数据库

### 16.1 One transaction wraps all writes / 一个事务包裹所有写入

```python
with conn:   # starts a transaction; auto-commits on success, auto-rolls-back on error
    for paper in accepted_papers:
        if paper.status == "new":
            conn.execute("INSERT INTO papers ...", (...))
            for id_type, id_value in paper.identifiers.as_pairs():
                if id_value:
                    conn.execute("INSERT OR IGNORE INTO paper_identifiers ...", (...))
        elif paper.status == "merged":
            conn.execute("""
                UPDATE papers SET last_seen_at=?,
                    abstract = COALESCE(NULLIF(abstract,''), ?),
                    pdf_url  = COALESCE(NULLIF(pdf_url,''), ?)
                WHERE paper_key=?
            """, (now, paper.abstract, paper.pdf_url, paper.paper_key))
```

`COALESCE(NULLIF(column,''), new_value)` = "use new_value only if column is NULL or empty string."

### 16.2 Write retrieval events / 写入检索事件

One row per provider-query occurrence — even if the paper was already in the DB:

每次数据源-查询出现一行——即使该论文已经在数据库中：

```sql
INSERT INTO retrieval_events
(event_id, run_id, architecture, paper_key, query_id, source, source_rank,
 request_fingerprint, cache_status, retrieved_at)
VALUES (...)
```

### 16.3 Write screening decisions / 写入筛选决策

```sql
INSERT INTO screening_decisions
(decision_id, paper_key, run_id, architecture, stage, decision, score,
 criteria_version, decision_source, rationale, evidence_json, created_at)
VALUES (...)
```

---

> ### 📊 Step 16 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Transactional writes / 事务性写入 | ★ `with conn:` wraps batch | ★ Batched chunks | – |
> | `retrieval_events` one-row-per-occurrence / 每次出现一行 | ★ Yes | – | – |
> | `screening_decisions` append-only / 追加式筛选决策 | ★ Yes | – | – |
> | `COALESCE` null-safe update / 空安全更新 | ★ Never overwrites non-null with null | ◑ Keep existing | ◑ Keep existing |
> | Atomic file exports (tmp + rename) / 原子文件导出 | ★ Yes | – | – |
> | Per-run artifact directory / 每次运行制品目录 | ★ `run_artifacts/{run_id}/` | ◑ `outputs/runs/{run_id}/` | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PF writes directly to NDJSON files without transactions — a crash mid-write produces a truncated file. Dynamic-LR wraps all writes for a batch in a single SQLite transaction: crash-safe by design. The `retrieval_events` table (absent from PRS and PF) is the paper trail for the acquisition layer — it records every time every provider returned every paper, even across runs, enabling source coverage analysis that neither PRS nor PF can produce.
>
> PF 直接写入 NDJSON 文件而没有事务——写入中途崩溃会产生截断的文件。Dynamic-LR 将一个批次的所有写入包装在单个 SQLite 事务中：设计上是崩溃安全的。`retrieval_events` 表（PRS 和 PF 中都没有）是采集层的纸质跟踪——它记录每个数据源每次返回每篇论文的时间，即使跨运行，使得 PRS 和 PF 都无法产生的来源覆盖分析成为可能。

---

## Step 17 — Check if We Found the Target Papers / 第十七步：检查是否找到目标论文

For each entry in `target_papers`, the pipeline runs a five-level fallback chain:

对于 `target_papers` 中的每个条目，流水线运行五级回退链：

```
Level 1: paper_identifiers table → DOI match
Level 2: paper_identifiers table → S2 ID match
Level 3: paper_identifiers table → arXiv ID match
Level 4: papers table → normalized title exact match
Level 5: Live API call → quoted title search on S2
```

Result per target:
```json
{
  "target_title":    "Attention Is All You Need",
  "must_find":       true,
  "found":           true,
  "found_by":        "paper_identifiers_doi",
  "paper_key":       "doi:10.48550/arxiv.1706.03762",
  "sources_found":   ["semantic_scholar", "openalex"],
  "was_accepted":    true
}
```

---

> ### 📊 Step 17 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Target paper detection / 目标论文检测 | ★ 5-level fallback chain | – | – |
> | Detection recorded in run artifact / 检测结果记录在制品中 | ★ `target_check.json` per run | – | – |
> | `target_paper_found_rate` metric / 目标论文找到率指标 | ★ Yes | – | – |
> | `must_find` flag (hard requirement) / `must_find` 标志（硬要求） | ★ Yes | – | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> Neither PRS nor PF has any concept of target papers. For a literature survey comparison experiment, knowing whether a specific set of canonical papers was found is the primary recall metric. Dynamic-LR's `target_papers` config block and 5-level detection chain provide a ground-truth recall check on every run without any manual inspection.
>
> PRS 和 PF 都没有目标论文的概念。对于文献调查比较实验，知道是否找到了一组特定的规范论文是主要的召回率指标。Dynamic-LR 的 `target_papers` 配置块和5级检测链在每次运行时提供基准真实召回检查，无需任何手动检查。

---

## Step 18 — Update the Query Statistics / 第十八步：更新查询统计数据

```python
for query in queries:
    accepted_this_query = count of accepted papers found by this query
    if accepted_this_query == 0:
        new_consecutive_zero = previous_consecutive_zero + 1
    else:
        new_consecutive_zero = 0   # reset

    conn.execute("""
        INSERT INTO query_state (query_id, source, query_norm, total_runs,
                                  total_candidates, total_accepted, last_run_at)
        VALUES (?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT (query_id, source) DO UPDATE SET
            total_runs       = total_runs + 1,
            total_candidates = total_candidates + ?,
            total_accepted   = total_accepted + ?,
            last_run_at      = ?
    """, ...)
```

---

> ### 📊 Step 18 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Cross-run query stats / 跨运行查询统计 | ★ `query_state` table, per-query per-source | – | – |
> | `consecutive_zero_accept` counter / 连续零接受计数器 | ★ Yes, drives loop demotion | – | – |
> | Loop policy versioned / 循环策略版本化 | ★ `loop_policy_version` on events | – | – |
> | Date-gap validation / 日期间隙验证 | ★ Post-fetch check | – | ★ `validate_fetch_results` |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> This step has no equivalent in PRS or PF. Both treat each run as independent. Dynamic-LR treats the pipeline as a loop where each run feeds the next. The `query_state` table accumulates per-query performance across the whole history of runs, and the loop-control rules (Step 5) read it to make smarter decisions on the next run. This is the mechanism that turns a single-shot retrieval tool into a self-improving system.
>
> 这个步骤在 PRS 或 PF 中没有等效项。两者都将每次运行视为独立的。Dynamic-LR 将流水线视为一个循环，每次运行为下一次提供信息。`query_state` 表在所有运行历史中积累每查询的性能，循环控制规则（第5步）读取它以在下次运行中做出更智能的决策。这是将一次性检索工具转变为自我改进系统的机制。

---

## Step 19 — Publish: Write Files for the Website / 第十九步：发布

### 19.1 The atomic write pattern / 原子写入模式

```python
def atomic_write(final_path: str, content: str):
    tmp_path = final_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    f.flush()
    os.fsync(f.fileno())
    os.replace(tmp_path, final_path)   # atomic rename
```

Readers always see either the complete old file or the complete new file. Never a partial write.

读者总是看到完整的旧文件或完整的新文件。永远不会看到部分写入。

### 19.2 Files written / 写入的文件

```
data/papers.ndjson          — one JSON object per accepted paper per line
data/rejects.ndjson         — one reject record per line
data/run_history.ndjson     — one run summary per line
data/changelog.md           — human-readable run changes
data/system_status.json     — current status (now: "finished")
site/data/papers.json       — full JSON array for the static website
site/data/rejects.json
site/data/run_history.json
site/data/system_status.json
site/data/survey_config.json
```

### 19.3 One paper in papers.ndjson / papers.ndjson 中一篇论文

```json
{
  "paper_key": "doi:10.1145/3580305.3599572",
  "title": "Explaining Neural Network Decisions via Calibrated Uncertainty",
  "score": 0.642,
  "score_components": {"title_keyword_overlap":0.30, "abstract_keyword_overlap":0.70, ...},
  "provenance": {
    "architectures_seen": ["baseline"],
    "sources_seen": ["semantic_scholar","arxiv"],
    "first_seen_by": "baseline",
    "field_sources": {"title":"semantic_scholar","abstract":"arxiv","doi":"semantic_scholar"}
  },
  "first_seen_run_id": "baseline-20260624T091533441882",
  "first_seen_at": "2026-06-24T09:17:44.123Z"
}
```

---

> ### 📊 Step 19 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Static site export (`site/data/`) / 静态站点导出 | ★ Yes | – (Flask only) | ★ Yes |
> | NDJSON exports / NDJSON 导出 | ★ Yes | – | ★ Yes |
> | **Atomic publish (tmp + rename) / 原子发布** | ★ Yes | – | – |
> | Changelog / 变更日志 | ★ `data/changelog.md` | – | – |
> | System status JSON / 系统状态 JSON | ★ Updated every phase | – | ◑ End of run only |
> | Per-paper provenance block / 每篇论文来源块 | ★ `architectures_seen`, `sources_seen`, `field_sources` | – | ◑ `source_hits` only |
> | **Deterministic sort before write / 写入前确定性排序** | ★ score desc → `paper_key` tiebreak | – | – |
> | Retro-scoring on publish / 发布时回溯评分 | – | – | ★ Yes |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PRS exports only to a Flask server with no file-based output — if the Flask server is down, there is no way to inspect the data. PF writes files but without atomic rename — a crash mid-publish leaves the site in a broken state. Dynamic-LR's `os.replace()` rename is atomic on all major operating systems: readers either see the complete previous file or the complete new file. The deterministic sort (score desc, then `paper_key` as tiebreak) means two identical runs always produce byte-for-byte identical output files.
>
> PRS 只导出到 Flask 服务器，没有基于文件的输出——如果 Flask 服务器宕机，就没有办法检查数据。PF 写文件但没有原子重命名——发布中途崩溃会让站点处于损坏状态。Dynamic-LR 的 `os.replace()` 重命名在所有主要操作系统上是原子的：读者要么看到完整的前一个文件，要么看到完整的新文件。确定性排序（分数降序，然后 `paper_key` 作为平局分隔符）意味着两次相同的运行总是产生逐字节相同的输出文件。

---

## Step 20 — Write the Run Artifacts / 第二十步：写入运行制品

```
data/baseline/run_artifacts/baseline-20260624T091533441882/
├── run_manifest.json          ← full overview of what happened
├── canonical_query_plan.json  ← queries built in Step 2
├── provider_query_plan.json   ← translations built in Step 3
├── provider_results/
│   ├── semantic_scholar.json  ← per-query API call counts and errors
│   ├── arxiv.json
│   └── openalex.json
├── normalized_candidates.json
├── dedupe_results.json
├── screening_decisions.json
├── accepted_candidates.json
├── rejected_candidates.json
├── merge_events.json
├── target_check.json
├── metrics.json
├── errors.json
└── final_report.json
```

---

> ### 📊 Step 20 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Per-run artifact directory / 每次运行制品目录 | ★ Full directory with 14 files | ◑ `outputs/runs/{run_id}/` partial | – |
> | `run_manifest.json` with `config_hash` / 运行清单 | ★ Yes | – | – |
> | `canonical_query_plan.json` + `provider_query_plan.json` / 查询计划 | ★ Both saved | – | – |
> | `screening_decisions.json` per run / 每次运行筛选决策 | ★ Yes | – | – |
> | `target_check.json` / 目标检查 | ★ Yes | – | – |
> | `metrics.json` per-source breakdown / 每数据源指标分解 | ★ Yes | ◑ Total only | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PF writes no run artifacts at all — there is no way to reconstruct what happened in a past run. PRS writes partial artifacts. Dynamic-LR's artifact directory is a complete, self-contained record: given the artifact directory and the survey config, you can reproduce every decision the pipeline made without accessing the database. The `run_manifest.json` with `config_hash` and `git_commit` is the evidence that makes two runs comparable.
>
> PF 完全不写运行制品——无法重建过去运行中发生的事情。PRS 写部分制品。Dynamic-LR 的制品目录是完整的、自包含的记录：给定制品目录和调查配置，你可以重现流水线做出的每个决定，而无需访问数据库。带有 `config_hash` 和 `git_commit` 的 `run_manifest.json` 是使两次运行可比较的证据。

---

## Step 21 — Return the Final Result / 第二十一步：返回最终结果

```python
runtime_s = time.perf_counter() - wall_start
status = "success" if not errors else "partial_success"
db.finish_run(conn, run_id, status=status, finished_at=now, metrics=metrics)

return ManagerRunResult(
    run_id        = "baseline-20260624T091533441882",
    architecture  = "baseline",
    success       = True,
    status        = "success",
    query_plan    = [...],
    acquisition_result  = {"sources": {"semantic_scholar": {...}, "arxiv": {...}, "openalex": {...}}},
    verification_result = {"method": "baseline_lexical_v1", "accepted": 87, "rejected": 536},
    dedupe_result       = {"duplicates": 198, "merged": 45, "new_papers": 87},
    target_check        = {"target_total": 3, "target_found": 3, "target_accepted": 3},
    metrics             = {"runtime_seconds": 398.5, "cache_hit_rate": 0.40, ...},
    summary = "Baseline run complete. 87 papers accepted from 1015 raw candidates."
)
```

---

> ### 📊 Step 21 — Three-Model Comparison / 三模型对比
>
> | Aspect / 方面 | Dynamic-LR | PRS | PF |
> |---|---|---|---|
> | Structured result object / 结构化结果对象 | ★ `ManagerRunResult` typed dataclass | ◑ Dict | – |
> | `partial_success` distinguished from `failure` / 部分成功与失败区分 | ★ Yes | – | – |
> | Per-source API call counts / 每数据源 API 调用数 | ★ Yes | ◑ Total only | – |
> | Cache hit/miss rate by source / 每数据源缓存命中率 | ★ Yes | – | – |
> | Duplicate / merge / possible-duplicate counts / 去重/合并/可能重复计数 | ★ All three reported | ◑ Merge only | – |
> | Target paper summary in result / 结果中的目标论文摘要 | ★ `target_found_rate` | – | – |
> | Result shared with manager layer / 结果与管理层共享 | ★ `ManagerRunResult` compatible with all architectures | ◑ Separate format | – |
>
> **Why Dynamic-LR is better / 为什么 Dynamic-LR 更好:**  
> PF returns nothing structured — the run either completes or crashes. PRS returns a dict. Dynamic-LR returns a `ManagerRunResult` dataclass that is the same type used by the single-agent and multi-agent architectures, which means the manager layer and CLI can treat all three architectures identically. The per-source breakdown of API calls and cache hits is what enables fair comparison between runs: you can see whether one run got 40% of its data from cache while another made 100% live calls, which explains runtime differences that would otherwise look like noise.
>
> PF 不返回任何结构化内容——运行要么完成要么崩溃。PRS 返回一个字典。Dynamic-LR 返回一个 `ManagerRunResult` 数据类，与单智能体和多智能体架构使用的类型相同，这意味着管理层和 CLI 可以同等对待所有三种架构。API 调用和缓存命中的每数据源分解是使运行之间公平比较成为可能的：你可以看到一次运行是否从缓存获得了40%的数据，而另一次进行了100%的实时调用，这解释了否则看起来像噪音的运行时差异。

---

## How Errors Are Handled — The Complete Guide / 错误如何处理——完整指南

| What goes wrong / 出了什么问题 | Dynamic-LR | PRS | PF |
|---|---|---|---|
| Config bad / 配置错误 | ★ `ConfigError` → immediate structured failure | Crash / traceback | Crash / traceback |
| API fails after retries / API 重试后失败 | ★ Log → skip query → `partial_success` | ◑ Raises exception | ◑ Logs only |
| Normalization fails / 规范化失败 | ★ Typed `malformed_metadata` reject | ◑ Skip silently | ◑ Skip silently |
| Provider times out / 数据源超时 | ★ Partial failure, others continue | Stop run | ◑ Caught but not recorded |
| Database write fails / 数据库写入失败 | ★ `DatabaseWriteError` logged, continue | Crash | – |
| Site export fails / 站点导出失败 | ★ `PublishError`, existing files unchanged | – | Partial overwrite |
| Fuzzy title match / 模糊标题匹配 | ★ `possible_duplicate` flag, not merged | Auto-merge | Auto-merge |

**Run status meanings / 运行状态含义:**
```
"success"         — everything worked perfectly
"partial_success" — some queries/papers/exports failed but data was saved
"failure"         — config could not be loaded (the only hard stop)
```

---

## How the Loop Gets Smarter Over Time / 循环如何随时间变得更聪明

```
Run 1: "XAI" → 0 accepted → consecutive_zero_accept = 1
Run 2: "XAI" → 0 accepted → consecutive_zero_accept = 2
Run 3: "XAI" → 0 accepted → consecutive_zero_accept = 3
Run 4: Loop control reads counter = 3 → removes "XAI" from query list
Run 5+: "XAI" still excluded until a future run accepts a paper from it → counter resets to 0
```

Neither PRS nor PF have this mechanism. PRS relies on an LLM to decide what to search next (non-deterministic, model-dependent). PF has no cross-run learning at all.

PRS 和 PF 都没有这个机制。PRS 依赖 LLM 来决定下一步搜索什么（非确定性，依赖模型）。PF 完全没有跨运行学习。

---

## Summary: The Full Flow in One Picture / 总结：一张图的完整流程

```
survey_config.json
        │
        ▼
[Step 1] Load config → SurveyConfig (fail-fast ConfigError)
        │
        ▼
[Step 2] Build queries → topic + questions + hints + combined (freq-weighted)
        │
        ▼
[Step 3] Translate → S2 plain / arXiv all:AND / OA search+filter
        │
        ▼
[Step 4] Open SQLite → create tables → start run row
        │
        ▼
[Step 5] Loop control → read query_state → remove 3-strike queries
        │
        ▼
[Step 6] ─────────────────────────────────────────────────────
         asyncio.gather (all three at the same time)
         │  S2:    cache? → HTTP → retry (det. jitter) → JSON
         │  arXiv: cache? → HTTP → retry → Atom XML → per-record date filter
         │  OA:    cache? → HTTP → cursor pages → reconstruct abstract
         ─────────────────────────────────────────────────────
        │
        ▼
[Steps 10-11] Normalize per-provider → validate → repair whitespace
        │
        ▼
[Step 12] Identity: DOI→arXiv→OA→S2→corpus→fp:  assign stable paper_key
        │
        ▼
[Step 13] Dedup within run → dedup vs. SQLite DB
          completeness merge → possible_duplicate flag (never auto-merge on title)
        │
        ▼
[Step 14] Score: 6 lexical components → weighted sum → store all components
        │
        ▼
[Step 15] Filter: metadata_filter stage → baseline_score stage
          → ScreeningDecision records with evidence_json
        │
        ▼
[Step 16] Persist: one transaction → papers, paper_identifiers,
                   retrieval_events, screening_decisions, merge_events
        │
        ▼
[Step 17] Target check → 5-level fallback chain
        │
        ▼
[Step 18] Update query_state → consecutive_zero_accept counters
        │
        ▼
[Step 19] Publish → atomic writes → data/*.ndjson → site/data/*.json
        │
        ▼
[Step 20] Write run artifacts → 14 files in run_artifacts/{run_id}/
        │
        ▼
[Step 21] Return ManagerRunResult → CLI prints summary
        │
        ▼
       DONE — next run reads query_state and is a bit smarter
```

---

## Overall Verdict / 总体评判

| Dimension / 维度 | Dynamic-LR | PRS | PF |
|---|:---:|:---:|:---:|
| Provider coverage / 数据源覆盖 | ★ 3 (S2+arXiv+OA) | 1 (S2 only) | 2 (S2+arXiv) |
| Determinism / 确定性 | ★ Full (no random calls) | ◑ Optional LLM + random jitter | ★ Full |
| Audit trail / 审计跟踪 | ★ retrieval_events + screening_decisions + raw refs | ◑ Partial | – |
| Cross-run learning / 跨运行学习 | ★ query_state + loop control | ◑ LLM-driven (non-det.) | – |
| Date filter correctness (arXiv) / 日期过滤正确性 | ★ per-record `continue` | ◑ per-page `break` (bug) | ◑ per-page `break` (bug) |
| Identity safety / 身份安全性 | ★ 8 levels, no auto-fuzzy-merge | ◑ Auto-merge on title | ◑ Auto-merge on title |
| Crash safety / 崩溃安全性 | ★ SQLite transactions + atomic rename | ◑ Transactions only | – |
| Score transparency / 分数透明性 | ★ 6 named lexical weights | ◑ SBERT (opaque) | ◑ SBERT (opaque) |
| Failure isolation / 故障隔离 | ★ partial_success for any sub-failure | – | ◑ Partial |

---

*This document covers every substep of the Dynamic-LR baseline pipeline with three-system comparisons at each step. For the formal specification, see `CLAUDE.md`. For the full comparison tables, see `baseline_comparison/baseline_synthesis.md`.*

*本文档涵盖了 Dynamic-LR 基线流水线的每个子步骤，并在每个步骤处进行了三系统比较。有关正式规范，请参见 `CLAUDE.md`。有关完整比较表，请参见 `baseline_comparison/baseline_synthesis.md`。*
