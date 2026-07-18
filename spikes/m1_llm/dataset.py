import json
from pathlib import Path
from typing import List

from .contracts import ChatMessage, LlmEvaluationCase


def load_llm_cases(path: Path, include_refusal_cases: bool = True) -> List[LlmEvaluationCase]:
    cases: List[LlmEvaluationCase] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc

            enabled = bool(record.get("enabled"))
            should_refuse = bool(record.get("should_refuse"))
            if not enabled and not (include_refusal_cases and should_refuse):
                continue

            cases.append(
                LlmEvaluationCase(
                    case_id=record["id"],
                    question=record["question"],
                    history=tuple(
                        ChatMessage(role=item["role"], content=item["content"])
                        for item in record.get("history", ())
                    ),
                    expected_document_ids=tuple(record.get("expected_document_ids", ())),
                    expected_chunk_ids=tuple(record.get("expected_chunk_ids", ())),
                    required_facts=tuple(record.get("required_facts", ())),
                    forbidden_facts=tuple(record.get("forbidden_facts", ())),
                    should_refuse=should_refuse,
                    refusal_reason=record.get("refusal_reason"),
                    enabled=enabled,
                    tags=tuple(record.get("tags", ())),
                )
            )
    return cases
