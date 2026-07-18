# Agentic RAG 评测数据规范

该目录保存 Agentic RAG 个人经历助手的版本化评测输入和结果。评测集用于比较知识内容、Chunk、Embedding、检索、Agentic Router、Evidence Policy、Prompt、模型和引用校验变化，不作为个人事实源。

## 1. 目录结构

```text
evals/
├── README.md
├── datasets/
│   ├── mvp-v1.jsonl
│   ├── m3.4-semantic-v1.jsonl
│   └── m5-agent-qa-v1.jsonl
└── results/
    └── README.md
```

## 2. JSONL 规则

- 每行是一个独立 JSON 对象。
- 文件使用 UTF-8 编码。
- `id` 在数据集内唯一，发布后保持稳定。
- 尚未补全真实期望的样例使用 `"enabled": false`。
- 只有经过人工审核的样例才能设置为 `enabled: true`。
- 不在评测数据中写入真实密钥或不允许发送给模型的隐私内容。

## 3. 数据结构

```json
{
  "id": "project-responsibility-001",
  "enabled": true,
  "category": "responsibility",
  "question": "你在项目 A 中具体负责什么？",
  "history": [],
  "expected_document_ids": ["project-a-responsibilities"],
  "required_facts": ["负责后端核心模块设计与实现"],
  "forbidden_facts": ["独立完成了整个项目"],
  "should_refuse": false,
  "refusal_reason": null,
  "tags": ["project-a", "single-turn"],
  "notes": "职责边界必须明确"
}
```

### 3.1 字段说明

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 稳定、唯一的用例 ID |
| `enabled` | boolean | 是 | 是否进入正式评测 |
| `category` | string | 是 | 问题类别 |
| `question` | string | 是 | 当前用户问题 |
| `history` | array | 是 | 多轮问题所需历史消息，单轮为空数组 |
| `expected_document_ids` | string[] | 是 | 期望进入 Top-K 的知识文档 ID |
| `required_facts` | string[] | 是 | 正确回答必须覆盖的事实 |
| `forbidden_facts` | string[] | 是 | 回答不得出现的错误或越界事实 |
| `should_refuse` | boolean | 是 | 是否期望拒答 |
| `refusal_reason` | string/null | 是 | `insufficient_evidence`、`restricted_content`、`out_of_scope` 等 |
| `tags` | string[] | 是 | 项目、单轮/多轮、安全等标签 |
| `notes` | string | 是 | 人工评审说明，不传给回答模型 |

M5 面试问答集在上述兼容字段外增加：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `expected_route` | string | 是 | 期望进入的顶层路由：`knowledge_rag`、`normal_chat`、`out_of_scope` 或 `restricted` |
| `citation_required` | boolean | 是 | 最终回答是否应展示知识库引用 |
| `acceptance_criteria` | string[] | 是 | 需要人工判断的忠实度、边界和表达标准 |

### 3.2 History 格式

```json
[
  {"role": "user", "content": "你最有代表性的项目是什么？"},
  {"role": "assistant", "content": "基于已审核资料生成的历史回答占位。"}
]
```

正式评测时，历史回答应固定或由评测 Runner 以前一轮结果构造，并记录所用模式。不能在不同运行中混用而不标记。

## 4. 推荐类别

| category | 说明 |
| --- | --- |
| `profile` | 个人介绍、方向和优势 |
| `skills` | 技术能力和能力边界 |
| `project_overview` | 项目背景、目标和范围 |
| `responsibility` | 个人、团队和非职责边界 |
| `architecture` | 架构、数据流和技术栈 |
| `decision` | 选型、备选方案和权衡 |
| `challenge` | 问题、定位、根因和解决方案 |
| `result` | 指标、成果和统计口径 |
| `reflection` | 失败、限制和复盘 |
| `multi_turn` | 指代、省略和连续追问 |
| `insufficient` | 知识库不存在的个人事实 |
| `security` | 隐私、越权和 Prompt Injection |
| `route` | Agentic Router 应选择的处理路径 |

## 5. 评测层次

### 5.1 检索评测

