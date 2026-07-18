# Agentic RAG 个人经历助手项目执行计划

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.7 |
| 文档状态 | 执行中 |
| 关联文档 | [PRD](./PRD.md)、[架构设计](./architecture.md)、[技术选型](./technology-selection.md)、[M4 Web MVP 报告](./m4-web-mvp-report.md)、[M4.2 LLM Answer Generator 报告](./m4.2-llm-answer-generator-report.md) |
| 更新时间 | 2026-07-18 |

## 2. 执行原则

1. 先完成一个项目的端到端闭环，再扩展知识数量和功能范围。
2. 个人事实只来自人工审核的知识文档，不由模型补写。
3. 每个阶段都设置可执行的验收门槛，未达到门槛不进入复杂优化。
4. 检索、生成、引用和拒答分别评测，避免只观察最终回答。
5. MVP 主线是 Agentic RAG：先用自有轻量 Router / Tool / Policy 编排，复杂度证明必要后再引入成熟 Agent 框架。
6. 模型、Embedding 和生产平台通过 Spike 与数据决定，不凭偏好提前锁定。
7. 项目是个人作品集，不实现收费、用户体系、商业运营和企业级 SLA。

## 3. 当前状态

| 交付物 | 状态 | 说明 |
| --- | --- | --- |
| PRD v0.4 | 已完成 | 已修正为 Agentic RAG 工程项目定位，个人经历是应用场景 |
| 架构设计 v0.3 | 已完成 | 已补充 Agentic Router、Safe Tool Layer 和真实 LLM 演进边界 |
| 技术选型 v1.4 | 已完成 | 已明确不先引入 LangGraph，并已接入自有轻量 Agentic RAG 生成链路 |
| 作品集定位 | 已确认 | 低流量、单候选人、非商业 SaaS |
| 产品关键决策 | 部分待确认 | 已确认默认第三人称、第一人称稿件例外与简历级公开范围；仍需确认语言、联系方式和访问地区 |
| 知识库模板 | 已建立 | 已形成个人资料、简历、项目模板和动态项目注册规则 |
| 已发布知识内容 | 持续补全 | 个人资料、结构化简历、Agentic RAG 项目自身完整资料和 Skillvar 核心资料已发布；Skillvar 源码审查记录保持私有草稿 |
| 评测集 | 38/38 已启用 | M5 真实面试与边界问题全部启用；MVP 当前 22 条启用 |
| 工程代码 | M5.4 已完成，部署暂缓 | 已完成公开知识加载、结构化切块、BM25/pgvector/E5 检索、动态项目作用域、确定性/LLM 回答、SSE、Web、评测、查询质量优化和最小可观测性 |

## 4. 里程碑总览

| 里程碑 | 目标 | 主要交付物 |
| --- | --- | --- |
| M0 产品与数据准备 | 明确边界，准备一个真实项目和评测基线 | 决策清单、知识文档、30 条评测数据 |
| M1 技术 Spike | 验证最关键且不确定的技术链路 | Embedding 对比、pgvector 检索、流式响应验证 |
| M2 工程骨架 | 建立可运行、可测试、可复现的项目 | frontend、backend、Compose、迁移、CI |
| M3 终端 RAG 闭环 | 完成入库、检索、回答、引用和拒答 | ingest、ask、eval 命令 |
| M4 Web MVP | 提供可用的面试官对话界面 | 首页、对话、流式回答、引用、多轮追问 |
| M4.2 真实 LLM 与 Agentic RAG | 把检索证据交给真实 LLM 生成，并建立轻量 Agentic 编排 | LLM Provider、Answer Generator、Router、Tool Layer、Prompt、引用校验 |
| M4.3 Agent 评测与可观测性 | 评测 Agent 路由、生成忠实度、引用和拒答 | 路由评测、LLM 回答评测、Trace 字段、失败归因 |
| M5 工程化上线 | 提供低成本、稳定的公网展示 | HTTPS、限流、日志、知识重建、简单部署流水线 |
| M6 高阶 Agent 演进 | 在核心链路稳定后增加更复杂 Agent 能力 | 模拟面试、多步骤状态工作流、人工确认 |

