from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LlmEvaluationCase:
    case_id: str
    question: str
    history: Tuple[ChatMessage, ...]
    expected_document_ids: Tuple[str, ...]
    expected_chunk_ids: Tuple[str, ...]
    required_facts: Tuple[str, ...]
    forbidden_facts: Tuple[str, ...]
    should_refuse: bool
    refusal_reason: Optional[str]
    enabled: bool
    tags: Tuple[str, ...]


@dataclass(frozen=True)
class Evidence:
    chunk_id: str
    document_id: str
    document_title: str
    heading_path: Tuple[str, ...]
    content: str


@dataclass(frozen=True)
class Citation:
    chunk_id: str
    document_id: str
    document_title: str


@dataclass(frozen=True)
class LlmAnswer:
    answer: str
    citations: Tuple[Citation, ...]
    refused: bool = False
    refusal_reason: Optional[str] = None


@dataclass(frozen=True)
class StreamEvent:
    event: str
    data: Dict[str, object]