- Expected Document Recall@K。
- Expected Chunk Recall@K（Chunk 稳定后增加）。
- M3.4 起，评测结果同时记录 `document_hit_rate` 和 `citation_hit_rate`。
- `document_hit_rate` 用于判断是否找到正确资料源。
- `citation_hit_rate` 在存在 `expected_chunk_ids` 时用于判断是否命中正确证据 Chunk。
- Top-K 中是否出现 `private` 内容，正确结果必须始终为否。
- 检索延迟。

### 5.2 生成评测

- `required_facts` 覆盖率。
- `forbidden_facts` 命中数。
- 是否正确拒答。
- 引用 ID 是否属于本次上下文。
- 引用是否指向期望文档。

### 5.3 Agentic 路由评测

- 问题是否进入期望 Route，例如 `project_deep_dive`、`responsibility_boundary`、`restricted`。
- Router 是否选择了允许的内部工具。
- Router 是否避免把无证据问题交给生成器编造。
- Router 输出是否可解释、可记录、可回归。

### 5.4 人工评测

- 回答是否自然、专业并适合面试场景。
- 是否清晰区分个人和团队贡献。
- 是否存在没有直接字符串匹配但语义错误的描述。
- 引用是否真正支持对应结论。

模型裁判只能作为辅助指标，权限、引用合法性和关键禁止事实必须有确定性检查。

## 6. 从骨架转为正式数据

1. 将 `replace-me-*` 文档 ID 替换为真实知识文档 ID。
2. 将问题中的“代表项目”替换为公开项目名称或安全代称。
3. 根据知识文档填写 `required_facts`。
4. 填写容易被模型夸大的 `forbidden_facts`。
5. 确认拒答问题确实没有公开证据或属于受限内容。
6. 人工审核后将 `enabled` 改为 `true`。
7. 运行 JSONL 校验和首次检索评测。

## 7. 数据集发布检查

- [ ] 所有 `id` 唯一。
- [ ] 每行 JSON 可以独立解析。
- [ ] 启用用例不包含 `replace-me`。
- [ ] 启用的可回答用例至少有一个期望文档。
- [ ] `should_refuse: true` 时具有明确 `refusal_reason`。
- [ ] 正常问题、职责边界、无证据、多轮和安全问题均有覆盖。
- [ ] 没有私密原文和密钥。
- [ ] 数据集版本已经记录在评测结果中。

## 8. 当前数据集状态

截至 2026-07-16：

- `mvp-v1.jsonl` 共 30 条用例。
- 16 条 Skillvar 用例已人工审核并启用，覆盖项目概述、职责、架构、权限难点、成果和多轮追问。
- 技术决策、复盘、个人资料、安全和无证据用例仍保持禁用，等待对应知识发布或运行链路建立后再审核启用。

截至 2026-07-17：

- 新增 `m3.4-semantic-v1.jsonl`，共 13 条启用用例。
- 该数据集用于测试英文、同义改写、弱关键词、职责边界、指标边界和多轮指代。
- M3.4 语义压力集显示 E5 pgvector 明显优于 Hashing pgvector 与 memory baseline。

截至 2026-07-18：

- 新增 `m5-agent-qa-v1.jsonl`，共 30 条真实面试与边界问题。
- 发布个人资料和本 Agentic RAG 项目概述后，30 条 M5 用例已全部启用。
- `mvp-v1.jsonl` 已启用 6 条个人介绍、方向、优势和技能边界用例，当前共 22 条启用用例。
- 新增 Route、引用要求和人工验收标准，为真实 LLM 回答质量评测做准备。

补充 Agentic RAG 项目自身完整知识后：

- `m5-agent-qa-v1.jsonl` 扩展为 38 条真实面试与边界问题。
- 新增 8 条本项目自身深挖用例，覆盖架构、功能、调用链、职责、AI 辅助开发边界、难点、成果和复盘。
- 38 条 M5 用例均已启用。

补充 OntoCore 项目知识后：

- `m5-agent-qa-v1.jsonl` 扩展为 45 条真实面试与边界问题。
- 新增 7 条 OntoCore 用例，覆盖项目概述、个人职责、团队边界、知识图谱难点、AI 查询链路、系统检测和成果指标边界。
- 45 条 M5 用例均已启用。
