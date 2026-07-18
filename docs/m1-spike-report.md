# M1 技术 Spike 执行报告

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档状态 | 执行中 |
| 当前阶段 | Spike A / B / C 已完成；Spike D Fake Provider 基线已完成，真实 LLM 候选待 API Key |
| 执行日期 | 2026-07-17 |
| 关联文档 | [项目执行计划](./project-plan.md)、[架构设计](./architecture.md)、[技术选型](./technology-selection.md) |
| 实验代码 | [`spikes/m1_ingestion`](../spikes/m1_ingestion/)、[`spikes/m1_embedding`](../spikes/m1_embedding/)、[`spikes/m1_pgvector`](../spikes/m1_pgvector/)、[`spikes/m1_sse`](../spikes/m1_sse/)、[`spikes/m1_llm`](../spikes/m1_llm/) |

## 2. 本阶段目标

在引入 Embedding、pgvector 和 LLM 前，验证下列基础假设：

1. 知识文件能够被确定性加载和校验。
2. 只有 `public + published` 文档能够进入公开检索语料。
3. Markdown 可以按标题和块结构切分，同时不破坏代码块。
4. Chunk ID 不因正文小改动而漂移，正文变化由独立内容哈希识别。
5. 现有评测集可以直接驱动检索评测。

## 3. 实验环境

| 项目 | 当前值 |
| --- | --- |
| 操作系统环境 | macOS 本地开发环境 |
| Python | 3.9.6（系统 Python） |
| 外部依赖 | ingestion 基线无外部依赖；Embedding、pgvector、SSE 使用各自 Spike requirements |
| 测试框架 | Python `unittest` |
| 语料版本 | 2026-07-16 工作区中的 5 份已发布 Skillvar 文档 |
| 评测集 | `evals/datasets/mvp-v1.jsonl` 中 16 条启用用例 |

本阶段使用标准库是为了快速验证数据契约，不改变 M2 使用 Python 3.13、uv、pytest、`python-frontmatter` 和 `markdown-it-py` 的正式选型。

## 4. 已实现能力

- Front Matter 必填字段、枚举、日期、项目 ID 和全局唯一文档 ID 校验。
- 跳过知识目录的 README 和模板，只导入 `visibility: public` 且 `status: published` 的文档。
- 识别 ATX 标题层级，忽略围栏代码块内部的伪标题。
- 按段落和代码块聚合 Chunk；超长普通文本可拆分，超长代码块保持完整。
- Chunk ID 采用 `document_id--heading_path--section_ordinal`，首个 H1 视为文档根标题，不进入 `heading_path`。
- 文档和 Chunk 分别计算 SHA-256 内容哈希。
- 保存前后相邻 Chunk ID，为后续邻接扩展预留数据。
- 实现零依赖 BM25 诊断基线，以及 Hit Rate 和期望文档召回率评测。

## 5. 自动化验证结果

运行命令：

```bash
python3 -m unittest discover -s spikes/m1_ingestion/tests -v
python3 -m spikes.m1_ingestion.cli
```

测试结果：12 项测试全部通过。

覆盖范围包括发布过滤、非法元数据、重复文档 ID、代码块解析、稳定 Chunk ID、内容哈希、当前公开语料集合、评测引用完整性和权限难点检索。

## 6. Chunk 基线

| 指标 | 结果 |
| --- | ---: |
| 已发布文档数 | 5 |
| Chunk 数 | 38 |
| 最短 Chunk | 78 字符 |
| 平均 Chunk | 185.8 字符 |
| 最长 Chunk | 503 字符 |
| 配置上限 | 1200 字符 |

文档分布：

| 文档 | Chunk 数 |
| --- | ---: |
| `skillvar-architecture` | 9 |
| `skillvar-challenges` | 7 |
| `skillvar-overview` | 8 |
| `skillvar-responsibilities` | 11 |
| `skillvar-results` | 3 |

观察：当前文档标题层级较细，因此没有 Chunk 达到强制拆分上限。平均 185.8 字符偏短，Embedding Spike 应同时比较“每个小节独立”和“相邻短小节合并”两种策略，不能把当前切块参数直接视为最终结论。

## 7. 词法检索基线

