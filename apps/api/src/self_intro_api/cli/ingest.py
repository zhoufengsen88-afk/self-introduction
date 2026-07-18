import json
from pathlib import Path

from self_intro_api.knowledge.loader import load_public_corpus
from self_intro_api.knowledge.scope import build_knowledge_scope


def main() -> None:
    corpus = load_public_corpus(Path("knowledge"))
    scope = build_knowledge_scope(corpus.documents)
    payload = {
        "document_count": len(corpus.documents),
        "chunk_count": len(corpus.chunks),
        "document_ids": [document.metadata.document_id for document in corpus.documents],
        "projects": [
            {
                "project_id": project.project_id,
                "aliases": list(project.aliases),
                "document_ids": list(project.document_ids),
            }
            for project in scope.projects
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
