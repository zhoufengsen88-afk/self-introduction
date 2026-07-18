.PHONY: dev dev-api dev-web install lint test migrate build ingest ingest-db ingest-db-e5 ask ask-db ask-db-e5 eval eval-semantic eval-m35-semantic eval-db eval-db-e5 eval-db-semantic eval-db-semantic-e5 eval-db-m35-semantic eval-db-m35-semantic-e5 eval-m5-llm

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
	ANSWER_GENERATOR=deterministic RAG_BACKEND=memory uv run pytest apps/api/tests
	pnpm test:web

migrate:
	uv run alembic upgrade head

build:
	pnpm build:web

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
