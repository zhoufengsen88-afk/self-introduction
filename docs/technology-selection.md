# Agentic RAG 个人经历助手技术选型说明

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 产品名称 | Agentic RAG 个人经历助手（暂定） |
| 文档版本 | v1.4 |
| 文档状态 | Agentic RAG 作品集项目技术选型草案 |
| 关联文档 | [PRD](./PRD.md)、[系统架构设计](./architecture.md) |
| 目标读者 | 开发者、架构评审者、测试者、运维人员 |
| 更新时间 | 2026-07-17 |

### 1.1 版本记录

| 版本 | 日期 | 变更内容 |
| --- | --- | --- |
| v0.1 | 2026-07-15 | 确定 MVP 前端、后端、数据、RAG、测试、可观测与部署技术基线 |
| v0.2 | 2026-07-15 | 按个人作品集定位简化会话持久化、反馈、监控和恢复要求 |
| v0.3 | 2026-07-17 | 记录 M1 首轮 Embedding 实测结果，并确定 pgvector Spike 的 384 维临时基线 |
| v0.4 | 2026-07-17 | 记录 PostgreSQL 18 + pgvector Spike 验证结果，确认精确余弦检索和 SQL 可见性过滤方案 |
| v0.5 | 2026-07-17 | 记录 FastAPI SSE Spike 验证结果，确认 POST 流式事件语义和客户端取消处理 |
| v0.6 | 2026-07-18 | 记录 M5.4 使用标准 logging 落地非敏感 RAG Trace 与 X-Trace-ID |
| v0.6 | 2026-07-17 | 记录 LLM Fake Provider 契约基线，真实模型选择待 API Key 与候选确认 |
| v0.7 | 2026-07-17 | 记录 M3 工程基线：内存 BM25 + 轻量意图重排 + 确定性证据组织器 |
| v0.8 | 2026-07-17 | 记录 M3.2 pgvector 工程基线：本地 Hash Embedding + 数据库入库/检索 |
| v0.9 | 2026-07-17 | 记录 M3.3 真实 Embedding Provider：multilingual-e5-small + pgvector |
| v1.0 | 2026-07-17 | 记录 M3.4 语义压力评测结果，确认 E5 在弱关键词/英文问题上优于基线 |
| v1.1 | 2026-07-17 | 记录 M3.5 查询理解优化：确定性意图识别、查询扩展和轻量重排 |
| v1.2 | 2026-07-17 | 记录 M4 Web MVP：浏览器流式对话、引用卡片和 sessionStorage 短期历史 |
| v1.3 | 2026-07-17 | 修正项目方向：个人经历是场景，核心技术目标是 Agentic RAG 工程落地 |
| v1.4 | 2026-07-17 | 记录 M4.2：OpenAI-compatible LLM Provider 与可插拔 Answer Generator |

### 1.2 文档目的

本文档在 PRD 和架构设计的约束下回答：

- 每个系统模块使用什么技术实现。
- 为什么选择该方案，而不是其他常见方案。
- 当前选择承担哪些成本和限制。
- 哪些选择立即确定，哪些必须通过评测或部署约束后确定。
- 出现什么条件时应重新评估。

本文不追求堆叠框架。MVP 的优先级是构建一个可理解、可测试、可上线、可持续演进的 Agentic RAG 应用。

本项目不是商业 SaaS。选型目标是以较低成本交付一个可信、可公开访问并能在面试中讲清楚的 Agent 应用开发工程项目；个人经历问答是展示这个工程能力的应用场景。

---

## 2. 选型结论

### 2.1 技术栈总览

| 领域 | MVP 选择 | 状态 |
| --- | --- | --- |
| 前端语言 | TypeScript | 已选择 |
| 前端框架 | Next.js App Router + React | 已选择 |
| 前端样式 | Tailwind CSS | 已选择 |
| 前端状态 | React 本地状态 + `sessionStorage` 短期会话 | 已选择 |
| 前端流式消费 | `fetch` + `ReadableStream` 解析 `text/event-stream` | M1 已验证 |
| 前端包管理 | pnpm + lockfile | 已选择 |
| 前端测试 | Vitest + React Testing Library + Playwright | 已选择 |
| 后端语言 | Python 3.13 | 已选择 |
| 后端框架 | FastAPI + Pydantic v2 | M1 SSE 已验证 |
| ASGI Server | Uvicorn | 已选择 |
| Python 项目管理 | uv + `pyproject.toml` + `uv.lock` | 已选择 |
| ORM / SQL | SQLAlchemy 2.x | 已选择 |
| 数据迁移 | Alembic | 已选择 |
| PostgreSQL 驱动 | psycopg 3 | 已选择 |
| 数据库 | PostgreSQL 18 | 已选择 |
| 向量扩展 | pgvector，MVP 使用精确余弦检索 | 已选择 |
| Markdown 解析 | markdown-it-py + python-frontmatter | 已选择 |
| Agentic RAG 编排 | 自有应用服务 Pipeline + 轻量 Router / Tool / Policy 分层 | 已选择 |
| M3 检索基线 | 内存 BM25 + 轻量意图重排 | 已实现 |
| M3 回答基线 | 确定性证据组织器，不调用真实 LLM | 已实现 |
| M3.2 DB 检索基线 | PostgreSQL + pgvector 精确检索 + 轻量意图重排 | 已实现 |
| M3.2 工程 Embedding | `local-hashing-embedding`，384 维，revision `m3.2-v1` | 已实现 |
| M3.3 真实 Embedding | `intfloat/multilingual-e5-small`，384 维，revision 固定 | 已实现 |
| M3.4 语义评测 | E5 pgvector 在语义压力集上 Chunk Hit 84.62%，优于 Hashing 53.85% | 已验证 |
| M3.5 查询理解 | 确定性意图识别 + 查询扩展 + 文档/标题/内容加权 | 已实现 |
| M4 Web MVP | 推荐问题 + 流式聊天 + 引用卡片 + 浏览器短期历史 | 已实现 |
| M4.2 真实 LLM 生成 | OpenAI-compatible Provider + 可插拔 Answer Generator，将检索 Chunk 交给 LLM 生成自然回答 | 已实现，待质量评测 |
| Agent 框架 | 不先引入 LangChain / LangGraph；先实现自有轻量 Agentic 编排 | 已选择 |
| LLM 接入 | 内部 Provider 接口 + 官方/兼容 SDK 适配器 | 已选择 |
| LLM 测试基线 | Fake Provider，固定流式事件、引用和拒答契约 | M1 已验证 |
| 生产 LLM 模型 | 首个本地配置目标为 `deepseek-v4-flash`；最终生产模型仍通过质量、延迟、地区可用性、数据条款和预算决定 | 待评测 |
| Embedding 接入 | 内部 Provider 接口 | 已选择 |
| pgvector Spike Embedding | `intfloat/multilingual-e5-small`，384 维，归一化余弦检索 | M1 已验证临时基线 |
| 生产 Embedding 模型 | M3.5 当前推荐 `multilingual-e5-small`；知识规模扩大和部署地区确认后复评 | 临时选择 |
| 日志 | Python 标准 logging + JSON 结构化输出 | 已选择 |
| Trace / Metric | MVP 不接入平台；保留 Request ID，后续按需要使用 OpenTelemetry | 已选择 |
| 本地环境 | Docker Compose | 已选择 |
| 生产交付物 | 独立 Web / API 容器 + 托管 PostgreSQL | 已选择 |
| 生产云平台 | 根据目标访问地区、预算和流式支持决定 | 待确认 |
| 后端测试 | pytest + pytest-asyncio + HTTPX | 已选择 |
| Python 代码质量 | Ruff + mypy | 已选择 |
| API 契约 | OpenAPI + Pydantic Schema | 已选择 |
| CI | GitHub Actions（代码进入 GitHub 后） | 计划采用 |

