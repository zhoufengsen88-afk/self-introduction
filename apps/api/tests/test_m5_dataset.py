import json
from pathlib import Path
from typing import Any

from self_intro_api.knowledge.loader import load_public_corpus

DATASET_PATH = Path("evals/datasets/m5-agent-qa-v1.jsonl")
EXPECTED_ROUTES = {"knowledge_rag", "normal_chat", "out_of_scope", "restricted"}
REQUIRED_FIELDS = {
    "id",
    "enabled",
    "category",
    "question",
    "history",
    "expected_route",
    "citation_required",
    "expected_document_ids",
    "required_facts",
    "forbidden_facts",
    "should_refuse",
    "refusal_reason",
    "acceptance_criteria",
    "tags",
    "notes",
}


def _load_records() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_m5_dataset_has_expected_size_and_unique_ids() -> None:
    records = _load_records()

    assert len(records) == 45
    assert sum(record["enabled"] for record in records) == 45
    assert len({record["id"] for record in records}) == len(records)


def test_m5_dataset_records_follow_the_interview_eval_contract() -> None:
    for record in _load_records():
        assert REQUIRED_FIELDS <= record.keys(), record["id"]
        assert record["expected_route"] in EXPECTED_ROUTES, record["id"]
        assert record["acceptance_criteria"], record["id"]
        assert record["refusal_reason"] if record["should_refuse"] else True
        if record["citation_required"]:
            assert record["expected_document_ids"], record["id"]


def test_enabled_m5_evidence_references_exist_in_public_corpus() -> None:
    corpus = load_public_corpus(Path("knowledge"))
    document_ids = {document.metadata.document_id for document in corpus.documents}
    chunk_ids = {chunk.chunk_id for chunk in corpus.chunks}

    for record in _load_records():
        if not record["enabled"]:
            continue
        assert set(record["expected_document_ids"]) <= document_ids, record["id"]
        assert set(record.get("expected_chunk_ids", ())) <= chunk_ids, record["id"]
