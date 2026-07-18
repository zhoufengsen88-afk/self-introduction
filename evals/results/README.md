# Agentic RAG 评测结果目录

该目录保存版本化评测报告，不保存临时调试输出。

每次正式评测结果至少记录：

```text
run_id
started_at
application_commit
evaluation_dataset_version
knowledge_base_version
chunker_version
embedding_model
embedding_dimensions
retrieval_strategy_version
top_k
evidence_policy_version
prompt_version
llm_model
agent_route_version
answer_generator
```

建议结果文件名：

```text
YYYYMMDD-HHMMSS-<run-id>.json
```

## 当前基线

M3 已生成第一份终端版 RAG 基线：

```text
evals/results/m3-baseline.json
evals/results/m3.2-pgvector-baseline.json
evals/results/m3.3-e5-pgvector-baseline.json
evals/results/m3.4-semantic-memory-baseline.json
evals/results/m3.4-semantic-hashing-pgvector.json
evals/results/m3.4-semantic-e5-pgvector.json
evals/results/m3.5-query-understanding-memory.json
evals/results/m3.5-query-understanding-hashing-pgvector.json
evals/results/m3.5-query-understanding-e5-pgvector.json
```

该基线使用：

- 公开知识库：`knowledge/` 中 `public + published` 文档。
- 检索策略：内存 BM25 + 轻量意图重排。
- Top-K：8。
- 回答策略：确定性证据组织器，不调用真实 LLM。
- 评测集：`evals/datasets/mvp-v1.jsonl` 中 16 条启用用例。

当前结果：

- Citation Hit Rate：100%。
- Mean Required Recall：100%。
- Forbidden Pass Rate：100%。

M3.2 pgvector 基线使用：

- 数据库：PostgreSQL + pgvector。
- Embedding：`local-hashing-embedding`，revision `m3.2-v1`，384 维。
- 检索策略：pgvector 精确余弦候选召回 + 轻量意图重排。
- 回答策略：确定性证据组织器，不调用真实 LLM。

M3.3 E5 pgvector 基线使用：

- 数据库：PostgreSQL + pgvector。
- Embedding：`multilingual-e5-small`，revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`，384 维。
- 检索策略：真实 dense embedding 精确余弦候选召回 + 轻量意图重排。
- 回答策略：确定性证据组织器，不调用真实 LLM。

注意：这些分数用于验证 M3/M3.2/M3.3 工程闭环和公开知识库质量。当前只有 16 条启用用例，不能把 100% 分数解读为最终线上质量。

M3.4 语义压力集原始观察：

| 方案 | Document Hit | Chunk Hit | Required Recall | Forbidden Pass |
| --- | ---: | ---: | ---: | ---: |
| memory baseline | 61.54% | 61.54% | 42.31% | 100% |
| hashing pgvector | 92.31% | 53.85% | 56.41% | 100% |
| E5 pgvector | 100% | 84.62% | 76.92% | 100% |

M3.4 说明：真实 E5 Embedding 在英文、弱关键词和同义改写问题上明显优于 Hashing 与内存 BM25，但仍需要查询改写和 rerank 继续提升 Chunk 级精确命中。

注意：M3.4 的原始数字作为历史观察记录在文档中；当前工作区继续演进 Pipeline 后，重新运行 `make eval-semantic` 等旧命令会用最新代码覆盖同名 JSON。M3.5 后的正式留档使用 `m3.5-query-understanding-*` 文件。

M3.5 查询理解优化后，同一语义压力集结果：

| 方案 | Document Hit | Chunk Hit | Required Recall | Forbidden Pass |
| --- | ---: | ---: | ---: | ---: |
| memory baseline | 76.92% | 76.92% | 61.54% | 100% |
| hashing pgvector | 100% | 84.62% | 76.92% | 100% |
| E5 pgvector | 100% | 100% | 100% | 100% |

M3.5 说明：查询理解层通过确定性意图识别、查询扩展和轻量重排，修复了 MCP/CLI、检索降级和多轮权限难点问题；主评测集 `mvp-v1.jsonl` 在 memory、hashing pgvector 和 E5 pgvector 三种方案下仍保持 100%，未出现回归。

M4.2 后需要新增真实 LLM 与 Agentic Router 评测结果，至少记录：

- Router 命中率。
- LLM 回答忠实度。
- 引用合法率。
- 正确拒答率。
- 首 Token 延迟和总延迟。
- 单次问答估算成本。

M5.2 已新增真实 LLM Runner：

```bash
make eval-m5-llm
```

当前默认结果写入 `evals/results/m5-current-llm-memory.json`，避免覆盖 `m5.2`、`m5.3` 等历史基线文件。其中自动指标用于定位 Route、引用、拒答和明确禁止事实问题。`human_review` 字段作为可选扩展保留；本项目定位为面试展示用轻量工程作品，不安排逐条人工打分阶段。当前 Provider 未返回 Token Usage 和服务商计费信息，因此 Runner 不伪造 Token 或成本估算。

首次 memory + `deepseek-v4-flash` 单次基线已完成：25 条用例、Route Accuracy 84%、Document/Chunk Hit 80%、Refusal Accuracy 96%、Deterministic Checks Pass 72%，Provider Error 为 0。详细失败分析见 `docs/m5.2-llm-eval-report.md`；这些数字是开发基线，不应解释为线上质量或 SLA。

M5.3 修复后，同一数据集单次回归达到 Route、引用展示、Document/Chunk Hit、拒答和 Deterministic Checks 100%，Provider Error 为 0；平均引用数从 5.76 降到 4.56。详细对比见 `docs/m5.3-query-quality-report.md`。自动检查 100% 只表示工程回归通过，不表述为人工忠实度 100%。

补充 Agentic RAG 项目自身完整知识后，M5 数据集扩展为 38 条。当时最新真实 LLM 结果写入：

```text
evals/results/m5-current-llm-memory.json
```

当前单次结果：

- Route Accuracy：100%。
- Citation Presence Accuracy：100%。
- Document Hit Rate：100%。
- Chunk Hit Rate：100%。
- Refusal Accuracy：100%。
- Forbidden Pass Rate：100%。
- Deterministic Checks Pass Rate：100%。
- Provider Error：0。
- Mean Required String Recall：57.53%。

其中 Required String Recall 是机械字符串召回，不等同于人工语义评分；本项目仍不声称已完成人工忠实度审核。

补充 OntoCore 项目知识后，M5 数据集扩展为 45 条。目前已完成确定性 memory 回归：

```text
evals/results/m5-current-deterministic-memory.json
```

当前确定性结果：

- Citation Hit Rate：100%。
- Document Hit Rate：100%。
- Forbidden Pass Rate：100%。
- Mean Required Recall：100%。

45 条 OntoCore 扩展后的真实 LLM 回归尚未重新运行；如果需要更新 `m5-current-llm-memory.json`，需显式执行 `make eval-m5-llm`。
