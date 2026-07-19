from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    heading_path: list[str] = Field(default_factory=list)
    score: float | None = None
    excerpt: str | None = None


class ChatDebugInfo(BaseModel):
    trace_id: str | None = None
    route: str
    intent: str | None = None
    project_id: str | None = None
    generation_strategy: str
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    citation_count: int = 0
    first_token_ms: float | None = None
    total_latency_ms: float | None = None
    model_name: str | None = None
    refused: bool = False
    refusal_reason: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    refused: bool = False
    refusal_reason: str | None = None
    debug: ChatDebugInfo | None = None