### 2.2 运行单元

```text
Web Container
  Next.js + React + TypeScript

API Container
  Python + FastAPI + SQLAlchemy + Provider Adapters

Ingestion / Evaluation CLI
  与 API 共用后端领域层和基础设施层

Database
  PostgreSQL + pgvector
```

MVP 不增加 Redis、消息队列、独立向量数据库、独立 Worker、API Gateway、Kubernetes 和 Agent 平台。

---

## 3. 项目约束

技术选择必须满足以下已知约束：

- 项目主要由单人开发和维护。
- 首版只有一个候选人和一个知识库。
- 知识规模预计为几百到几千个 Chunk，而不是百万级。
- 不包含商业化、用户账户、付费、运营和企业 SLA。
- 中文问答和中文项目资料是首要场景。
- 面试官通过公开网页访问，不能要求复杂登录流程。
- 必须支持流式输出、引用、拒答和连续追问。
- 必须体现 Agent 应用开发工程能力，而不只是普通个人主页或静态问答 Demo。
- 必须能够在本地复现，并最终以 HTTPS 部署到公网。
- 模型、Embedding 和部署平台尚未最终确定。
- 项目既是产品，也是工程学习和面试展示材料。

因此，选型倾向于成熟、透明、可调试的通用技术，而不是把关键业务隐藏在高层 AI 框架中。

---

## 4. 评价维度

所有候选方案按以下维度评估：

| 维度 | 说明 | 权重倾向 |
| --- | --- | --- |
| 满足 PRD | 是否支持流式回答、引用、权限、评测和部署 | 最高 |
| 可解释性 | 能否观察和解释数据流及错误位置 | 很高 |
| 开发效率 | 单人能否较快实现 MVP | 很高 |
| 可维护性 | 代码边界、类型、测试和文档是否清晰 | 很高 |
| 部署复杂度 | 需要维护多少运行组件 | 很高 |
| 生态成熟度 | 文档、社区、驱动和工具是否稳定 | 高 |
| 可替换性 | 是否容易更换模型或部署平台 | 高 |
| 成本 | 开发成本、云资源和模型费用 | 高 |
| 性能 | 是否满足当前规模，而不是理论峰值 | 中 |
| 扩展性 | 是否保留未来 Agent 和检索优化空间 | 中 |

选型原则是“满足当前需求并保留演进边界”，而不是为假设中的大规模场景提前建设。

---

## 5. 前端选型

### 5.1 选择：Next.js App Router + React + TypeScript

选择理由：

- 同时适合候选人公开主页和交互式聊天页面。
- 支持服务端渲染、静态内容和客户端交互的组合。
- TypeScript 能为 API 事件、引用和错误模型提供静态约束。
- App Router 提供布局、加载、错误边界和服务端组件等能力。
- 可以作为 Node.js Server 或 Docker 容器部署，符合架构中的独立 Web 运行单元。
- 官方部署模式支持流式内容；需要确保反向代理不缓冲响应。

