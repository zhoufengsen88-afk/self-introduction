.PHONY: dev dev-api dev-web install lint test test-ci migrate build check-knowledge ingest ingest-db ingest-db-e5 ask ask-db ask-db-e5 eval eval-semantic eval-m35-semantic eval-db eval-db-e5 eval-db-semantic eval-db-semantic-e5 eval-db-m35-semantic eval-db-m35-semantic-e5 eval-m5-llm

QUESTION ?= 你在 Skillvar 中具体负责什么？
EMBEDDING_PROVIDER ?= hashing
SEMANTIC_DATASET ?= evals/datasets/m3.4-semantic-v1.jsonl
M5_DATASET ?= evals/datasets/m5-agent-qa-v1.jsonl
M5_OUTPUT ?= evals/results/m5-current-llm-memory.json
M5_BACKEND ?= memory

install:
	uv sync
	pnpm install

dev:
	@echo "Starting API on http://127.0.0.1:8000 and Web on http://127.0.0.1:3000"
	uv run uvicorn self_intro_api.main:app --app-dir apps/api/src --reload --port 8000 & pnpm dev:web

dev-api:
	uv run uvicorn self_intro_api.main:app --app-dir apps/api/src --reload --port 8000

dev-web:
	pnpm dev:web

lint:
	uv run ruff check apps/api/src apps/api/tests
	uv run mypy apps/api/src
	pnpm lint:web
	pnpm typecheck:web

test:
	LITE_LLMOPS_ENABLED=false ANSWER_GENERATOR=deterministic RAG_BACKEND=memory uv run pytest apps/api/tests
	pnpm test:web

test-ci:
	LITE_LLMOPS_ENABLED=false ANSWER_GENERATOR=deterministic RAG_BACKEND=memory uv run pytest \
		apps/api/tests/test_db_repository.py \
		apps/api/tests/test_embedding.py \
		apps/api/tests/test_embedding_factory.py \
		apps/api/tests/test_knowledge_scope.py \
		apps/api/tests/test_openai_compatible_provider.py \
		apps/api/tests/test_api.py::test_healthz \
		apps/api/tests/test_api.py::test_rag_restricted_content_refusal \
		apps/api/tests/test_api.py::test_out_of_scope_stream_has_no_citations \
		apps/api/tests/test_eval_llm.py::test_build_summary_keeps_human_review_separate_from_deterministic_checks \
		apps/api/tests/test_knowledge_rag.py::test_normal_chat_does_not_use_rag_citations \
		apps/api/tests/test_knowledge_rag.py::test_out_of_scope_question_does_not_use_rag_citations \
		apps/api/tests/test_knowledge_rag.py::test_candidate_scoped_question_without_evidence_refuses_cleanly \
		apps/api/tests/test_knowledge_rag.py::test_m53_router_regressions \
		apps/api/tests/test_knowledge_rag.py::test_m53_unknown_external_credential_refuses_without_citations \
		apps/api/tests/test_observability.py::test_composite_trace_sink_forwards_to_each_sink \
		apps/api/tests/test_observability.py::test_lite_llmops_trace_sink_reports_privacy_preserving_summary \
		apps/api/tests/test_observability.py::test_lite_llmops_trace_sink_reports_detailed_spans \
		apps/api/tests/test_observability.py::test_insufficient_evidence_trace_has_no_retrieved_chunks \
		apps/api/tests/test_observability.py::test_normal_chat_stream_records_first_token_and_route_policy \
		apps/api/tests/test_observability.py::test_trace_sink_failure_does_not_break_chat_response
	pnpm test:web

migrate:
	uv run alembic upgrade head

build:
	pnpm build:web

check-knowledge:
	uv run python -m self_intro_api.cli.check_knowledge --root knowledge

ingest:
	uv run python -m self_intro_api.cli.ingest

ingest-db:
	uv run python -m self_intro_api.cli.ingest_db --embedding-provider "$(EMBEDDING_PROVIDER)"

ingest-db-e5:
	uv run python -m self_intro_api.cli.ingest_db --embedding-provider multilingual-e5-small

ask:
	uv run python -m self_intro_api.cli.ask "$(QUESTION)" --debug

ask-db:
	uv run python -m self_intro_api.cli.ask_db "$(QUESTION)" --embedding-provider "$(EMBEDDING_PROVIDER)" --debug

ask-db-e5:
	uv run python -m self_intro_api.cli.ask_db "$(QUESTION)" --embedding-provider multilingual-e5-small --debug

eval:
	uv run python -m self_intro_api.cli.eval --output evals/results/m3-baseline.json

eval-semantic:
	uv run python -m self_intro_api.cli.eval --dataset $(SEMANTIC_DATASET) --output evals/results/m3.4-semantic-memory-baseline.json

eval-m35-semantic:
	uv run python -m self_intro_api.cli.eval --dataset $(SEMANTIC_DATASET) --output evals/results/m3.5-query-understanding-memory.json

eval-db:
	uv run python -m self_intro_api.cli.eval_db --embedding-provider "$(EMBEDDING_PROVIDER)" --output evals/results/m3.2-pgvector-baseline.json

eval-db-e5:
	uv run python -m self_intro_api.cli.eval_db --embedding-provider multilingual-e5-small --output evals/results/m3.3-e5-pgvector-baseline.json

eval-db-semantic:
	uv run python -m self_intro_api.cli.eval_db --dataset $(SEMANTIC_DATASET) --embedding-provider "$(EMBEDDING_PROVIDER)" --output evals/results/m3.4-semantic-hashing-pgvector.json

eval-db-semantic-e5:
	uv run python -m self_intro_api.cli.eval_db --dataset $(SEMANTIC_DATASET) --embedding-provider multilingual-e5-small --output evals/results/m3.4-semantic-e5-pgvector.json

eval-db-m35-semantic:
	uv run python -m self_intro_api.cli.eval_db --dataset $(SEMANTIC_DATASET) --embedding-provider "$(EMBEDDING_PROVIDER)" --output evals/results/m3.5-query-understanding-hashing-pgvector.json

eval-db-m35-semantic-e5:
	uv run python -m self_intro_api.cli.eval_db --dataset $(SEMANTIC_DATASET) --embedding-provider multilingual-e5-small --output evals/results/m3.5-query-understanding-e5-pgvector.json

eval-m5-llm:
	uv run python -m self_intro_api.cli.eval_llm --dataset $(M5_DATASET) --backend $(M5_BACKEND) --output $(M5_OUTPUT)
