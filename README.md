# Agentic RAG Self Introduction Assistant

以个人经历知识库为应用场景的 Agentic RAG 工程项目。项目目标不是只做一个简历问答网页，而是展示从知识治理、检索、上下文构造、LLM 生成、引用校验、拒答评测到工程化部署的完整 AI 应用落地能力。

当前阶段：RAG 检索闭环 + Web 展示已完成；M4.2 已接入真实 LLM Provider 与 RAG Answer Generator；M5.1～M5.4 已完成问答评测、查询质量优化与最小可观测性；当前优先补全个人资料和多个项目的公开知识，暂缓部署。

## 本地启动

```bash
make install
make dev
```

API 默认地址：

```text
http://127.0.0.1:8000
```

Web 默认地址：

```text
http://127.0.0.1:3000
```

如需启用真实 LLM 生成，在本地 `.env` 中配置：

```env
ANSWER_GENERATOR=llm
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=你的 OpenAI-compatible API Base URL
LLM_API_KEY=你的 API Key
LLM_MODEL=deepseek-v4-flash
LLM_TEMPERATURE=0.2
```

如果不配置这些值，默认 `ANSWER_GENERATOR=deterministic`，项目仍会使用确定性证据回答器，适合本地 smoke test、CI 和 RAG 检索基线评测。

## 常用命令

```bash
make lint
make test
make migrate
make build
make check-knowledge
make ingest
make ingest-db
make ingest-db-e5
make ask QUESTION="你在 Skillvar 中具体负责什么？"
make ask-db QUESTION="你在 Skillvar 中具体负责什么？"
make ask-db-e5 QUESTION="你在 Skillvar 中具体负责什么？"
make eval
make eval-semantic
make eval-m35-semantic
make eval-db
make eval-db-e5
make eval-db-semantic
make eval-db-semantic-e5
make eval-db-m35-semantic
make eval-db-m35-semantic-e5
make eval-m5-llm
```

## 面试展示能力

当前 Web 端不仅提供问答，还会展示几类面试官容易感知的工程能力：

- 首屏说明 RAG 链路：知识治理、检索、RAG Prompt、LLM 生成、引用、拒答和 Trace。
- 推荐问题按个人背景、项目经历、职责边界、技术深挖分组，避免只围绕单个项目。
- 每次回答附带公开证据卡片，默认展示最关键证据，可展开查看更多 Chunk。
- 每次回答附带非敏感调试链路，包括 route、intent、project_id、generation_strategy、Trace ID、命中 Chunk 和延迟。
- 拒答被视为产品边界能力：公开知识库证据不足、范围外或敏感内容时明确说明，而不是编造答案。

## 添加新项目知识

复制 `knowledge/projects/_template/`，填写项目文档并将确认可公开的文件设为
`visibility: public`、`status: published`。Router 会从 `project_id`、标题和可选
`aliases` 自动识别新项目，不需要修改代码。运行 `make ingest` 可检查动态项目
注册表；内存模式随后重启 API，pgvector 模式还需重新执行 `make ingest-db-e5`。

添加或替换知识库后，建议先执行：

```bash
make check-knowledge
make ingest
```

`make check-knowledge` 会检查：

- Markdown 是否包含必需 Front Matter：`document_id`、`title`、`category`、`visibility`、`status`、`updated_at`。
- `visibility` 是否为 `public` 或 `private`，`status` 是否为 `draft` 或 `published`。
- `document_id` 是否重复。
- `public + published` 文档正文是否为空。
- `knowledge/projects/**` 下的公开项目文档是否设置了 `project_id`，否则动态项目路由无法稳定识别。

如果希望别人下载这个仓库后使用自己的知识库，最小流程是：

1. 复制 `knowledge/projects/_template/` 为自己的项目目录。
2. 填写公开可展示的项目概述、职责、架构、难点、成果和复盘。
3. 给每份文档设置唯一 `document_id`，同一项目使用相同 `project_id`，并补充 `aliases`。
4. 只把确认可公开的文件设为 `visibility: public`、`status: published`。
5. 执行 `make check-knowledge` 和 `make ingest`。
6. 重启 API；如果使用 pgvector，则执行 `make ingest-db-e5` 后再启动服务。

不建议上传到 GitHub 的内容：

