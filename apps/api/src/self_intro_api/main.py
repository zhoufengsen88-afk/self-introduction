from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from self_intro_api.core.config import get_settings
from self_intro_api.core.logging import configure_logging
from self_intro_api.core.observability import LoggingTraceSink
from self_intro_api.knowledge.scope import load_knowledge_scope
from self_intro_api.llm.factory import create_llm_provider
from self_intro_api.rag.pipeline import (
    DeterministicAnswerGenerator,
    LLMAnswerGenerator,
    RagService,
    create_rag_service,
)
from self_intro_api.schemas.chat import ChatRequest, ChatResponse
from self_intro_api.sse import encode_event_stream

configure_logging()
settings = get_settings()
trace_sink = LoggingTraceSink()


def create_application_answer_generator() -> DeterministicAnswerGenerator | LLMAnswerGenerator:
    answer_generator = settings.answer_generator.lower().strip()
    if answer_generator == "llm":
        return LLMAnswerGenerator(create_llm_provider(settings))
    if answer_generator == "deterministic":
        return DeterministicAnswerGenerator()
    raise ValueError(f"Unsupported ANSWER_GENERATOR: {settings.answer_generator}")


def create_application_rag_service() -> RagService:
    answer_generator = create_application_answer_generator()
    if settings.rag_backend == "pgvector":
        from self_intro_api.db.session import engine
        from self_intro_api.embedding.factory import create_embedding_provider
        from self_intro_api.knowledge.db_repository import PgVectorSearchBackend

        provider = create_embedding_provider(settings.embedding_provider)
        return RagService(
            PgVectorSearchBackend(engine, provider),
            answer_generator,
            trace_sink,
            load_knowledge_scope(Path("knowledge")),
        )
    return create_rag_service(Path("knowledge"), answer_generator, trace_sink)


rag_service = create_application_rag_service()

app = FastAPI(title="Agentic RAG Self Introduction Assistant API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-ID"],
)


@app.get("/healthz")
async def healthz() -> dict[str, str | bool]:
    return {"ok": True, "env": settings.app_env}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, response: Response) -> ChatResponse:
    trace_id = uuid4().hex
    response.headers["X-Trace-ID"] = trace_id
    return await rag_service.answer(request, trace_id=trace_id)


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    trace_id = uuid4().hex
    return StreamingResponse(
        encode_event_stream(rag_service.stream(request, trace_id=trace_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Trace-ID": trace_id,
        },
    )
