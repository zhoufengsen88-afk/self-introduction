# M4 Web MVP 报告：Agentic RAG 展示层

## 1. 目标

M4 的目标是把 M3 已经验证过的 RAG 检索能力接到一个真实可用的浏览器界面中，让面试官可以直接围绕候选人的公开经历提问。

本阶段不追求复杂视觉动效，也不进入公网部署。更重要的是：M4 只是 Agentic RAG 项目的展示层，不能代表真实 LLM 生成和 Agent 编排已经完成。

## 2. 已实现功能

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 候选人首页 | 已完成 | 首页首屏说明项目用途、当前能力和公开知识库边界 |
| 推荐问题 | 已完成 | 提供 Skillvar 概述、职责、难点、MCP/CLI、检索降级和职责边界等问题 |
| 流式回答 | 已完成 | 前端通过 `fetch` + `ReadableStream` 消费 `/api/chat/stream` |
| 引用卡片 | 已完成 | 展示文档标题、标题路径、片段摘要和检索分数 |
| 多轮追问 | 已完成 | 发送最近浏览器会话历史给 API，服务端结合 history 做查询理解 |
| 浏览器短期历史 | 已完成 | 使用 `sessionStorage` 保存当前浏览器会话，不写入服务端 |
| 停止生成 | 已完成 | 使用 `AbortController` 取消当前流式请求 |
| 拒答状态 | 已完成 | 支持展示 restricted / insufficient evidence 等拒答原因 |
| 错误状态 | 已完成 | API 未启动或请求失败时展示错误提示 |
| 清空会话 | 已完成 | 支持清空浏览器中的短期对话历史 |

## 3. 主要改动

| 文件 | 说明 |
| --- | --- |
| `apps/web/app/page.tsx` | 从单问题 Demo 升级为完整聊天界面 |
| `apps/web/lib/sse.ts` | 补全流式 done 事件中的 Citation 类型 |
| `docs/m4-web-mvp-report.md` | 记录 M4 范围、验收和边界 |
| `docs/project-plan.md` | 更新 M4 任务状态和下一执行点 |
| `README.md` | 更新当前阶段和能力说明 |

## 4. 验证结果

已通过：

```text
pnpm --filter @self-introduction/web lint
pnpm --filter @self-introduction/web typecheck
pnpm --filter @self-introduction/web test
```

完整工程验证在本阶段收尾时执行。

## 5. 当前边界

- 当前 Web 默认连接本地 API：`http://127.0.0.1:8000`。
- 当前对话历史只保存在浏览器 `sessionStorage`，刷新后同一标签页会保留，关闭会话后消失。
- 当前没有服务端用户体系、完整对话落库、反馈系统和后台管理。
- 当前仍使用确定性证据组织器，不是真实 LLM 生成。
- 当前没有 Agentic Router / Safe Tool Layer 的正式实现。
- 当前没有公网域名、HTTPS、限流和生产日志，以上进入 M5。

## 6. 下一步建议

建议优先进入 M4.2：真实 LLM 与 Agentic RAG 编排，而不是继续只打磨前端。

M4.2 需要完成：

1. 接入真实 LLM Provider。
2. 将检索到的 Chunk 构造成 Prompt 上下文。
3. 让 LLM 基于公开证据流式生成自然回答。
4. 保留 Citation Validator 和拒答策略。
5. 增加 Agentic Router / Safe Tool Layer 的最小实现。
6. 增加 LLM/Agent 评测。

M4.1 前端产品化打磨仍然需要做，但应排在 M4.2 核心链路之后；否则项目容易被误解成“个人主页前端项目”，而不是 Agent 应用开发工程项目。
