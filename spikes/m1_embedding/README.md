# M1 第二阶段：Embedding 对比

本实验复用 `m1_ingestion` 生成的 38 个 Chunk 和 16 条启用评测用例，比较真实稠密向量模型。

## 首轮候选

| 配置名 | 模型 | 维度 | 查询格式 |
| --- | --- | ---: | --- |
| `bge-small-zh-v1.5` | `BAAI/bge-small-zh-v1.5` | 512 | 使用模型卡推荐的中文检索指令 |
| `multilingual-e5-small` | `intfloat/multilingual-e5-small` | 384 | 查询加 `query:`，正文加 `passage:` |

模型代码固定了本次验证使用的 Hugging Face commit revision，避免上游同名模型更新后结果静默变化。

选择这两个较小模型，是为了先验证中文专用模型和多语言模型在本项目真实数据上的差异。首轮不引入 305M 参数的 `gte-multilingual-base`，避免模型规模差异掩盖数据与评测问题；如果两个小模型均不达标，再将其加入第二轮。

## 隔离运行

建议使用临时虚拟环境，避免修改正式项目依赖：

```bash
python3 -m venv /tmp/self-introduction-m1-venv
/tmp/self-introduction-m1-venv/bin/python -m pip install -r spikes/m1_embedding/requirements.txt
/tmp/self-introduction-m1-venv/bin/python -m spikes.m1_embedding.run --summary-only
```

首次运行会从 Hugging Face 下载模型。输出为 JSON，包含模型维度、加载耗时、语料编码耗时、查询延迟和文档/Chunk 两级指标。

## 注意

- 本机 CPU 延迟只用于候选之间的相对比较，不代表生产服务器延迟。
- 16 条用例规模很小，分数变化一条就是 6.25 个百分点。
- 生产选型还需结合部署地区、推理方式、成本和数据条款。
