import argparse
import asyncio
from pathlib import Path

from self_intro_api.db.session import engine
from self_intro_api.embedding.factory import HASHING_PROVIDER_NAME, create_embedding_provider
from self_intro_api.knowledge.db_repository import PgVectorSearchBackend
from self_intro_api.knowledge.loader import load_public_corpus
from self_intro_api.knowledge.scope import build_knowledge_scope, load_knowledge_scope
from self_intro_api.rag.pipeline import InMemorySearchBackend, RagService
from self_intro_api.schemas.chat import ChatRequest


async def run(
    question: str,
    top_k: int,
    debug: bool,
    fallback_to_memory: bool,
    embedding_provider: str,
) -> None:
    provider = create_embedding_provider(embedding_provider)
    try:
        service = RagService(
            PgVectorSearchBackend(engine, provider),
            knowledge_scope=load_knowledge_scope(Path("knowledge")),
        )
        response = await service.answer(ChatRequest(message=question), top_k=top_k)
    except Exception:
        if not fallback_to_memory:
            raise
        corpus = load_public_corpus(Path("knowledge"))
        service = RagService(
            InMemorySearchBackend(corpus),
            knowledge_scope=build_knowledge_scope(corpus.documents),
        )
        response = await service.answer(ChatRequest(message=question), top_k=top_k)

    if debug:
        print(response.model_dump_json(indent=2))
        return
    print(response.answer)
    if response.citations:
        print("\n引用：")
        for citation in response.citations:
            print(f"- {citation.document_title}: {citation.chunk_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the pgvector-backed RAG pipeline a question")
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--embedding-provider", default=HASHING_PROVIDER_NAME)
    parser.add_argument(
        "--fallback-to-memory",
        action="store_true",
        help="fall back to the in-memory M3 backend if the database is unavailable",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            args.question,
            args.top_k,
            args.debug,
            args.fallback_to_memory,
            args.embedding_provider,
        )
    )


if __name__ == "__main__":
    main()
