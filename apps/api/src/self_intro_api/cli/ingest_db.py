import argparse
import json
from pathlib import Path

from self_intro_api.db.session import engine
from self_intro_api.embedding.factory import HASHING_PROVIDER_NAME, create_embedding_provider
from self_intro_api.knowledge.db_repository import ingest_corpus
from self_intro_api.knowledge.loader import load_public_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the public knowledge corpus into pgvector")
    parser.add_argument("--embedding-provider", default=HASHING_PROVIDER_NAME)
    args = parser.parse_args()

    corpus = load_public_corpus(Path("knowledge"))
    stats = ingest_corpus(engine, corpus, create_embedding_provider(args.embedding_provider))
    print(json.dumps(stats.__dict__, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