当前基线使用英文词元和中文字符一元、二元、三元组构建 BM25，并在 Chunk 排名后去重得到文档排名。

| 指标 | 结果 |
| --- | ---: |
| Hit Rate@1 | 50.00% |
| Hit Rate@3 | 81.25% |
| Hit Rate@5 | 100.00% |
| Mean Expected Recall@1 | 37.50% |
| Mean Expected Recall@3 | 75.00% |
| Mean Expected Recall@5 | 100.00% |

补充 Chunk 级人工证据标注后，词法基线结果如下：

| 指标 | 结果 |
| --- | ---: |
| Chunk Hit Rate@1 | 18.75% |
| Chunk Hit Rate@3 | 43.75% |
| Chunk Hit Rate@5 | 56.25% |
| Chunk Mean Expected Recall@3 | 34.58% |
| Chunk Mean Expected Recall@5 | 40.99% |

### 7.1 如何解读

- Top-1 只有一半命中，说明仅靠词面重合无法稳定区分“概述、架构、职责、成果”等相近文档。
- 权限继承、个人职责等词面明确的问题表现较好；“代表项目”“解决什么问题”“最终结果”等抽象问题表现较差。
- Top-5 为 100% 没有选型意义，因为当前语料一共只有 5 份文档。它只能证明评测引用没有指向发布语料之外。
- 当前评测按文档 ID 判断，但真实问答使用 Chunk 证据。Embedding 阶段需要同时增加 Chunk 级证据标注，否则文档命中仍可能取错段落。
- 当前多轮用例只使用最终问题，没有拼接 `history`。问题改写和指代消解应作为后续独立变量评测。

## 8. 本阶段决策

| 决策 | 结论 |
| --- | --- |
| 发布过滤 | 必须在加载阶段执行，并在数据库查询阶段再次执行防御性过滤 |
| Chunk ID | 采用稳定结构 ID，内容哈希独立保存 |
| 代码块 | 保持原子性，允许极少数 Chunk 超过软上限 |
| 词法检索 | 保留为可解释的回归基线，不作为单独的生产检索方案 |
| Agent 框架 | 本阶段没有产生引入 LangChain/LangGraph 的需求 |
| 正式解析器 | M2 替换为选型文档中的生产库，并复用本阶段测试用例 |

## 9. Embedding 对比

### 9.1 候选与可复现配置

| 配置 | Hugging Face revision | 维度 | 查询处理 | 正文处理 |
| --- | --- | ---: | --- | --- |
| `BAAI/bge-small-zh-v1.5` | `7999e1d3359715c523056ef9478215996d62a620` | 512 | 添加中文检索指令 | 无前缀 |
| `intfloat/multilingual-e5-small` | `614241f622f53c4eeff9890bdc4f31cfecc418b3` | 384 | 添加 `query: ` | 添加 `passage: ` |

两个模型均使用 L2 归一化向量和点积，等价于余弦相似度排序。模型运行代码见 [`spikes/m1_embedding`](../spikes/m1_embedding/)。

### 9.2 运行环境

| 项目 | 当前值 |
| --- | --- |
| 设备 | Apple M1，16 GB 内存，CPU 推理 |
| Python | 3.9.6 |
| sentence-transformers | 3.4.1 |
| transformers | 4.57.6 |
| PyTorch | 2.8.0 |
| 语料 | 5 文档、38 Chunk |
| 用例 | 16 条 |

### 9.3 检索质量

| 指标 | BM25 | BGE small zh v1.5 | Multilingual E5 small |
| --- | ---: | ---: | ---: |
| Document Hit@1 | 50.00% | 68.75% | **75.00%** |
| Document Hit@3 | 81.25% | **93.75%** | **93.75%** |
| Document Mean Recall@3 | 75.00% | **93.75%** | **93.75%** |
| Chunk Hit@1 | 18.75% | 18.75% | **43.75%** |
| Chunk Hit@3 | 43.75% | 43.75% | **81.25%** |
| Chunk Hit@5 | 56.25% | 62.50% | **87.50%** |
| Chunk Mean Recall@3 | 34.58% | 25.26% | **47.34%** |
| Chunk Mean Recall@5 | 40.99% | 42.19% | **58.28%** |

### 9.4 本地性能