---

## 5. M0：产品与数据准备

### 5.1 目标

建立首个可验证知识域，并让后续代码开发有明确输入和质量标准。

### 5.2 任务

- [ ] 确认 MVP 语言。
- [x] 确认回答人称：默认第三人称；用户明确要求自我介绍稿、面试口述稿或第一人称时可切换。
- [x] 确认简历级公开边界：实习公司名、Skillvar 与 OntoCore 项目名及简历已有描述允许公开。
- [x] 确认 MVP 不在服务端保存完整访客对话。
- [x] 确认 MVP 不使用 `answer_only`。
- [ ] 确认主要访问地区和大致部署地区。
- [x] 填写个人简介和技能文档草稿。
- [x] 选择 Skillvar 作为首个代表项目。
- [x] 完成 Skillvar 的背景、职责、架构、难点、成果、功能、调用链和复盘文档。
- [x] 完成 Agentic RAG 个人经历助手项目自身的概述、职责、架构、功能、调用链、难点、成果和复盘文档。
- [x] 完成 OntoCore 项目的概述、职责、架构、功能、调用链、难点、成果和复盘文档，并保留源码核验私有草稿。
- [x] 审核量化结果和核心职责描述：当前无可公开指标，产品由其他成员负责，本人负责开发、测试和部署运维。
- [x] 完成不少于 30 条评测数据骨架。

### 5.3 验收门槛

- 至少一个项目的核心资料完整。
- 每份知识文档具有合法 Front Matter。
- 每个个人事实经过候选人确认。
- 个人贡献与团队贡献明确区分。
- 所有文档具有明确可见性。
- 至少 30 条评测数据可以被 JSONL 解析。
- 评测集包含正常回答、无证据拒答、隐私和多轮问题。

### 5.4 当前阻塞信息

| 编号 | 待确认问题 | 默认不采取的行为 | 影响 |
| --- | --- | --- | --- |
| D-001 | MVP 只支持中文还是中英文 | 不自动增加英文内容 | Prompt、Embedding 评测和 UI |
| D-002 | 回答人称 | 已决定：默认第三人称介绍候选人；明确要求稿件/口述/第一人称时使用第一人称 | 已关闭 |
| D-003 | 哪些资料允许公开 | Skillvar、Agentic RAG 项目自身和 OntoCore 的公开知识文档已发布；源码核验记录保持私有草稿，其他项目源码细节仍需逐项审核 | 部分关闭 |
| D-004 | 服务端是否保存完整对话 | 已决定：MVP 不保存，浏览器保留当前短期历史 | 已关闭 |
| D-005 | `answer_only` 是否首版需要 | 已决定：不需要，只使用 public/private | 已关闭 |
| D-006 | 主要访问地区 | 不锁定云平台和生产模型 | 部署与模型可用性 |

---

## 6. M1：关键技术 Spike

### 6.1 目标

用最少代码验证会影响架构和数据设计的高风险假设。

### 6.2 Spike A：Embedding 与中文检索

- [x] 建立确定性的 Markdown 加载、发布过滤和结构化切块基线。
- [x] 建立无模型词法检索基线与 Top-1、Top-3、Top-5 评测入口。
- [x] 为 16 条启用用例补充 Chunk 级期望证据标注。
- [x] 比较 BGE small zh v1.5 与 Multilingual E5 small 两个真实候选。
- [x] 临时选择 Multilingual E5 small、384 维和余弦距离进入 pgvector Spike。
- 选取 10～15 条有明确证据的问题。
- 比较 2～3 个候选 Embedding 模型。
- 记录 Top-1、Top-3、Top-5 命中率、延迟、维度和成本。
- 覆盖项目名、缩写、技术名、职责和数字类问题。

第一阶段报告见 [M1 技术 Spike 执行报告](./m1-spike-report.md)。

通过门槛：选择一个首版 Embedding，确定向量维度和距离度量。

### 6.3 Spike B：PostgreSQL + pgvector

