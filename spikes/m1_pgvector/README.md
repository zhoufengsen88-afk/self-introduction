# M1 第三阶段：PostgreSQL + pgvector

本实验复用 `m1_ingestion` 的 5 份公开文档、38 个 Chunk，以及 `m1_embedding` 临时选定的 `intfloat/multilingual-e5-small` 384 维向量。

## 验证目标

- 使用 PostgreSQL 表结构保存文档、Chunk 和 Embedding。
- 使用 `pgvector vector(384)` 和余弦距离 `<=>` 执行精确检索。
- 查询阶段强制过滤 `visibility = public` 且 `status = published`。
- 重复导入同一批语料后，行数不膨胀。
- 同一 Chunk 支持不同 Embedding revision，并在查询时按 revision 隔离。
- pgvector Top-5 排名与同一批内存向量计算结果一致。

## 临时本地环境

当前机器的默认 PostgreSQL 是 16，但 Homebrew `pgvector` bottle 提供 PostgreSQL 17/18 扩展文件。因此本 Spike 使用 PostgreSQL 18 的临时实例：

```bash
brew install postgresql@18 pgvector

PG18=/opt/homebrew/opt/postgresql@18/bin
PGDATA=/tmp/self-introduction-pgvector-pg18
"$PG18/initdb" -D "$PGDATA" --locale=en_US.UTF-8 -E UTF-8
"$PG18/pg_ctl" -D "$PGDATA" -l /tmp/self-introduction-pgvector-pg18.log -o "-p 55432 -k /tmp" start
"$PG18/createdb" -h /tmp -p 55432 self_intro_m1_spike
"$PG18/psql" -h /tmp -p 55432 -d self_intro_m1_spike -c "create extension if not exists vector;"
```

## 运行

建议继续使用 M1 临时虚拟环境：

```bash
/tmp/self-introduction-m1-venv/bin/python -m pip install -r spikes/m1_pgvector/requirements.txt
/tmp/self-introduction-m1-venv/bin/python -m spikes.m1_pgvector.run --reset
```

默认连接：

```text
postgresql:///self_intro_m1_spike?host=/tmp&port=55432
```

也可以通过 `PGVECTOR_DATABASE_URL` 或 `--database-url` 覆盖。

## 解释边界

本阶段只验证小语料下的正确性和工程约束，不验证生产并发、索引性能或 ANN 召回。当前只有 38 个 Chunk，精确检索比近似索引更适合做基线。
