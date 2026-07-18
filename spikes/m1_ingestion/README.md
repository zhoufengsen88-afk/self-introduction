# M1 第一阶段：知识摄取与检索基线

## 实验目标

在选择 Embedding 和数据库之前，先固定不会随供应商变化的输入规则：

- 仅加载 `visibility: public` 且 `status: published` 的知识文档。
- 校验 Front Matter 和全局唯一 `document_id`。
- 按 Markdown 标题、段落、列表和代码块进行结构优先切块。
- 使用 `document_id + heading_path + section ordinal` 生成稳定 Chunk ID。
- 内容变化通过独立 SHA-256 哈希识别，不让 Chunk ID 随正文小改动漂移。
- 以词法 BM25 作为无模型、无网络的诊断基线。

词法结果不是最终 Embedding 选型结论。后续候选模型必须复用同一批 Chunk、问题和 Top-K 指标，才能公平比较。

## 为什么暂时只用标准库

当前本机默认环境是 Python 3.9，尚未安装项目计划中的 Python 3.13、uv 和 pytest。Spike 使用标准库可以立即验证数据设计，并避免在 M2 工程骨架建立前产生临时依赖。正式实现将使用 `python-frontmatter`、`markdown-it-py` 和 Pydantic。

## 运行

在仓库根目录执行：

```bash
python3 -m unittest discover -s spikes/m1_ingestion/tests -v
python3 -m spikes.m1_ingestion.cli
```

CLI 将结果输出为 JSON，不写入知识目录。实验结论记录在 `docs/m1-spike-report.md`。

## 当前限制

- Front Matter 解析器只支持项目当前使用的平坦标量字段，不是完整 YAML 实现。
- Markdown 解析覆盖 ATX 标题和围栏代码块，不覆盖所有 CommonMark 边界情况。
- 超长代码块保持原子性，因此可能超过 `max_chars`。
- 中文词法基线采用字符、二元组和三元组，不包含语义能力。