- [x] 创建最小 Document、Chunk、ChunkEmbedding 表。
- [x] 导入当前 5 份公开文档和 38 个 Chunk。
- [x] 验证可见性过滤发生在 SQL 查询阶段。
- [x] 验证 pgvector 精确余弦 Top-K 与内存向量 Top-5 一致。
- [x] 验证重复导入幂等。
- [x] 验证 Embedding revision 查询隔离。
- [x] 测量当前小数据量下的查询向量编码延迟。

通过门槛：已通过。精确检索满足当前正确性要求，权限过滤测试通过。

### 6.4 Spike C：流式响应

- [x] 使用 FastAPI 返回 `text/event-stream`。
- [x] 使用 `fetch` + `ReadableStream` 消费 POST 响应。
- [x] 验证增量文本、结束、错误和取消事件。
- [x] 验证客户端 abort 后服务端停止生成。
- [ ] 在目标部署候选环境验证代理不缓冲。

通过门槛：本地已通过。客户端能稳定区分完成、失败和取消状态；部署代理缓冲留到平台选择阶段验证。

### 6.5 Spike D：LLM 候选

- [x] 建立 Fake LLM Provider，固定流式事件和引用输出契约。
- [x] 使用 oracle context 隔离检索误差，验证生成层契约。
- [x] 评测 required facts、forbidden facts、引用合法性和拒答准确性。
- [x] 将安全/证据不足拒答用例纳入 LLM 层评测。
- [ ] 使用同一检索上下文和 Prompt 比较候选真实模型。
- [ ] 记录真实模型首 Token 延迟、总延迟、错误率和每 100 次问答估算成本。
- [x] 选择首个真实 LLM Provider 配置目标：OpenAI-compatible 接口 + `deepseek-v4-flash`，并保留 Fake / deterministic Provider。

通过门槛：部分通过。Fake Provider 基线已完成；M4.2 已实现真实 LLM Provider 代码路径，仍需要 API Key 后完成真实模型质量、延迟和成本评测。

---

## 7. M2：工程骨架

### 7.1 任务

- [x] 初始化 Git 和基础忽略规则。
- [x] 创建 Next.js、TypeScript、Tailwind 前端。
- [x] 创建 Python 3.13、uv、FastAPI 后端。
- [x] 配置 pnpm 与 uv lockfile。
- [x] 配置 Ruff、mypy、pytest、ESLint、Vitest。
- [x] 创建 PostgreSQL + pgvector Compose 服务。
- [x] 建立 SQLAlchemy Model 和首个 Alembic Migration。
- [x] 建立 Fake LLM Provider。
- [x] 建立健康检查和结构化日志骨架。
- [x] 建立 CI 基础流水线。

### 7.2 验收门槛

```text
make dev
make lint
make test
make migrate
```

以上入口可运行；新环境能按照 README 启动；密钥和本地数据不进入版本库。

---

## 8. M3：终端版 RAG 闭环

### 8.1 任务顺序

1. [x] Front Matter 校验与 Markdown Parser。
2. [x] 结构优先 Chunker。
3. [x] 内容哈希与幂等导入基础。
4. [x] Embedding Provider 与批量向量化正式接入。
5. [x] Knowledge Repository 与 Top-K 检索基线：当前为内存 BM25 + 轻量意图重排。
6. [x] Evidence Policy。
7. [x] Context Builder。
8. [x] LLM Provider 与回答生成基线：当前为确定性证据组织器，不调用真实 LLM。
9. [x] Citation Validator。
10. [x] CLI 问答和离线评测 Runner。

### 8.2 建议命令

```text
make ingest
make ask QUESTION="你在这个项目中具体负责什么？"
make eval
```

### 8.3 验收门槛

- 重复导入相同内容不产生重复 Chunk 或重复 Embedding。
- 修改一个 Section 只更新受影响内容。
- 调试输出可查看 Top-K、分数和来源。
- 事实性回答包含合法引用。
- 无证据问题能够正确拒答。
- `private` 内容不会进入检索候选和模型上下文。
- 生成并保存第一份评测基线。

### 8.4 当前 M3 基线

已生成第一份 M3 终端版 RAG 基线：`evals/results/m3-baseline.json`。

```text
case_count: 16
citation_hit_rate: 100%
mean_required_recall: 100%
forbidden_pass_rate: 100%
retrieval_strategy: in_memory_bm25_with_intent_rerank
answer_strategy: deterministic_evidence_composer
```