Next.js 当前官方文档推荐 TypeScript、ESLint、Tailwind CSS 和 App Router 作为新项目默认组合；其 Node.js Server 和 Docker 部署模式支持完整框架能力。[Next.js 安装文档](https://nextjs.org/docs/app/getting-started/installation) [Next.js 部署文档](https://nextjs.org/docs/app/getting-started/deploying)

### 5.2 备选方案

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| Vite + React | 简单、构建快、纯前端边界清晰 | 主页 SEO、服务端渲染和一体化部署能力需额外设计 | 可行，但不作为首选 |
| Vue / Nuxt | 开发体验好，功能完整 | 当前项目需要同时学习另一套生态 | 不选 |
| Streamlit / Gradio | AI Demo 开发极快 | 产品定制、工程边界和公开网站体验受限 | 仅适合早期实验，不作为正式前端 |
| 纯静态 HTML | 部署简单 | 聊天状态、流式交互和组件维护能力不足 | 不选 |

### 5.3 Node.js 版本

选择 Node.js 24 LTS，而不是 Current 或已结束支持的版本。

理由：

- 生产环境使用 LTS 分支，避免追随短周期 Current 版本。
- Node.js 官方建议生产应用使用 Active LTS 或 Maintenance LTS。
- 截至本文更新时间，Node.js 24 处于 LTS，Node.js 26 仍是 Current。[Node.js 发布状态](https://nodejs.org/en/about/previous-releases)

版本策略：

- 通过 `.nvmrc` 或等效文件固定主版本。
- `package.json` 声明 `engines.node`。
- 容器镜像固定到 Node.js 24 的具体补丁或摘要。
- 每季度检查一次 LTS 状态和依赖兼容性。

### 5.4 包管理：pnpm

选择原因：

- 安装速度和磁盘利用率良好。
- lockfile 适合复现开发与 CI 环境。
- 对 monorepo/workspace 具有成熟支持，即使 MVP 暂不需要复杂 workspace。

约束：

- 提交 `pnpm-lock.yaml`。
- CI 使用冻结 lockfile 安装。
- 不在同一项目混用 npm、yarn 和 pnpm lockfile。
- 通过 Corepack 或固定版本确保本地与 CI 一致。

### 5.5 样式：Tailwind CSS

选择原因：

- 适合快速实现首页、对话气泡、引用卡片和响应式布局。
- 与 Next.js 新项目默认工具链兼容。
- MVP 可以少量编写业务组件，不需要先建设完整设计系统。

暂不选择大型组件库。需要 Dialog、Tooltip、Accordion 等可访问性组件时，可按需引入基于 Radix primitives 的薄组件，而不是一次性引入大量未使用组件。

### 5.6 前端状态管理

选择：

- 页面局部状态使用 React State / Reducer。
- 会话流状态使用一个明确的 `useChatStream` Hook。
- 只有跨多个页面共享且生命周期稳定的数据才进入 Context。
- 服务端公开资料优先通过 Server Component 或普通 `fetch` 获取。

暂不引入 Redux、MobX 或 Zustand。

重新评估条件：

- 出现复杂的跨页面可编辑状态。
- 会话草稿、多个并行对话和乐观更新难以维护。
- 状态逻辑无法通过 reducer 和模块化 Hook 清晰表达。

### 5.7 流式响应：fetch + ReadableStream

选择后端返回 `Content-Type: text/event-stream`，前端通过 `fetch` 读取响应流并解析 SSE 格式事件。

不直接使用浏览器 `EventSource` 的原因：

- 问答接口使用 `POST`，需要提交 JSON 请求体。
- 原生 `EventSource` 面向 `GET`，请求头和请求体控制有限。
- `fetch` 可以同时处理 POST、取消信号、HTTP 错误和流式响应。

不选择 WebSocket 的原因：

- MVP 的主要数据方向是服务器向客户端持续输出。
- WebSocket 会增加连接状态、心跳、代理和重连协议设计。
- 停止生成可以通过取消 `fetch` 和服务端取消传播实现。

重新评估条件：需要语音、实时协作或高频双向事件。

### 5.8 前端测试

| 工具 | 用途 |
| --- | --- |
| Vitest | 工具函数、Reducer、SSE 解析器单元测试 |
| React Testing Library | 组件交互和无障碍行为测试 |
| Playwright | 从提问到流式回答、引用展示和错误重试的端到端测试 |

端到端测试默认连接 Fake Provider 环境，少量测试环境冒烟用例再连接真实模型。

### 5.9 M4 Web MVP 实现记录

M4 已按前端选型完成本地浏览器对话界面：

- 使用 `fetch` + `ReadableStream` 消费后端 `POST /api/chat/stream`。
- 使用 React 本地状态维护输入框、全局状态、消息列表和当前流式回答。
- 使用 `AbortController` 实现停止生成。
- 使用 `sessionStorage` 保存当前浏览器会话内的短期对话历史。
- 每次请求发送最近历史给 API，支持基础多轮追问。
- 引用通过 `done` 事件一次性返回，并渲染为引用卡片。
- 拒答、错误和取消都在前端有明确状态展示。

M4 暂不引入：

- Redux / Zustand 等全局状态库。
- WebSocket。
- 服务端会话持久化。
- 登录态、用户系统和反馈系统。

这些能力等 M4.1 产品化测试或 M5 上线阶段再按需要评估。

---

## 6. 后端语言与框架

### 6.1 语言：Python 3.13

选择理由：

- RAG、Embedding、文档处理和模型 SDK 生态集中在 Python。
- 现代类型标注可以表达领域接口和 Provider Protocol。
- 3.13 已具备稳定生态支持，同时避免在 MVP 初期采用更新的解释器主版本造成依赖兼容风险。

版本策略：

- `pyproject.toml` 声明 `requires-python = ">=3.13,<3.14"`。
- `.python-version` 固定开发版本。
- 容器镜像固定到具体 Python 3.13 补丁版本和 Debian slim 基础镜像。
- 升级主版本必须执行完整测试、入库和离线评测。

### 6.2 Web 框架：FastAPI

选择理由：

- 与 Python 类型标注和 Pydantic 数据校验自然结合。
- 自动生成 OpenAPI 和 JSON Schema，适合维护前后端契约。
- 支持异步请求、Streaming Response、依赖注入和标准 ASGI 生命周期。
- 能以较少框架代码实现问答和健康检查 API。
- 与 HTTPX、pytest 和 OpenTelemetry 生态兼容。

FastAPI 官方列出的能力包括 OpenAPI、JSON Schema、Pydantic 校验、依赖注入和 Streaming Response，和本项目的接口及流式需求直接匹配。[FastAPI 功能说明](https://fastapi.tiangolo.com/features/)

### 6.3 备选方案

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| Django + DRF | 管理后台、ORM 和权限体系完整 | MVP 不需要复杂后台，框架面更大 | 不选 |
| Flask | 简单、自由 | 类型校验、OpenAPI 和异步流式需更多组装 | 不选 |
| Node.js 后端 | 前后端统一语言 | Python AI/文档生态更适合本项目学习目标 | 不选 |
| Go | 部署和并发性能好 | 模型与文档生态、开发速度不占优势 | 不选 |

### 6.4 数据校验与配置：Pydantic v2 + pydantic-settings

用途：

- 定义 API 请求、响应和流式事件 Schema。
- 定义应用内部不可变数据对象。
- 从环境变量加载有类型的配置。
- 在启动时校验必需配置，避免请求运行到中途才发现缺失密钥。

规则：

- API Schema、领域对象和 ORM Model 不直接复用为同一个类。
- 生产密钥使用 `SecretStr` 或等效类型，避免默认日志输出。
- 未识别的生产配置应按策略报错，防止拼写错误静默失效。
- 配置按 `development`、`test`、`production` 区分，但使用同一份定义。

### 6.5 ASGI Server：Uvicorn

选择原因：

- FastAPI 官方运行路径直接支持。
- 满足异步 HTTP 和流式响应。
- 容器内采用单个应用进程起步，由托管平台负责重启和未来的实例扩展。

MVP 不在容器内叠加 Gunicorn。需要单机多核扩展时，先以负载测试和部署平台能力为依据，再选择 Uvicorn workers 或多容器副本。

---

## 7. Python 项目与代码质量工具

### 7.1 依赖管理：uv

选择原因：

- 使用标准 `pyproject.toml` 管理项目元数据和依赖。
- 使用 `uv.lock` 固定跨环境解析结果。
- 可以统一创建环境、锁定、同步和运行命令。
- CI 可通过 `--locked` 或 `--frozen` 防止依赖被静默更新。

uv 官方文档说明 `uv.lock` 保存精确解析版本并应提交到版本控制，从而让不同环境使用一致依赖。[uv 项目文档](https://docs.astral.sh/uv/guides/projects/)

规则：

- 提交 `pyproject.toml` 和 `uv.lock`。
- 运行环境使用 `uv sync --locked` 或等价冻结方式。
- 依赖升级通过独立提交完成，并运行完整测试。
- 不手工编辑 `uv.lock`。
- 生产镜像只安装运行依赖，不安装测试与开发工具。

### 7.2 格式化与 Lint：Ruff

选择 Ruff 统一完成格式化、Import 排序和大部分静态规则，避免同时维护 Black、isort 和多套 Flake8 插件。

规则：

- CI 执行 `ruff format --check`。
- CI 执行 `ruff check`。
- 规则从较小集合开始，根据实际缺陷增加，不一次性启用大量噪声规则。

### 7.3 静态类型：mypy

选择原因：

- Provider、Repository 和 Pipeline 接口是本项目的重要边界。
- 类型检查可以尽早发现异步返回类型、可空值和事件联合类型错误。

范围：

- `application`、`domain` 和 Provider 接口使用严格或接近严格检查。
- 基础设施层对缺少类型信息的第三方 SDK允许局部隔离，不使用全局忽略。

### 7.4 测试：pytest

选择 pytest 作为后端统一测试入口，配合：

- `pytest-asyncio`：异步服务和 Repository 测试。
- HTTPX：ASGI API 测试客户端。
- Testcontainers 或 Docker Compose 测试数据库：验证真实 PostgreSQL/pgvector 行为。
- 参数化测试：批量覆盖 Evidence Policy、权限和 Chunk 边界。

pytest 支持函数和 Fixture 参数化，适合把评测样例和安全样例转成回归测试。[pytest 参数化文档](https://docs.pytest.org/en/stable/how-to/parametrize.html)

---

## 8. 数据访问与迁移

### 8.1 ORM / SQL：SQLAlchemy 2.x

选择方式：

- 常规实体写入和关系使用 SQLAlchemy ORM。
- 向量检索、批量 Upsert 和性能敏感查询允许使用 SQLAlchemy Core 或显式 SQL。
- 不强制所有查询都包装成通用 Repository CRUD。

选择原因：

- ORM、Core、事务和连接池可以在一套工具中使用。
- SQLAlchemy 2.x 提供 AsyncIO 支持，适合 FastAPI 请求路径。
- 允许在抽象便利性与明确 SQL 之间选择。

SQLAlchemy 2.x 官方文档同时覆盖 ORM、Core、事务、连接池和 AsyncIO。[SQLAlchemy 2.0 文档](https://docs.sqlalchemy.org/en/20/)

### 8.2 PostgreSQL Driver：psycopg 3

选择 psycopg 3 的异步支持连接 PostgreSQL。

原则：

- 请求级事务边界由应用服务显式控制。
- 会话关闭由依赖或上下文管理器保证。
- 设置连接池、连接超时和 SQL 语句超时。
- 流式生成期间不长期占用数据库事务；先读取检索数据并结束事务，再调用模型。

### 8.3 数据迁移：Alembic

选择原因：

- 与 SQLAlchemy Metadata 直接集成。
- 迁移脚本可以进入版本控制并随部署执行。
- 支持检查模型是否存在尚未生成的 Schema 变化。

规则：

- `autogenerate` 只生成候选迁移，必须人工审查。
- 每个迁移应提供可理解的 upgrade；高风险 downgrade 可明确限制。
- 生产迁移执行前备份并评估锁表风险。
- CI 运行 `alembic check` 或等效 Schema 一致性检查。
- pgvector 扩展启用和向量维度变更使用显式迁移。

Alembic 官方明确指出自动生成并不完美，生成的迁移需要人工检查；其 `alembic check` 可在 CI 中检测模型变化是否缺少迁移。[Alembic 自动迁移文档](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)

---

## 9. 数据库与向量存储

### 9.1 选择：PostgreSQL 18 + pgvector

选择原因：

- 文档、版本、Chunk、导入和评测元数据属于关系数据。
- 向量与业务元数据保存在同一事务系统中，减少数据同步问题。
- 可以在向量检索前通过 SQL 强制应用 `visibility`、`status`、`project_id` 等过滤。
- 支持 JSONB 保存尚未稳定的扩展元数据。
- 后续可使用 PostgreSQL 全文检索增加混合检索，无须立即新增搜索集群。
- 当前知识规模不需要单独的向量数据库。

### 9.2 为什么选择 PostgreSQL 18

- 使用当前受支持的稳定主版本建立新项目。
- 本地和生产环境统一主版本，避免 SQL、扩展和迁移差异。
- 部署前仍需确认目标托管平台是否提供 PostgreSQL 18 和兼容 pgvector 扩展。

若目标平台暂不支持 PostgreSQL 18，则允许退回平台支持的最新稳定主版本，但本地、CI 和生产必须一致，并在 ADR 中记录。

### 9.3 向量字段

使用 pgvector `vector(n)`，其中 `n` 在选定 Embedding 模型后确定。

约束：

- 一个有效索引版本只使用一个 Embedding 模型和一个维度。
- 数据库保存 `embedding_model`、`embedding_dimensions` 和索引版本。
- 更换不兼容模型时建立新索引版本并完整重算，不在同一向量空间混用。
- 使用余弦距离作为首个候选度量，但最终由 Embedding 模型说明和检索评测确认。

### 9.4 MVP 使用精确向量检索

选择：不创建 HNSW 或 IVFFlat 近似索引，先执行精确 Top-K 检索。

原因：

- 初始 Chunk 数量小。
- 精确检索具有稳定召回，适合建立基线。
- 更容易判断召回问题来自内容、切分、Embedding 还是过滤。
- 避免近似索引参数成为早期干扰变量。

pgvector 默认执行精确近邻搜索；HNSW 和 IVFFlat 会以一定召回变化换取查询速度。[pgvector 官方文档](https://github.com/pgvector/pgvector)

重新评估条件：

- 实际数据量下 P95 检索延迟超过既定预算。
- 向量查询成为数据库主要 CPU 消耗。
- 评测确认加入近似索引后召回损失可接受。

### 9.5 为什么暂不选择专用向量数据库

| 方案 | 优点 | 当前问题 | 结论 |
| --- | --- | --- | --- |
| pgvector | 组件少、SQL 过滤、事务一致 | 超大规模向量能力不是其唯一目标 | 选择 |
| Qdrant | 向量能力和过滤完整 | 新增服务、备份和同步 | 暂不选 |
| Milvus | 面向大规模向量检索 | 运维和资源复杂度过高 | 不选 |
| Pinecone 等托管服务 | 运维少、扩缩容方便 | 外部成本、数据边界、额外依赖 | 暂不选 |
| 本地 FAISS | 原型简单、性能好 | 持久化、元数据、并发和更新需自行实现 | 仅适合实验 |

### 9.6 未来混合检索

如果向量检索对技术名词、缩写、项目名或精确数字召回不足，优先评估：

```text
pgvector 语义结果
    +
PostgreSQL Full-Text Search 关键词结果
    ↓
Reciprocal Rank Fusion
    ↓
可选 Reranker
```

这条演进路径仍可留在 PostgreSQL 内，只有评测和规模证明必要时才引入独立搜索服务。

---

## 10. 文档解析与知识入库

### 10.1 MVP 输入格式：Markdown + YAML Front Matter

选择理由：

- 适合人工编写和审查。
- 标题层级天然表达项目内容结构。
- Git Diff 清晰，方便版本追踪。
- 元数据和正文可放在同一个文件中。
- 避免 PDF/DOCX 排版解析问题干扰第一版 RAG 质量。

### 10.2 Markdown Parser：markdown-it-py

选择 token/AST 级解析，不使用正则表达式直接拆 Markdown。

用途：

- 识别标题层级。
- 保留段落、列表和代码块边界。
- 生成稳定的标题路径。
- 避免在代码块中的 `#` 被错误识别为标题。

### 10.3 Front Matter：python-frontmatter

用于读取和校验：

- `document_id`
- `title`
- `category`
- `project_id`
- `visibility`
- `status`
- `updated_at`

读取结果必须转换为内部 Pydantic Schema，再进入入库流程；不能直接信任任意 YAML 字段。

### 10.4 Chunk 策略

MVP 采用“结构优先、长度兜底”：

1. 根据 Markdown 标题树拆分 Section。
2. 短 Section 保持完整。
3. 超长 Section 按段落、列表和代码块边界继续切分。
4. 添加有限重叠，仅在语义跨块确有需要时使用。
5. 保存标题路径和前后块关系。

不在选型文档硬编码 Chunk 字符数和重叠值。初始值在实现时配置，并通过检索评测调整。

### 10.5 Token 估算

首版同时保存字符数和可获得的 Token 估算：

- 模型供应商提供稳定 tokenizer 时使用对应 tokenizer。
- 没有统一 tokenizer 时使用保守估算控制上下文，不假设不同模型 Token 完全一致。
- 最终模型请求的真实 Token 用量以供应商返回 usage 为准。

### 10.6 PDF / DOCX 后续策略

不在 MVP 主链路引入通用文档解析平台。

后续增加时的顺序：

1. 明确实际需要导入的文件类型和复杂度。
2. 建立包含标题、列表、表格和分页的解析测试集。
3. 比较轻量解析库与版面理解工具。
4. 将解析结果统一转换为内部 `ParsedDocument`，后续 Chunk 流程不感知来源格式。

---

## 11. Agentic RAG 编排与 Agent 框架

### 11.1 选择：自有轻量 Agentic RAG Pipeline

MVP 问答流程由 Python 应用服务中的轻量 Agentic RAG Pipeline 编排：

```text
validate browser history
→ route intent / task type
→ select safe internal tools
→ resolve or rewrite query
→ embed query
→ retrieve
→ evaluate evidence
→ build context
→ call answer generator
→ validate citations
→ persist result
```

选择原因：

- 每一步都可以单元测试和独立记录耗时。
- 数据结构、权限过滤和失败语义由项目自己控制。
- 避免学习框架概念替代学习 RAG 本身。
- 当前需要的是受控 Router / Tool / Policy 编排，而不是高自治开放式 Agent。
- 后续可以在不改 Retrieval、Evidence 和 Provider 接口的前提下升级为更成熟的 Agent 工作流。

### 11.2 为什么 MVP 不使用 LangChain / LangGraph

不是因为这些框架不能实现，也不是因为项目不做 Agent，而是当前阶段更需要展示底层 Agentic RAG 工程能力。先自研轻量编排可以让查询路由、检索、上下文、生成、引用和拒答的边界更清楚。

当前不引入可以避免：

- 隐式 Prompt 和数据转换。
- 框架版本变化扩大调试范围。
- 简单流程被包装成难以解释的状态图。
- 测试依赖框架内部事件格式。

当前选择是：

```text
先实现可测试的轻量 Agentic RAG
→ 当路由、工具调用和状态管理复杂度上升
→ 再评估 LangGraph 或等效工作流框架
```

### 11.3 Agent 框架重新评估条件

满足以下两项以上时重新评估 LangGraph 或等效工作流框架：

- 根据问题动态选择多个工具。
- 一个任务包含分支、循环或多次检索。
- 工作流需要持久化暂停和恢复。
- 高风险操作需要人工批准。
- 需要长时间运行任务和失败续跑。
- Agent 状态已无法通过清晰的应用服务表达。

即使未来引入 Agent 框架，Retrieval、Evidence、Visibility 和 Provider 仍保持独立接口，权限规则不能交给模型自行决定。

### 11.4 M4.2 真实 LLM Answer Generator

M4.2 已把当前“检索 + 确定性证据组织器”升级为可插拔 Answer Generator。默认仍使用 `deterministic` 生成器保障本地开发和测试稳定；设置 `ANSWER_GENERATOR=llm` 后，会调用 OpenAI-compatible LLM Provider：

```text
retrieved chunks
→ context builder
→ prompt / instruction
→ LLM streaming
→ citation validation
→ final answer event
```

设计原则：

- 前端仍使用现有 `/api/chat/stream`，避免因为模型更换重写前端。
- Answer Generator 已提供 `deterministic` 和 `llm` 两种实现，便于评测对比。
- 首个真实模型配置目标是通过 OpenAI-compatible 接口调用 `deepseek-v4-flash`。
- Prompt 必须包含证据边界、职责边界、引用规则和拒答规则。
- LLM 输出不得绕过 Citation Validator。
- 没有足够证据时，Evidence Policy 先于 LLM 生成触发拒答。

### 11.5 结构化输出

模型最终回答建议逻辑上包含：

```json
{
  "answer": "...",
  "citation_ids": ["chunk_xxx"],
  "answerability": "answered"
}
```

由于流式 JSON 容易出现未完成状态，MVP 可以采用：

- 正文以文本增量流式返回。
- 引用 ID 通过稳定标记或最终结构化事件返回。
- 服务端完成后统一执行引用合法性校验。

不要让模型直接生成对外文档路径、数据库 ID 之外的任意 URL。

### 11.6 M3.5 查询理解层

M3.5 在自有 Pipeline 中加入轻量查询理解层，而不是引入完整 Agent 框架或让 LLM 动态改写所有问题。

当前实现包括：

- 基于问题和最近历史判断意图。
- 为权限难点、MCP / CLI、检索降级等高价值主题补充查询扩展词。
- 根据文档 ID、标题路径和内容关键词做轻量重排加权。
- 用离线评测验证是否提升 Chunk Hit 和 Required Recall。

选择确定性规则的原因：

- 当前知识库规模小，失败模式集中，规则足以覆盖已知问题。
- 每个意图可以直接解释给面试官，符合工程化学习目标。
- 规则变更可以通过 `mvp-v1` 和语义压力集做回归验证。
- 不需要额外模型调用成本、延迟和不可控输出。

M3.5 后，同一语义压力集上 E5 pgvector 达到：

```text
document_hit_rate: 100%
citation_hit_rate: 100%
mean_required_recall: 100%
```

重新评估 LLM query rewrite 或 cross-encoder rerank 的条件：

- 语义压力集扩充后，规则意图数量明显膨胀。
- 新问题分布难以用少量稳定规则覆盖。
- 正确文档已经召回，但 Top-K 内 Chunk 排序经常错误。
- 需要跨多个项目进行复杂比较和多跳检索。

---

## 12. LLM 与 Embedding 选型

### 12.1 先确定接口，不先绑定供应商

代码层选择内部协议：

```text
LLMProvider
EmbeddingProvider
```

至少提供：

- `FakeLLMProvider`
- `FakeEmbeddingProvider`
- 一个真实模型适配器
- 一个真实 Embedding 适配器

真实适配器可以使用供应商官方 SDK，或在供应商明确支持时使用兼容协议。供应商特有字段只能出现在适配器内部。

### 12.2 为什么生产模型暂不直接指定

模型选择受以下尚未确认因素影响：

- 网站和后端部署地区。
- API 在目标网络中的可访问性和延迟。
- 中文项目问答和指令遵循质量。
- 流式输出、结构化输出和 usage 数据支持。
- 数据保留、训练使用和隐私条款。
- 单次成本、免费额度和速率限制。
- Embedding 维度与 PostgreSQL 存储兼容性。

在这些条件未知时写死供应商，会把部署和隐私风险推迟到开发后期。

### 12.3 LLM 候选评测标准

候选模型使用同一知识库、Prompt 和评测集比较：

| 指标 | 关注点 |
| --- | --- |
| 忠实度 | 是否只使用提供证据陈述个人事实 |
| 拒答准确率 | 无证据时是否拒绝编造 |
| 引用遵循率 | 是否只输出允许的引用 ID |
| 职责边界 | 是否区分个人与团队贡献 |
| 中文表达 | 是否自然、专业、不过度扩写 |
| 首 Token 延迟 | 公开聊天的等待体验 |
| 总延迟 | 完整回答耗时 |
| 成本 | 每 100 次标准问答的估算费用 |
| 稳定性 | 超时、限流和错误率 |
| 数据条款 | 是否满足公开产品的数据要求 |

### 12.4 Embedding 候选评测标准

Embedding 不通过“感觉回答不错”选择，而直接评测检索：

- Top-1 / Top-3 / Top-5 命中率。
- 项目名、技术名、缩写和数字类问题表现。
- 中文和中英文混合查询表现。
- 维度、存储占用和单次成本。
- 批处理能力、限流和导入速度。
- 查询延迟和目标地区可用性。

### 12.5 初始适配策略

为了尽快搭建代码骨架，首个真实实现采用可配置的兼容客户端：

```text
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
EMBEDDING_BASE_URL
EMBEDDING_API_KEY
EMBEDDING_MODEL
EMBEDDING_DIMENSIONS
```

如果最终供应商的能力或错误模型与兼容协议差异明显，则新增供应商专用 Adapter，不在业务层增加条件分支。

### 12.6 超时、重试和用量

- HTTP Client 设置连接、读取和总请求超时。
- 只对明确的瞬时错误和限流进行有限重试。
- 已向前端发送正文后不自动重新生成整段回答。
- 保存供应商请求 ID、模型 ID、输入/输出 Token 和可估算成本。
- 日志不保存 API Key；完整 Prompt 默认不进入普通生产日志。

---

## 13. API 契约与客户端类型

### 13.1 OpenAPI

FastAPI 生成 OpenAPI 作为非流式接口的主要契约来源。

适用：

- Profile。
- Profile 和 Chat 请求。
- Feedback。
- Health 和错误响应。

### 13.2 流式事件 Schema

SSE 事件需要在后端使用 Pydantic Discriminated Union 定义，在前端建立对应 TypeScript 联合类型。

示例：

```typescript
type ChatEvent =
  | { type: "message.started"; data: MessageStarted }
  | { type: "answer.delta"; data: AnswerDelta }
  | { type: "citations.completed"; data: CitationsCompleted }
  | { type: "refusal.completed"; data: RefusalCompleted }
  | { type: "error"; data: StreamError }
  | { type: "message.done"; data: MessageDone };
```

MVP 可以手工维护这一小组事件类型，同时用契约测试保证前后端样例一致。非流式 Schema 可以后续评估从 OpenAPI 生成 TypeScript Client。

### 13.3 为什么不立即生成完整客户端

- API 数量少。
- 流式事件仍需要自定义消费逻辑。
- 过早引入代码生成会增加构建步骤和生成文件管理。

重新评估条件：API 数量增加、多人协作或前后端契约漂移频繁。

---

## 14. 可观测性

### 14.1 MVP：结构化 JSON 日志

选择 Python 标准 `logging` 作为日志 API，配置 JSON Formatter 输出到标准输出。

原因：

- 不把业务代码绑定到具体日志平台。
- 本地、容器和大多数托管平台都能采集标准输出。
- 可以先实现 `request_id`、阶段、耗时、模型和检索字段。

允许使用轻量 JSON 格式化库，但业务层不直接依赖厂商 Logger。

M5.4 已按该方案实现：FastAPI 为 JSON/SSE 问答返回 `X-Trace-ID`，RAG Service 通过可替换 `TraceSink` 输出 route、intent、Chunk IDs、生成策略、拒答、耗时和错误码。日志不记录问题、历史、回答、Prompt、密钥和 Base URL。当前不引入额外 Observability SaaS。

### 14.2 后续可选：OpenTelemetry

当结构化日志不足以定位问题或希望展示完整调用链时，选择 OpenTelemetry 作为 Trace 和 Metric 的标准接口：

- 为一次问答建立根 Trace。
- 为查询改写、Embedding、检索、Evidence、生成和持久化建立 Span。
- 导出到可替换的 Collector 或托管后端。
- 日志通过 `trace_id` / `span_id` 关联。

OpenTelemetry Python 当前 Trace 和 Metric 为稳定状态，Log SDK 仍处于开发状态。作品集 MVP 只保留可升级的 Span 边界和 Request ID，不要求上线前部署 Collector 或监控平台。[OpenTelemetry Python 状态](https://opentelemetry.io/docs/languages/python/)

### 14.3 为什么暂不选择特定 LLM Observability SaaS

LangSmith、Langfuse 等工具可以加速 Prompt、Trace 和评测观察，但会增加外部依赖和潜在数据流向。

MVP 顺序：

1. 先建立内部 request/trace 数据结构。
2. 使用结构化日志和数据库评测结果跑通闭环。
3. 再根据 UI、Prompt 管理、团队协作和数据条款决定是否接入专用平台。

接口和版本字段必须由本项目保存，不能只存在于第三方平台。

---

## 15. 缓存、限流与后台任务

### 15.1 MVP 不引入 Redis

原因：

- 短期会话由浏览器保存，服务端不需要共享会话缓存。
- 知识库规模小，检索延迟预计可接受。
- 单实例可以先用进程内令牌桶实现基础防滥用。
- 没有需要消息队列处理的高频后台任务。

进程内限流仅适合单实例 MVP。扩展到多个 API 实例时，限流状态需要迁移到边缘平台、Redis 或托管限流服务。

### 15.2 缓存顺序

只有监控证明需要时加入：

1. 公开 Profile 与推荐问题 HTTP 缓存。
2. 查询 Embedding 短期缓存。
3. 完全相同问题、知识版本和 Prompt 版本下的回答缓存。

回答缓存键必须至少包含：

```text
normalized_question
knowledge_base_version
retrieval_strategy_version
prompt_version
model_id
visibility_scope
```

否则知识更新或权限变化后可能返回过期、越权答案。

### 15.3 后台任务

入库和评测先由 CLI 同步执行。

重新评估 Worker / Queue 的条件：

- 在线上传文档。
- 单次入库时间超过交互请求容忍范围。
- 需要并行处理大量文件。
- 任务需要失败重试、进度查询和暂停恢复。

候选方案届时根据部署平台选择，不在 MVP 预装 Celery、RQ 或消息代理。

---

## 16. 本地开发与容器

### 16.1 Docker Compose

本地编排包含：

```text
web
api
postgres
```

可选开发 profile：

```text
otel-collector
observability-backend
```

原则：

- PostgreSQL 使用具备 pgvector 扩展的明确镜像或构建文件。
- 数据库使用命名 Volume。
- Web/API 源码可以在开发模式挂载，生产镜像不挂载源码。
- 健康检查用于控制依赖就绪，不只控制容器启动顺序。
- `.env.example` 只包含变量名称和安全示例，不包含真实密钥。

### 16.2 Dockerfile

Web 和 API 分别使用多阶段构建：

- Builder 阶段安装锁定依赖并构建。
- Runtime 阶段只包含运行所需文件。
- 使用非 root 用户运行。
- 固定基础镜像主版本和补丁策略。
- 配置健康检查或由平台调用应用健康端点。

FastAPI 官方将 Linux 容器列为常见部署方式，并建议从官方 Python 镜像构建应用镜像。[FastAPI Docker 部署](https://fastapi.tiangolo.com/deployment/docker/)

### 16.3 本地命令入口

统一提供少量稳定命令，例如：

```text
make dev
make test
make lint
make migrate
make ingest
make eval
```

`Makefile` 只做命令聚合，不包含难以测试的大量业务脚本。Windows 支持不是 MVP 硬要求；若后续需要跨平台，可迁移到 Taskfile 或 Python CLI。

---

## 17. 生产部署

### 17.1 已确定的交付形态

- Web：Node.js 24 LTS 容器。
- API：Python 3.13 容器。
- Database：托管 PostgreSQL，启用 pgvector。
- HTTPS / DNS：由云平台入口、负载均衡或反向代理负责。
- Secret：由平台密钥系统或环境变量安全注入。
- 日志：采集容器标准输出。

### 17.2 为什么生产平台暂不锁定

平台选择取决于：

- 面试官主要访问地区。
- 是否需要中国大陆备案和节点。
- 模型 API 在该地区的网络可达性。
- 是否支持 PostgreSQL + pgvector。
- 是否支持流式响应且代理默认不缓冲。
- 最低运行费用、休眠策略和冷启动。
- 自定义域名、HTTPS、日志和可接受的数据库恢复方式。

平台选错会直接影响公开可访问性，因此应在模型供应商和目标访问地区确认后完成部署 ADR。

### 17.3 生产平台最低能力

候选平台必须支持：

- 从 Dockerfile 构建或运行 OCI 镜像。
- 独立部署 Web 和 API。
- 长时间 HTTP 流式响应。
- 健康检查和异常自动重启。
- 运行时 Secret 注入。
- 私网或受控网络连接 PostgreSQL。
- 自定义域名和自动 HTTPS。
- 持久日志或日志导出。
- 能从版本化知识源重新构建向量数据；低成本自动备份属于加分项。

### 17.4 首版不使用 Kubernetes

原因：

- 服务数量少。
- 当前没有复杂扩缩容、服务发现和多团队隔离需求。
- 会显著增加部署、网络、Secret、监控和故障排查学习面。

重新评估条件：多个独立服务、显著流量、复杂发布策略或组织已有 Kubernetes 平台。

---

## 18. CI/CD

### 18.1 CI 选择

代码托管到 GitHub 后使用 GitHub Actions。若最终选择其他代码平台，则保留相同流水线阶段，替换执行器即可。

### 18.2 Pull Request 流水线

并行执行：

```text
frontend-lint-and-typecheck
frontend-unit-test
backend-lint-and-typecheck
backend-unit-test
database-integration-test
```

随后执行：

```text
build-web-image
build-api-image
contract-test
minimal-rag-evaluation
```

### 18.3 生产发布

```text
main branch / release tag
→ 完整 CI
→ 构建并标记不可变镜像
→ 推送镜像仓库
→ 部署测试环境
→ 数据库迁移检查
→ 冒烟测试
→ 人工批准
→ 生产迁移与部署
→ 健康检查
→ 流式问答冒烟测试
```

### 18.4 知识发布

知识文档和代码发布逻辑分离：

```text
knowledge change
→ metadata validation
→ ingestion dry-run
→ retrieval evaluation
→ human review
→ production ingestion
→ smoke questions
```

生产知识更新失败时保持上一有效版本可用。

---

## 19. 测试与评测工具

### 19.1 后端自动化测试

| 类型 | 工具 |
| --- | --- |
| 单元测试 | pytest |
| 异步测试 | pytest-asyncio |
| HTTP API | HTTPX ASGI Transport |
| 数据库集成 | 测试 PostgreSQL + pgvector |
| Mock / Fake | 自有 Fake Provider，必要时标准 unittest.mock |
| 覆盖率 | coverage.py / pytest-cov |

不使用 SQLite 代替 PostgreSQL 做 Repository 测试，因为向量类型、SQL、事务和约束行为不同。

### 19.2 前端自动化测试

| 类型 | 工具 |
| --- | --- |
| 单元测试 | Vitest |
| 组件测试 | React Testing Library |
| E2E | Playwright |
| 类型检查 | TypeScript Compiler |
| Lint | ESLint |

### 19.3 RAG 离线评测

首版不依赖单一 RAG 评测框架作为真值，使用版本化 JSONL/YAML 数据集和 Python Runner：

```text
evals/datasets/*.jsonl
→ evaluation runner
→ retrieval metrics
→ deterministic checks
→ optional model judge
→ versioned report
```

优先使用确定性指标：

- 期望 Chunk 是否进入 Top-K。
- 必须事实是否出现。
- 禁止事实是否出现。
- 是否正确拒答。
- 引用 ID 是否有效。
- 私密 Chunk 是否完全未进入候选集。

模型裁判只作为辅助信号；高风险安全和权限要求必须使用确定性测试。

### 19.4 为什么暂不引入 RAGAS 等框架

- MVP 需要先明确自己的评测数据结构和失败分类。
- 模型裁判可能引入额外成本、波动和不可解释性。
- 后续可以把框架指标作为插件加入，不应让核心评测数据绑定到框架格式。

重新评估条件：固定评测集稳定，需要批量计算更多语义指标并与社区基准对齐。

---

## 20. 安全工具与策略

### 20.1 依赖安全

- Python 和 Node 依赖均提交 lockfile。
- 自动化执行依赖漏洞扫描。
- 容器镜像执行基础漏洞扫描。
- 依赖升级通过独立 Pull Request 和测试完成。

### 20.2 Secret 检查

- `.gitignore` 排除 `.env`、私有密钥和本地数据库数据。
- CI 加入 Secret 扫描。
- 测试使用无权限假密钥。
- 泄露密钥按“立即吊销并轮换”处理，不能只从 Git 删除。

### 20.3 输入与输出

- Pydantic 验证长度和格式。
- 前端渲染模型输出时不使用未消毒的任意 HTML。
- Markdown 渲染采用白名单并禁用危险 HTML。
- 引用只展示服务端生成的安全字段。
- Prompt Injection 测试进入固定评测集。

### 20.4 限流

MVP 单实例使用应用层令牌桶，并同时配置云入口的基础限流能力。多实例后迁移到共享或边缘限流。

限流维度：

- IP 哈希。
- IP 哈希或浏览器生成的非身份客户端标识。
- 单客户端并发生成数。
- 全局预算保护。

---

## 21. 暂不引入的技术

| 技术 | 暂不引入原因 | 重新评估条件 |
| --- | --- | --- |
| LangGraph | 当前无状态图、暂停恢复和多工具需求 | Agent 工作流出现分支、循环、持久状态 |
| LangChain 高层 Chain | 会隐藏首版 RAG 关键数据流 | 明确组件能显著减少稳定重复代码 |
| Redis | 单实例、低流量、无队列需求 | 多实例限流、缓存或任务队列 |
| Celery / 消息队列 | 入库低频且可由 CLI 完成 | 在线上传、长任务和进度管理 |
| Elasticsearch / OpenSearch | PostgreSQL 足以完成首版检索 | 全文检索规模和能力超出 PostgreSQL |
| 专用向量数据库 | 当前数据量小，增加运维组件 | 向量规模、过滤或性能出现明确瓶颈 |
| WebSocket | 当前主要是单向流式输出 | 语音或高频双向实时通信 |
| Kubernetes | 服务少、流量小、运维复杂 | 组织平台或规模需求明确 |
| 微服务 | 单人开发且领域规模小 | 独立团队、独立扩缩容和发布需求 |
| 模型微调 | 优先解决内容、检索和 Prompt | 有高质量数据且 RAG/Prompt 已达瓶颈 |
| PDF/DOCX 通用解析 | 首版 Markdown 足够，版面解析复杂 | 真实知识源必须自动导入这些格式 |
| LLM Observability SaaS | 数据条款和必要性未确认 | 需要 Prompt UI、团队 Trace 与评测管理 |

---

## 22. 版本与升级策略

### 22.1 版本声明

- 运行时主版本显式固定：Node.js 24、Python 3.13、PostgreSQL 18。
- 应用依赖通过 lockfile 固定精确解析版本。
- Docker 基础镜像在生产构建中固定可追溯标签，成熟后考虑固定 Digest。
- 模型和 Prompt 使用应用级版本 ID，不只记录易变化的别名。

### 22.2 升级频率

| 类型 | 建议频率 |
| --- | --- |
| 紧急安全更新 | 评估后尽快升级 |
| Patch 依赖 | 每月批量检查 |
| Minor 依赖 | 每月或每季度，运行完整测试 |
| Major 框架 | 按收益评估，不自动升级 |
| Python / Node / PostgreSQL 主版本 | 独立升级计划和回归验证 |
| LLM / Embedding 模型 | 必须运行离线评测和成本对比 |

### 22.3 模型升级门禁

更换 LLM：

- 运行完整回答评测。
- 对比拒答、引用、职责边界、延迟和成本。
- 保留旧模型配置以便回退。

更换 Embedding：

- 生成全新索引版本。
- 完整重算知识向量。
- 运行检索评测。
- 验证后原子切换有效索引版本。
- 不在同一检索中混用两个不兼容向量空间。

---

## 23. 成本控制

### 23.1 主要成本来源

- LLM 输入和输出 Token。
- 查询与文档 Embedding。
- Web/API 容器运行时间。
- PostgreSQL 实例；备份按平台能力和成本选择。
- 日志、Trace 和 Metric 存储。
- 域名和网络流量。

### 23.2 初始控制措施

- 限制用户输入、历史消息、检索上下文和模型输出长度。
- 文档通过 `content_hash` 做增量 Embedding。
- 开发与 CI 默认使用 Fake Provider。
- 只在单独评测任务中批量调用真实模型。
- 记录每次请求 usage 和估算成本。
- 设置客户端和全局限流。
- 不在未测量前增加额外模型调用，如每次都进行 Query Rewrite 和 Rerank。

### 23.3 成本预算待办

生产模型确定前，使用标准评测集测量：

```text
平均输入 Token
平均输出 Token
P95 输入 / 输出 Token
每 100 次问答费用
每 1000 个 Chunk 的首次 Embedding 费用
一次完整重建费用
```

这些数据应进入部署决策，而不是只比较供应商标价。

---

## 24. 最终决策与取舍

### 24.1 已接受的取舍

| 选择 | 获得 | 代价 |
| --- | --- | --- |
| Next.js | 完整公开网站和交互能力 | Node.js 构建与运行环境 |
| FastAPI | Python AI 生态、类型化 API、流式能力 | 前后端使用两种语言 |
| 模块化单体 | 部署简单、调用透明 | 未来拆服务需要明确边界迁移 |
| PostgreSQL + pgvector | 组件少、事务与过滤统一 | 极大规模向量能力有限 |
| 精确向量检索 | 可解释、召回稳定 | 数据量大后查询成本上升 |
| 自有 RAG Pipeline | 学习深入、调试清楚 | 需要自己维护编排代码 |
| Provider Adapter | 可替换、易于 Fake 测试 | 需要维护内部统一接口 |
| CLI 入库 | 安全、简单、可重复 | 暂无可视化后台和在线进度 |
| SSE over fetch | 适合 POST 流式回答 | 需要自定义事件解析和重连策略 |
| 先不选生产模型 | 避免地区和评测未经确认就锁定 | 开发开始前仍需完成一次候选评测 |

### 24.2 技术选型完成标准

在以下事项完成后，v0.1 可从“草案”更新为“已接受”：

- 确认首版语言范围。
- 确认目标访问地区和生产部署地区。
- 选择一个实际 LLM 和一个 Embedding 模型。
- 确认生产 PostgreSQL 版本和 pgvector 支持。
- 通过小型 Spike 验证 POST 流式响应在目标平台不被缓冲。
- 使用一个完整项目和首批问题验证精确检索的质量与延迟。

---

## 25. 建议 ADR

根据本选型创建：

```text
docs/decisions/
├── ADR-001-use-modular-monolith.md
├── ADR-002-use-nextjs-and-fastapi.md
├── ADR-003-use-postgresql-and-pgvector.md
├── ADR-004-start-with-exact-vector-search.md
├── ADR-005-use-deterministic-rag-pipeline.md
├── ADR-006-use-provider-adapters.md
├── ADR-007-use-fetch-sse-streaming.md
└── ADR-008-defer-production-model-and-platform.md
```

模型、Embedding 和部署平台确定后追加：

```text
ADR-009-select-llm-and-embedding.md
ADR-010-select-production-platform.md
```

---

## 26. 实施顺序

### 第一步：工程基础

- 初始化 Git 仓库和 `.gitignore`。
- 创建 Next.js / TypeScript 前端。
- 创建 Python 3.13 / uv / FastAPI 后端。
- 配置 Ruff、mypy、pytest、ESLint 和前端测试。
- 创建 Docker Compose PostgreSQL 环境。

### 第二步：数据基础

- 启用 pgvector。
- 建立 SQLAlchemy Model 和首个 Alembic Migration。
- 实现 Knowledge Repository。
- 实现 Markdown Front Matter 校验和 Parser。

### 第三步：入库闭环

- 实现 Chunker。
- 实现 Fake 和真实 Embedding Provider。
- 实现内容哈希、增量判断和导入报告。
- 导入一个完整项目。

### 第四步：RAG 闭环

- 实现查询 Embedding 和精确 Top-K 检索。
- 实现 Evidence Policy 和 Context Builder。
- 实现 Fake 和真实 LLM Provider。
- 实现回答和引用校验。
- 在 CLI 中完成首个端到端回答。

### 第五步：Web MVP

- 实现 Profile 和无状态 Chat API。
- 实现 POST 流式事件协议。
- 实现聊天 UI、推荐问题和引用展示。
- 实现错误、取消和拒答状态。

### 第六步：工程化与上线

- 加入限流、结构化日志、健康检查和成本统计。
- 建立 CI、容器镜像和测试环境。
- 选择生产部署平台。
- 验证迁移、知识重建、HTTPS 和流式链路。
- 执行完整评测后上线。

---

## 27. 待确认事项

1. 首版是否只支持中文，还是同时支持英文。
2. 主要面试官访问地区和后端部署地区。
3. 是否需要满足中国大陆域名备案和云服务要求。
4. 可接受的月度基础设施预算和模型预算。
5. 模型供应商是否允许保存请求，以及需要何种数据保留配置。
6. 选择哪些 LLM 和 Embedding 候选进行第一次评测。
7. 目标托管 PostgreSQL 是否支持 PostgreSQL 18 和 pgvector。
8. 知识源存储在私有 Git 仓库还是独立安全存储。
9. 访客完整对话允许保存多久。

---

## 28. 参考资料

- [Next.js App Router 安装与默认工具链](https://nextjs.org/docs/app/getting-started/installation)
- [Next.js 部署模式](https://nextjs.org/docs/app/getting-started/deploying)
- [Next.js 自托管与流式响应](https://nextjs.org/docs/app/guides/self-hosting)
- [Node.js 版本与 LTS 状态](https://nodejs.org/en/about/previous-releases)
- [FastAPI 功能说明](https://fastapi.tiangolo.com/features/)
- [FastAPI Docker 部署](https://fastapi.tiangolo.com/deployment/docker/)
- [SQLAlchemy 2.0 文档](https://docs.sqlalchemy.org/en/20/)
- [Alembic 自动生成迁移与限制](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [pgvector 官方文档](https://github.com/pgvector/pgvector)
- [uv 项目与 Lockfile](https://docs.astral.sh/uv/guides/projects/)
- [pytest 参数化测试](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