- 原始简历 Word/PDF。
- 从源码压缩包、内部系统或私有仓库整理出的未脱敏原文。
- 切分前的私有 Markdown 原文。
- 评测集中包含隐私、公司内部信息或未公开事实的样例。
- `.env`、API Key、数据库连接串、LiteLLMOps Key 等配置。

这个仓库更适合作为“RAG 个人经历助手模板 + 工程实现”开源；个人真实知识库可以保留在本地或服务器私有目录中。

数据库迁移需要先启动 PostgreSQL + pgvector：

```bash
docker compose up -d postgres
make migrate
```

## 当前边界

- 当前已经完成 RAG 检索、证据组织、引用返回、Web 流式展示和真实 LLM 生成链路。
- M3 当前使用本地公开 Markdown 知识库、内存 BM25 检索和确定性证据生成器；M4.2 新增可插拔 LLM Answer Generator。
- `make eval` 会生成 `evals/results/m3-baseline.json`，用于记录当前 RAG 基线。
- M3.2 已提供 PostgreSQL + pgvector 入库和检索入口，使用本地确定性 384 维 Hash Embedding 验证工程链路。
- `make eval-db` 会生成 `evals/results/m3.2-pgvector-baseline.json`，需要先完成数据库迁移和入库。
- M3.3 已接入真实 Embedding Provider：`intfloat/multilingual-e5-small`，固定 Hugging Face revision，384 维。
- `make eval-db-e5` 会生成 `evals/results/m3.3-e5-pgvector-baseline.json`，首次运行会下载 Hugging Face 模型。
- M3.4 已新增语义压力评测集：`evals/datasets/m3.4-semantic-v1.jsonl`，用于比较 BM25、Hashing 和 E5 在英文/同义/弱关键词问题上的差异。
- M3.5 已新增轻量查询理解：针对权限难点、MCP/CLI、检索降级等问题做确定性意图识别、查询扩展和重排加权。
- M3.5 后 E5 pgvector 在 13 条语义压力用例上达到 Citation Hit / Document Hit / Required Recall 均 100%。
- M4 已提供浏览器对话界面：推荐问题、流式回答、引用卡片、停止生成、错误/拒答状态和浏览器短期多轮历史。
- API 默认使用 `RAG_BACKEND=memory`；如需让 API 使用 pgvector，可设置 `RAG_BACKEND=pgvector` 和 `EMBEDDING_PROVIDER=multilingual-e5-small`，并先完成迁移与入库。
- M4.2 已接入 OpenAI-compatible LLM Provider：设置 `ANSWER_GENERATOR=llm` 后，API 会把检索到的 Chunk、轻量 Router 意图和最近对话历史组织成 RAG Prompt，再交给模型生成自然回答。
- M5 面试评测集已扩展为 45 条真实面试与边界问题，覆盖个人资料、Agentic RAG 项目自身、Skillvar 和 OntoCore。`make eval-m5-llm` 会使用本地 `.env` 中的 OpenAI-compatible 配置，并记录 Route、回答、引用、拒答、首 Token/总延迟及可选复核字段。评测结果不会记录 API Key；已有 M5.2/M5.3 报告仍是当时 25 条用例的历史基线。
- M5.3 使用同一评测集完成修复回归：Route、文档/Chunk 命中、引用展示和拒答自动检查达到 100%；详细结果见 `docs/m5.3-query-quality-report.md`。AI 辅助开发等高风险职责边界由 grounded policy 控制，不完全依赖模型自由生成。
- 项目按面试展示型小项目控制范围：保留自动回归和重点失败样例抽查，不继续建设逐条人工评分、LLM-as-a-Judge 或完整评测平台；当前重点是补全个人与多项目知识，完成后再进入部署。
- M5.4 已接入轻量非敏感 Trace：JSON/SSE 响应返回 `X-Trace-ID`，服务端结构化日志记录 route、intent、公开 Chunk IDs、generation strategy、拒答原因和延迟，不记录问题、回答、Prompt 或密钥。详见 `docs/m5.4-observability-report.md`。
- 后续 Agentic 能力会优先以轻量 Router / Tool / Policy 编排实现；只有当工作流复杂度证明必要时，再评估 LangGraph 等成熟 Agent 框架。
- 生产部署在公开知识内容补全并通过回归后再开始。
- Docker Compose 已提供 PostgreSQL + pgvector 配置，但本机 Docker Desktop 需要手动启动后才能运行。