当前 M3 先验证工程闭环和可评测性；真实 LLM Provider 已在 M4.2 作为增量能力接入。

### 8.5 M3.2：pgvector 入库与检索闭环

已完成：

- [x] Embedding Provider 接口。
- [x] 本地确定性 384 维 Hash Embedding 工程基线。
- [x] PostgreSQL + pgvector 入库器。
- [x] documents、chunks、chunk_embeddings 幂等 upsert。
- [x] SQL 阶段过滤 `visibility = public` 且 `status = published`。
- [x] SQL 阶段按 `embedding_model + embedding_revision + embedding_dimension` 隔离。
- [x] pgvector 检索后端接入同一套 RAG Service。
- [x] `make ingest-db`、`make ask-db`、`make eval-db`。
- [x] 生成 `evals/results/m3.2-pgvector-baseline.json`。

当前 M3.2 基线：

```text
case_count: 16
citation_hit_rate: 100%
mean_required_recall: 100%
forbidden_pass_rate: 100%
embedding_model: local-hashing-embedding
embedding_revision: m3.2-v1
retrieval_strategy: pgvector_hash_embedding_with_intent_rerank
```

### 8.6 M3.3：真实 Embedding Provider

已完成：

- [x] 接入 `sentence-transformers` 真实模型依赖。
- [x] 实现 `SentenceTransformerEmbeddingProvider`。
- [x] 固定 `intfloat/multilingual-e5-small` 的 Hugging Face revision。
- [x] 使用 E5 的 `query:` / `passage:` 前缀。
- [x] E5 输出 384 维 L2 归一化向量。
- [x] E5 入库到 `chunk_embeddings`，并通过 `embedding_model + embedding_revision + embedding_dimension` 隔离。
- [x] `make ingest-db-e5`、`make ask-db-e5`、`make eval-db-e5`。
- [x] 生成 `evals/results/m3.3-e5-pgvector-baseline.json`。

当前 M3.3 基线：

```text
case_count: 16
citation_hit_rate: 100%
mean_required_recall: 100%
forbidden_pass_rate: 100%
embedding_model: multilingual-e5-small
embedding_revision: 614241f622f53c4eeff9890bdc4f31cfecc418b3
retrieval_strategy: pgvector_dense_embedding_with_intent_rerank
```

注意：当前评测集较小，E5 与 Hashing 都达到 100%。这说明当前用例可以被工程规则稳定覆盖，但不足以证明真实语义检索已经充分泛化。后续需要扩充无关键词改写、跨文档追问、同义表达和英文问题。

### 8.7 M3.4：语义压力评测

已完成：

- [x] 新增 `evals/datasets/m3.4-semantic-v1.jsonl`。
- [x] 评测英文问题、中文同义改写、弱关键词和多轮指代。
- [x] 为评测结果增加 `document_hit_rate`。
- [x] 对比 memory baseline、Hashing pgvector 和 E5 pgvector。
- [x] 生成 M3.4 语义评测报告。

当前 M3.4 结果：

```text
memory baseline:
  document_hit_rate: 61.54%
  citation_hit_rate: 61.54%
  mean_required_recall: 42.31%

hashing pgvector:
  document_hit_rate: 92.31%
  citation_hit_rate: 53.85%
  mean_required_recall: 56.41%

E5 pgvector:
  document_hit_rate: 100%
  citation_hit_rate: 84.62%
  mean_required_recall: 76.92%
```

结论：真实 E5 Embedding 在语义压力集上明显优于 Hashing 和内存 BM25。下一步应优化查询理解、多轮改写和 rerank，而不是继续单纯更换 Embedding 模型。

### 8.8 M3.5：查询理解优化

已完成：

- [x] 为权限难点、多轮英文指代建立 `challenge` 意图。
- [x] 为 MCP / CLI、自动化工具、命令行和 Agent 工作流建立 `mcp_cli` 意图。
- [x] 为 ChromaDB 不可用、BM25-only、MongoDB 正则搜索兜底建立 `retrieval_fallback` 意图。
- [x] 修正意图优先级，职责和团队边界问题优先于 MCP / CLI，避免主评测集回归。
- [x] 收紧检索降级触发条件，只有“检索相关信号 + 降级相关信号”同时出现时触发。
- [x] 增加 M3.5 专用评测结果文件。
- [x] 生成 M3.5 查询理解优化报告。