以下是模型已缓存后的单次本地运行结果，只用于候选间相对比较：

| 指标 | BGE small zh v1.5 | Multilingual E5 small |
| --- | ---: | ---: |
| 模型加载 | 2.14 s | 3.68 s |
| 38 Chunk 批量编码 | 0.51 s | 0.79 s |
| 查询 P50 | **7.34 ms** | 12.04 ms |
| 查询 P95 | **7.80 ms** | 14.45 ms |

样本只有 16 条，延迟没有并发负载，不能外推为生产 SLA。

### 9.5 结果分析

- E5 在 Chunk Hit@3 上达到 81.25%，比 BGE 和词法基线高 37.5 个百分点，是首轮最明显的质量差异。
- E5 查询比 BGE 慢约 4.7 ms，但本项目是低流量个人作品集，这个差异暂时不构成选型阻碍。
- BGE 的文档级指标提高，但 Chunk Mean Recall@3 反而低于词法基线，说明只看文档命中会掩盖证据段落排序问题。
- “Skillvar 解决了什么问题”被 E5 错误理解为 GitLab 权限问题，说明宽泛问题仍需要推荐问题改写、混合检索或项目概述加权。
- “主要技术”“具体职责”需要多个证据片段，Top-3 天然无法覆盖全部人工标注 Chunk。后续应验证邻接扩展或分层检索，而不是无限提高 Top-K。
- 16 条用例中每一条占 6.25 个百分点；扩大知识库后必须重新评测，不能把当前分数当作稳定泛化能力。

## 10. Spike A 临时决策

| 决策项 | 结论 |
| --- | --- |
| pgvector 临时 Embedding | `intfloat/multilingual-e5-small` |
| 模型 revision | `614241f622f53c4eeff9890bdc4f31cfecc418b3` |
| 向量维度 | 384 |
| 距离 | L2 归一化后的余弦距离 |
| 输入格式 | 查询使用 `query: `，Chunk 使用 `passage: ` |
| 生产模型状态 | 尚未最终锁定；知识规模扩大和部署地区确认后复评 |
| 检索策略方向 | 保留 BM25，后续验证稠密向量 + BM25 混合检索和邻接扩展 |

这项临时选择足以固定 Spike B 的测试表结构，但不能直接解释为生产部署已经决定采用本地 E5 推理。

## 11. Spike B：PostgreSQL + pgvector

### 11.1 运行环境

| 项目 | 当前值 |
| --- | --- |
| PostgreSQL | 18.4（Homebrew 临时实例，端口 55432） |
| pgvector | 0.8.5 |
| Python 驱动 | psycopg 3.2.13 |
| Embedding | `intfloat/multilingual-e5-small` |
| 向量维度 | 384 |
| 语料 | 5 文档、38 Chunk |
| 用例 | 16 条 |

本机默认 PostgreSQL 为 16.14，但 Homebrew `pgvector` bottle 提供的是 PostgreSQL 17/18 扩展文件。因此本次 Spike 使用 PostgreSQL 18 临时实例验证，不切换系统默认 PostgreSQL。

### 11.2 已实现能力

- 建立 `m1_documents`、`m1_chunks`、`m1_chunk_embeddings` 三张最小表。
- `m1_chunk_embeddings` 使用 `(chunk_id, embedding_model, embedding_revision)` 作为主键，支持同一 Chunk 的多版本 Embedding 隔离。
- 使用 `vector(384)` 保存归一化向量，并用 `<=>` 执行精确余弦距离排序。
- 查询阶段通过 SQL 强制过滤 `visibility = 'public'` 且 `status = 'published'`。
- 导入逻辑使用 upsert，重复导入同一语料不会产生重复行。
- 使用私有探针文档验证：如果不加可见性过滤，私有 Chunk 会排第一；加过滤后不会返回。

### 11.3 验证结果

运行命令：

```bash
/tmp/self-introduction-m1-venv/bin/python -m unittest discover -s spikes/m1_pgvector/tests -v
/tmp/self-introduction-m1-venv/bin/python -m spikes.m1_pgvector.run --reset
```

