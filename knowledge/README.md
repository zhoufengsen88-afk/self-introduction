# 个人知识库编写规范

该目录是 Agentic RAG 个人经历助手的人工审核事实源。模型回答中的个人事实必须能够追溯到这里的已发布文档。

## 1. 目录结构

```text
knowledge/
├── profile/               # 个人简介和技能
├── resume/                # 结构化简历
└── projects/
    ├── _template/         # 项目模板，不参与入库
    └── <project-id>/      # 真实项目资料
```

`_template` 目录及 `status: draft` 的文档不得进入生产知识库。

## 2. Front Matter

每份知识文档必须以 YAML Front Matter 开头：

```yaml
---
document_id: project-a-overview
title: 项目 A 概述
category: project
project_id: project-a
aliases: 项目 A,Project A
visibility: public
status: published
updated_at: 2026-07-15
---
```

字段规则：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `document_id` | 是 | 稳定、唯一、使用小写字母/数字/连字符；发布后不要随意修改 |
| `title` | 是 | 可向访客展示的安全标题，不包含内部路径或机密名称 |
| `category` | 是 | `profile`、`skills`、`resume`、`project` 之一 |
| `project_id` | 项目文档必填 | 同一项目所有文档使用相同 ID；非项目文档为 `null` |
| `aliases` | 否 | 项目名称或简称，使用英文逗号、中文逗号或 `|` 分隔；可只写在一份项目文档中 |
| `visibility` | 是 | `public` 或 `private` |
| `status` | 是 | `draft` 或 `published` |
| `updated_at` | 是 | 内容最后人工审核日期，格式为 `YYYY-MM-DD` |

默认安全规则：

- 新文档先使用 `visibility: private` 和 `status: draft`。
- 只有经过人工审核后才能改为 `published`。
- 不确定能否公开的内容保持 `private`。
- 模板中的 `replace-me` 必须替换后才能发布。

## 3. 可见性

| 级别 | 参与公开检索 | 可发送给模型 | 可展示原文 |
| --- | --- | --- | --- |
| `public` | 是 | 是 | 是，经过安全裁剪 |
| `private` | 否 | 否 | 否 |

MVP 不使用 `answer_only`。允许发送给模型但不允许向访客展示的中间级别会增加不必要的泄露边界，不适合当前个人作品集。

## 4. 内容编写原则

### 4.1 只写可以确认的事实

- 不使用“应该”“大概”等猜测补全经历。
- 量化结果写明时间范围、统计口径和个人贡献。
- 无法公开的公司、客户或系统名称使用一致的安全代称。
- 不因表达效果夸大职责、规模和成果。

### 4.2 区分个人与团队

建议使用明确表述：

```text
个人负责：我设计并实现了……
协作完成：我与前端/产品/测试共同完成了……
团队成果：项目整体实现了……，其中我的贡献是……
不负责：部署平台由基础设施团队维护，我只负责应用侧接入。
```

### 4.3 提高事实密度

优先写：

- 背景和约束。
- 具体职责。
- 技术选择及备选方案。
- 问题定位过程。
- 实施动作。
- 可核验结果。
- 失败、限制和复盘。

避免只写“负责项目开发”“提升了性能”“取得良好效果”等无法支持深入问答的空泛表述。

### 4.4 保护敏感信息

不得写入可被系统读取的文档：

- API Key、密码、Cookie、Token、连接串。
- 身份证件、家庭住址和未决定公开的联系方式。
- 前雇主未公开的客户信息、商业数据和内部地址。
- 受保密协议限制的代码、配置和架构细节。

密钥即使标记为 `private` 也不得放入知识目录。

## 5. 项目创建方法

1. 复制 `projects/_template/` 为 `projects/<project-id>/`。
2. 将所有 `replace-me` 替换为真实、稳定的项目 ID 和标题。
3. 先保持 `private + draft`，完成内容填写。
4. 审核事实、职责、数字口径和敏感信息。
5. 确认允许公开的文档后改为 `public + published`。
6. 为每个主要 Section 增加对应评测问题。

项目不需要在 Router 中手工注册。系统启动时会从所有 `public + published`
项目文档的 `project_id`、标题和 `aliases` 自动建立项目注册表，并将同一
`project_id` 下的文档聚合为一个知识域。例如：

```yaml
project_id: nebula-forge
title: Nebula Forge 项目概述
aliases: 星云工坊,Nebula
```

发布后，`Nebula Forge`、`nebula-forge`、`星云工坊` 和 `Nebula` 都可以触发
该项目的知识检索。草稿或私有文档不会注册名称，也不会参与检索。

更新知识后执行：

```bash
make ingest
```

该命令会显示当前可检索文档、Chunk 和项目注册表。内存模式需要重启 API
加载新文档；pgvector 模式还需要执行 `make ingest-db-e5` 重新入库，再重启 API。

## 6. 发布前检查

- [ ] Front Matter 字段完整且格式正确。
- [ ] `document_id` 唯一并且不含 `replace-me`。
- [ ] 没有未完成的 `[TODO]`。
- [ ] 项目、公司和客户名称符合公开策略。
- [ ] 个人职责和团队成果已经区分。
- [ ] 数字有来源和统计口径。
- [ ] 没有密钥、私人信息或保密内容。
- [ ] 可见性设置经过人工确认。
- [ ] 文档状态已从 `draft` 改为 `published`。
- [ ] 对应评测问题已经补充。
- [ ] `make ingest` 中能看到预期的项目 ID、别名和文档列表。

## 7. 当前已发布知识域

截至 2026-07-18，已发布个人资料：

- `profile-introduction`
- `profile-skills`
- `resume-main`

已发布项目知识域为 Agentic RAG 个人经历助手，包含：

- `self-introduction-agentic-rag-overview`
- `self-introduction-agentic-rag-architecture`
- `self-introduction-agentic-rag-responsibilities`
- `self-introduction-agentic-rag-features`
- `self-introduction-agentic-rag-data-flows`
- `self-introduction-agentic-rag-challenges`
- `self-introduction-agentic-rag-results`
- `self-introduction-agentic-rag-reflection`

已发布项目知识域为 Skillvar，包含：

- `skillvar-overview`
- `skillvar-responsibilities`
- `skillvar-architecture`
- `skillvar-challenges`
- `skillvar-results`
- `skillvar-features`
- `skillvar-data-flows`
- `skillvar-reflection`

已发布项目知识域为 OntoCore，包含：

- `ontocore-overview`
- `ontocore-responsibilities`
- `ontocore-architecture`
- `ontocore-features`
- `ontocore-data-flows`
- `ontocore-challenges`
- `ontocore-results`
- `ontocore-reflection`

`skillvar-source-review` 和 `ontocore-source-review` 仍为私有草稿，只用于维护证据和安全边界，不进入公开问答。Signal Field Agent、Vacuum Agent 等其他项目文档在发布前不进入生产知识库。