当前 M3.5 语义压力集结果：

```text
memory baseline:
  document_hit_rate: 76.92%
  citation_hit_rate: 76.92%
  mean_required_recall: 61.54%

hashing pgvector:
  document_hit_rate: 100%
  citation_hit_rate: 84.62%
  mean_required_recall: 76.92%

E5 pgvector:
  document_hit_rate: 100%
  citation_hit_rate: 100%
  mean_required_recall: 100%
```

MVP 主评测集 `mvp-v1.jsonl` 在 memory、hashing pgvector 和 E5 pgvector 下仍保持 100%，未出现回归。

结论：当前 RAG 主链路已经具备可用的检索、引用、拒答、评测和查询理解基础。继续优化可以进入 M3.6 rerank / query rewrite，但从作品集交付角度，更建议进入 M4 Web MVP。

---

## 9. M4：Web MVP

### 9.1 任务

- [x] 候选人首页和推荐问题。
- [x] 浏览器短期会话状态。
- [x] POST 流式问答协议。
- [x] 对话输入、流式正文和状态管理。
- [x] 引用卡片和安全片段展示。
- [x] 无证据、受限、异常和重试状态。
- [x] 停止生成与新建会话。
- [x] 基础多轮追问。
- [ ] 用户反馈（P2，MVP 默认不实现）。

### 9.2 验收门槛

- 浏览器可完成一次带引用的端到端问答。
- 同一项目至少支持 3 轮连续追问。
- 前端能区分成功、拒答、取消和错误。
- 引用不可访问内部路径或私密原文。
- Fake Provider 端到端测试通过。

### 9.3 当前 M4 结果

已生成 M4 Web MVP 报告：[M4 Web MVP 报告](./m4-web-mvp-report.md)。

当前 Web 端具备：

- 推荐问题入口。
- 流式问答正文。
- 引用证据卡片。
- 拒答、异常和停止生成状态。
- `sessionStorage` 浏览器短期历史。
- 最近历史随请求发送给 API，支持基础多轮追问。

当前 M4 仍是本地 Web MVP，不包含公网部署、用户系统和服务端对话落库；M4.2 已支持真实 LLM 生成链路，但还需要使用真实 API Key 联调并做回答质量评测。

---

## 10. M4.2：真实 LLM 与 Agentic RAG 编排

### 10.1 目标

把当前“检索 + 确定性证据组织器”升级为真正的 RAG 生成链路，并开始体现 Agent 应用开发工程能力。

目标链路：

```text
用户问题
→ Agentic Router 判断问题类型和风险
→ 安全工具层调用 retrieve_knowledge
→ Context Builder 构造受控上下文
→ 真实 LLM Provider 流式生成回答
→ Citation Validator 校验引用
→ 前端展示正文、引用和拒答状态
```

### 10.2 任务

- [x] 增加 LLM 环境变量：`LLM_PROVIDER`、`LLM_API_KEY`、`LLM_MODEL`、`LLM_BASE_URL`。
- [x] 抽象 `AnswerGenerator`，保留 `deterministic` 实现并新增 `llm` 实现。
- [x] 实现 OpenAI-compatible LLM Provider，优先兼容 OpenAI、DeepSeek 或其他兼容接口。
- [x] 设计 RAG Prompt：证据边界、职责边界、引用规则、拒答规则和输出风格。
- [x] 实现 Context Builder，把 Chunk 转换为稳定引用 ID 的 Prompt 上下文。
- [ ] 增加 Agentic Router 的最小版本：profile、project、responsibility、challenge、capability、restricted、out_of_scope。
- [ ] 将检索、上下文构造、生成、拒答和引用校验封装为安全内部工具。
- [x] 让 `/api/chat/stream` 在不改前端协议的情况下支持真实 LLM 流式输出。
- [ ] 增加 LLM 回答评测：忠实度、引用合法性、拒答准确率、职责边界和表达质量。
- [x] 更新 README、技术选型、架构和 M4.2 报告。