| 验证项 | 结果 |
| --- | --- |
| pgvector 与内存向量 Top-5 排名一致 | 通过 |
| 重复导入幂等 | 通过 |
| 私有文档查询过滤 | 通过 |
| Embedding revision 隔离 | 通过 |

导入两次后，真实 revision 下仍为 5 个 Document、38 个 Chunk、38 条 Embedding。额外插入的私有探针在未过滤查询中排名第一，但在公开查询中不会返回。

### 11.4 pgvector 检索指标

由于 pgvector 排名与内存向量 Top-5 完全一致，评测结果与 E5 本地向量实验一致：

| 指标 | 结果 |
| --- | ---: |
| Document Hit@1 | 75.00% |
| Document Hit@3 | 93.75% |
| Document Mean Recall@3 | 93.75% |
| Chunk Hit@1 | 43.75% |
| Chunk Hit@3 | 81.25% |
| Chunk Hit@5 | 87.50% |
| Chunk Mean Recall@3 | 47.34% |
| Chunk Mean Recall@5 | 58.28% |

本地 16 条查询的向量编码耗时 P50 为 12.89 ms，P95 为 15.75 ms。这个数字主要反映本机 CPU 上 E5 查询向量编码耗时，不代表生产数据库 SLA。

### 11.5 Spike B 决策

| 决策项 | 结论 |
| --- | --- |
| 表结构 | 生产阶段继续采用 Document、Chunk、ChunkEmbedding 分表思路 |
| 可见性过滤 | 必须在 SQL 查询阶段强制执行，不能只依赖应用层 |
| Embedding 版本 | 必须进入查询条件，避免新旧向量混排 |
| pgvector 查询 | 当前规模先使用精确余弦检索，不引入 ANN 索引 |
| PostgreSQL 版本 | 本地和生产优先对齐 PostgreSQL 18，避免扩展版本错配 |

Spike B 已满足通过门槛，可以进入 Spike C：FastAPI SSE。

## 12. Spike C：FastAPI SSE

### 12.1 运行环境

| 项目 | 当前值 |
| --- | --- |
| FastAPI | 0.115.6 |
| Uvicorn | 0.34.0 |
| HTTPX | 0.28.1 |
| Node.js | 26.4.0 |
| Python | 3.9.6 临时 venv |

### 12.2 已实现能力

- 使用 FastAPI `StreamingResponse` 返回 `text/event-stream`。
- 定义并验证 `delta`、`done`、`error` 和 `cancelled` 四类事件。
- 响应头设置 `Cache-Control: no-cache` 和 `X-Accel-Buffering: no`，降低代理缓冲风险。
- 使用真实 uvicorn 进程和 HTTP 客户端验证 POST 流式响应。
- 使用 Node.js Web Fetch / ReadableStream API 验证流式消费、服务端错误、服务端取消和客户端主动 abort。
- 提供浏览器页面示例 `browser_client.html`，用于后续手动或 Playwright 验证。

### 12.3 验证结果

运行命令：

```bash
/tmp/self-introduction-m1-venv/bin/python -m unittest discover -s spikes/m1_sse/tests -v
/tmp/self-introduction-m1-venv/bin/python -m unittest discover -s spikes -v
node spikes/m1_sse/fetch_client.mjs http://127.0.0.1:8010 normal
node spikes/m1_sse/fetch_client.mjs http://127.0.0.1:8010 error
node spikes/m1_sse/fetch_client.mjs http://127.0.0.1:8010 cancelled
node spikes/m1_sse/fetch_client.mjs http://127.0.0.1:8010 client-cancel
```

| 验证项 | 结果 |
| --- | --- |
| SSE 编码和解析 | 通过 |
| `delta` + `done` 正常完成 | 通过 |
| `error` 错误事件 | 通过 |
| `cancelled` 服务端取消事件 | 通过 |
| 客户端断开后服务端标记取消 | 通过 |
| Fetch + ReadableStream 消费 POST 流 | 通过 |

全量 `spikes` 测试共 19 项通过。

### 12.4 边界说明

本环境的 in-app browser 插件当前没有可用浏览器实例，未能完成真实浏览器点击验证。因此本阶段使用 Node.js 的 Web Fetch / ReadableStream API 完成流式客户端验证，并保留浏览器 HTML 页面用于 M2 前端工程或 Playwright 环境继续验证。

