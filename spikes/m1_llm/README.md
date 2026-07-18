# M1 第五阶段：LLM 候选与回答契约

本实验先建立模型无关的回答契约和评测入口，再接入真实 LLM Provider。

## 当前实现

- 读取 `evals/datasets/mvp-v1.jsonl` 中 16 条启用用例。
- 额外纳入 2 条 `should_refuse = true` 的安全/证据不足用例。
- 使用 oracle context，即直接使用评测集中标注的 `expected_chunk_ids` 构造上下文，隔离检索误差。
- 使用 Fake LLM Provider 固定输出契约：
  - `delta`：增量文本。
  - `done`：结束事件，包含 `citations`、`refused` 和 `refusal_reason`。
- 评测 required facts、forbidden facts、引用合法性和拒答准确性。

## 运行

```bash
python3 -m unittest discover -s spikes/m1_llm/tests -v
python3 -m spikes.m1_llm.run
```

## 解释边界

Fake Provider 不是质量模型，它只是一个稳定的契约测试基线。真实模型比较需要 API key 和候选模型确认后再运行；本阶段不会虚构真实模型分数。