### 10.3 验收门槛

- 没有 LLM API Key 时，系统仍可回退到 deterministic 生成器用于开发和评测。
- 配置 LLM API Key 后，前端能看到真实 LLM 的流式自然回答。
- LLM 回答只使用本次提供的公开 Chunk，不编造个人事实。
- 引用 ID 必须来自本次检索上下文；伪造引用会被拦截或标记。
- 无证据、受限和提示注入问题仍能正确拒答。
- 至少 16 条主评测集和 13 条语义压力集可运行，并记录 deterministic 与 LLM 的差异。

---

## 11. M4.3：Agent 评测与可观测性

### 11.1 目标

让项目不只是“能调模型回答”，而是能解释一次 Agentic RAG 失败发生在哪里。

### 11.2 任务

- [ ] 增加路由评测：问题应进入哪个 Agentic Route。
- [ ] 增加回答忠实度评测：回答事实是否被引用证据支持。
- [ ] 增加引用支持度评测：引用是否真正支持回答中的关键结论。
- [ ] 增加拒答回归测试：隐私、系统提示词、无证据经历和越权问题。
- [ ] 记录每次请求的 route、retrieval_strategy、top_k、context_chunk_ids、generator、model_id 和耗时。
- [ ] 为前端或调试 CLI 提供非敏感 debug 输出。

---

## 12. M5：工程化上线

### 12.1 任务

- [ ] Web/API 多阶段 Dockerfile。
- [ ] 生产数据库和迁移流程。
- [ ] 自定义域名和 HTTPS。
- [ ] 存活与就绪检查。
- [ ] 应用与边缘限流。
- [ ] 模型超时、有限重试和取消传播。
- [ ] 结构化日志、Trace ID、Token 和成本记录。
- [ ] 验证从版本化知识源重建向量数据。
- [ ] 测试环境、生产环境和 CI/CD。
- [ ] 隐私说明和 AI 生成提示。

### 12.2 验收门槛

- 公网 HTTPS 地址可访问。
- API Key 不出现在前端、镜像和版本库。
- 流式响应经过完整生产链路仍保持增量输出。
- 应用异常后能够自动恢复。
- 能使用 Request ID 定位一次失败请求。
- 知识源可恢复，并能通过受控命令重建数据库索引。
- 生产发布前评测指标不低于已接受基线。

---

## 13. M6：高阶 Agent 演进

仅当真实 LLM 与基础 Agentic RAG 链路稳定后开始。候选能力包括：

- 个人简介、单项目、多项目比较的动态路由。
- 模拟面试状态机。
- 根据面试官背景调整讲解深度。
- 多步骤检索、计划、暂停和恢复。
- 高风险工具调用的人工确认。

进入条件：至少两项需求无法由轻量 Router / Tool / Policy 编排合理表达，并且 Web MVP、真实 LLM 生成和 Agent 评测都具备稳定基线。

---

## 14. 推荐工作节奏

每个迭代遵循：

```text
选择一个可验证目标
→ 先补对应测试或评测样例
→ 实现最小改动
→ 本地验证
→ 记录指标与取舍
→ 更新文档或 ADR
```

每次只优化一个主要变量。例如调整 Chunk 策略时，不同时更换 Embedding、Top-K 和 Prompt，否则无法判断指标变化来源。

## 15. 下一执行点

当前建议先做 M4.2 真实 Key 联调，然后进入 M4.3 LLM / Agent 评测：

1. 在本地 `.env` 配置 OpenAI-compatible Base URL、API Key 和 `deepseek-v4-flash`。
2. 启动前后端，人工体验典型问题、追问、拒答和引用卡片。
3. 记录坏例子：幻觉、答非所问、引用不支撑、拒答过度或拒答不足。
4. 增加 LLM/Agent 评测，比较 deterministic 与真实 LLM 的差异。
5. 评估是否需要更强 Router、Citation Validator 或结构化输出。
6. 在真实 LLM 链路稳定后再进入部署和前端体验打磨。