本阶段只验证本地直连 uvicorn 的流式语义，不代表目标部署平台不会缓冲响应。正式部署候选平台仍需要单独验证代理、CDN 或 Serverless 网关是否支持无缓冲 SSE。

### 12.5 Spike C 决策

| 决策项 | 结论 |
| --- | --- |
| 服务端协议 | MVP 可使用 `text/event-stream` 承载 POST 流式回答 |
| 事件类型 | 固定为 `delta`、`done`、`error`、`cancelled` 起步 |
| 客户端消费 | 前端使用 `fetch` + `ReadableStream`，不依赖原生 `EventSource` |
| 取消处理 | 客户端 abort 后服务端必须感知并停止生成 |
| 部署风险 | 代理缓冲是后续平台验证重点 |

Spike C 已满足通过门槛，可以进入 Spike D：LLM 候选。

## 13. Spike D：LLM 候选与回答契约

### 13.1 当前实现范围

| 项目 | 当前值 |
| --- | --- |
| Provider | `fake-llm` |
| 上下文策略 | oracle context，使用评测集 `expected_chunk_ids` 构造证据 |
| 启用问答用例 | 16 条 |
| 额外拒答用例 | 2 条 |
| 公开 Chunk | 38 个 |
| 真实 Provider API Key | 当前环境未检测到 OpenAI、DashScope、ZhipuAI/GLM 或 Anthropic key |

本阶段先验证模型无关契约：Prompt、流式事件、引用、拒答和离线评测。真实模型比较尚未执行，因此不能把 Fake Provider 的结果解释为真实模型质量。

### 13.2 已实现能力

- 建立 Fake LLM Provider，固定 `delta` 和 `done` 流式事件。
- `done` 事件包含 `citations`、`refused` 和 `refusal_reason`。
- 使用同一批 oracle context 隔离检索误差，先验证生成层契约。
- 评测 required facts、forbidden facts、引用合法性和拒答准确性。
- 将 2 条 disabled 的安全/证据不足用例纳入 LLM 层拒答评测。

### 13.3 验证结果

运行命令：

```bash
python3 -m unittest discover -s spikes/m1_llm/tests -v
python3 -m spikes.m1_llm.run
/tmp/self-introduction-m1-venv/bin/python -m unittest discover -s spikes -v
```

| 指标 | 结果 |
| --- | ---: |
| 用例总数 | 18 |
| Answer Contract Pass Rate | 100.00% |
| Refusal Accuracy | 100.00% |
| Required Fact Pass Rate | 100.00% |
| Mean Required Recall | 100.00% |
| Forbidden Fact Pass Rate | 100.00% |
| Citation Pass Rate | 100.00% |
| Fake Provider 成本 | 0 USD |

全量 `spikes` 测试共 22 项通过。

### 13.4 边界说明

Fake Provider 通过率为 100% 只说明回答契约和评测器可运行，不说明真实 LLM 能达到相同质量。真实 LLM 还需要在相同 context、Prompt 和评测集上比较中文表达、事实忠实度、引用稳定性、拒答表现、首 Token 延迟、总延迟、错误率和成本。

### 13.5 Spike D 当前决策

| 决策项 | 结论 |
| --- | --- |
| Fake Provider | 保留为 M2/M3 的自动化测试基线 |
| 评测上下文 | 真实模型比较先使用 oracle context，之后再切回检索结果 |
| 引用契约 | 非拒答必须返回合法 Chunk 引用；拒答默认不返回引用 |
| 拒答评测 | 安全和证据不足用例必须纳入 LLM 层评测 |
| 真实模型状态 | 尚未选择；当前环境没有可调用 API Key |

Spike D 的离线基线已完成，但通过门槛尚未完全满足：还需要配置至少一个真实 LLM Provider 并完成候选对比。

## 14. 下一阶段

1. 配置一个真实 LLM Provider 的 API Key，并确认候选模型。
2. 使用相同 Prompt、oracle context 和评测器跑真实模型。
3. 记录质量、首 Token 延迟、总延迟、错误率和成本。
4. 若暂时不配置真实模型，可以先进入 M2 工程骨架，并把 Fake Provider 作为默认测试 Provider。
