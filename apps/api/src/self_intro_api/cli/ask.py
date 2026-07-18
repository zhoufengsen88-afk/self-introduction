import argparse
import asyncio
from pathlib import Path

from self_intro_api.rag.pipeline import create_rag_service
from self_intro_api.schemas.chat import ChatRequest


async def run(question: str, top_k: int, debug: bool) -> None:
    service = create_rag_service(Path("knowledge"))
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
    parser = argparse.ArgumentParser(description="Ask the local RAG pipeline a question")
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.question, args.top_k, args.debug))


if __name__ == "__main__":
    main()
