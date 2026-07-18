import argparse
import json
from pathlib import Path

from .chunker import chunk_document
from .loader import load_published_documents
from .retrieval import BM25Index, evaluate, load_enabled_cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the M1 ingestion and lexical retrieval spike")
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets/mvp-v1.jsonl"))
    parser.add_argument("--max-chars", type=int, default=1200)
    args = parser.parse_args()

    documents = load_published_documents(args.knowledge)
    chunks = [chunk for document in documents for chunk in chunk_document(document, args.max_chars)]
    cases = load_enabled_cases(args.dataset)
    result = evaluate(BM25Index(chunks), cases)
    result["corpus"] = {
        "published_document_count": len(documents),
        "chunk_count": len(chunks),
        "max_chars": args.max_chars,
        "document_ids": [document.metadata.document_id for document in documents],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
