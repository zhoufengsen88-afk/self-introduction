import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Protocol, cast
from uuid import uuid4

from self_intro_api.core.observability import ObservedSpan, RagTrace, TraceSink
from self_intro_api.knowledge.loader import load_public_corpus
from self_intro_api.knowledge.models import Corpus, SearchResult
from self_intro_api.knowledge.retrieval import BM25Retriever
from self_intro_api.knowledge.scope import KnowledgeScope, ProjectKnowledge, build_knowledge_scope
from self_intro_api.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMUsage,
    LLMUsageStreamingProvider,
)
from self_intro_api.rag.context import build_rag_messages
from self_intro_api.rag.perspective import wants_first_person_response
from self_intro_api.schemas.chat import ChatDebugInfo, ChatRequest, ChatResponse, Citation

RESTRICTED_PATTERNS = ("忽略之前的规则", "系统提示词", "数据库连接", "private 文档", "密钥")
LLM_PROVIDER_ERROR_MESSAGE = "大模型调用失败，请检查 LLM 配置或稍后重试。"
QueryRoute = Literal["knowledge_rag", "normal_chat", "out_of_scope", "restricted"]
LATIN_QUERY_ANCHOR_RE = re.compile(r"[a-z][a-z0-9_.+-]{2,}", re.IGNORECASE)
GENERIC_LATIN_ANCHORS = {"agent", "skill", "llm", "rag"}
GENERIC_EVIDENCE_MIN_SCORE = 8.0
PROFILE_INTENT_NAMES = {
    "identity",
    "education",
    "profile_introduction",
    "skills_profile",
    "career_direction",
    "personal_strengths",
    "job_fit",
}
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievalIntent:
    name: str = "generic"
    project_id: str | None = None
    allowed_document_ids: tuple[str, ...] = ()
    expanded_terms: tuple[str, ...] = ()
    document_boosts: Mapping[str, float] = field(default_factory=dict)
    heading_keywords: tuple[str, ...] = ()
    content_keywords: tuple[str, ...] = ()


class SearchBackend(Protocol):
    def search(self, query: str, intent: RetrievalIntent, top_k: int) -> list[SearchResult]:
        """Search evidence chunks for a rewritten query and inferred intent."""


class InMemorySearchBackend:
    def __init__(self, corpus: Corpus):
        self.corpus = corpus
        self.retriever = BM25Retriever(corpus.chunks)

    def search(self, query: str, intent: RetrievalIntent, top_k: int) -> list[SearchResult]:
        raw_results = self.retriever.search(query, limit=max(len(self.corpus.chunks), top_k))
        allowed_document_ids = set(intent.allowed_document_ids)
        reranked: list[SearchResult] = []
        for result in raw_results:
            if allowed_document_ids and result.chunk.document_id not in allowed_document_ids:
                continue
            score = rerank_score(result, intent)
            if score > 0:
                reranked.append(SearchResult(chunk=result.chunk, score=score))
        reranked.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
        return reranked[:top_k]


class AnswerGenerator(Protocol):
    async def generate_text(
        self,
        request: ChatRequest,
        intent: RetrievalIntent,
        results: Sequence[SearchResult],
    ) -> str:
        """Generate the final answer from retrieved evidence."""
        ...

    def stream_text(
        self,
        request: ChatRequest,
        intent: RetrievalIntent,
        results: Sequence[SearchResult],
    ) -> AsyncIterator[str]:
        """Stream the final answer from retrieved evidence."""
        ...


class DeterministicAnswerGenerator:
    async def generate_text(
        self,
        request: ChatRequest,
        intent: RetrievalIntent,
        results: Sequence[SearchResult],
    ) -> str:
        return _compose_answer(request.message, list(results), intent)

    async def stream_text(
        self,
        request: ChatRequest,
        intent: RetrievalIntent,
        results: Sequence[SearchResult],
    ) -> AsyncIterator[str]:
        answer = await self.generate_text(request, intent, results)
        for piece in _stream_chunks(answer):
            yield piece
            await asyncio.sleep(0)


@dataclass
class AnswerGenerationObservation:
    messages: list[LLMMessage] = field(default_factory=list)
    used_llm: bool = False
    used_policy_answer: bool = False
    model_name: str | None = None
    usage: LLMUsage = field(default_factory=LLMUsage)


class LLMAnswerGenerator:
    def __init__(
        self,
        provider: LLMProvider,
        prompt_cost_per_1k: float = 0.0,
        completion_cost_per_1k: float = 0.0,
    ):
        self.provider = provider
        self.prompt_cost_per_1k = Decimal(str(prompt_cost_per_1k))
        self.completion_cost_per_1k = Decimal(str(completion_cost_per_1k))

    async def generate_text(
        self,
        request: ChatRequest,
        intent: RetrievalIntent,
        results: Sequence[SearchResult],
    ) -> str:
        answer, _observation = await self.generate_text_with_observation(request, intent, results)
        return answer

    async def generate_text_with_observation(
        self,
        request: ChatRequest,
        intent: RetrievalIntent,
        results: Sequence[SearchResult],
    ) -> tuple[str, AnswerGenerationObservation]:
        observation = AnswerGenerationObservation()
        chunks = [
            chunk
            async for chunk in self.stream_text_with_observation(
                request,
                intent,
                results,
                observation,
            )
        ]
        answer = "".join(chunks).strip()
        if answer:
            return answer, observation
        fallback = "模型没有返回可用内容；当前无法基于公开知识库生成可靠回答。"
        if observation.used_llm and observation.usage.total_tokens == 0:
            observation.usage = _estimate_llm_usage(observation.messages, fallback)
        return fallback, observation

    async def stream_text(
        self,
        request: ChatRequest,
        intent: RetrievalIntent,
        results: Sequence[SearchResult],
    ) -> AsyncIterator[str]:
        observation = AnswerGenerationObservation()
        async for piece in self.stream_text_with_observation(
            request,
            intent,
            results,
            observation,
        ):
            yield piece

    async def stream_text_with_observation(
        self,
        request: ChatRequest,
        intent: RetrievalIntent,
        results: Sequence[SearchResult],
        observation: AnswerGenerationObservation,
    ) -> AsyncIterator[str]:
        policy_answer = _grounded_policy_answer(intent, request.message)
        if policy_answer:
            observation.used_policy_answer = True
            for piece in _stream_chunks(policy_answer):
                yield piece
                await asyncio.sleep(0)
            return

        emitted = False
        emitted_parts: list[str] = []
        messages = build_rag_messages(request, intent.name, results)
        observation.messages = list(messages)
        observation.used_llm = True
        observation.model_name = self._provider_model_name()
        usage_stream = self._usage_stream()
        if usage_stream is not None:
            async for chunk in usage_stream.stream_chat_with_usage(messages):
                if chunk.usage is not None:
                    observation.usage = chunk.usage
                if chunk.content:
                    emitted = True
                    emitted_parts.append(chunk.content)
                    yield chunk.content
        else:
            async for piece in self.provider.stream_chat(messages):
                if piece:
                    emitted = True
                    emitted_parts.append(piece)
                    yield piece
        if not emitted:
            fallback = "模型没有返回可用内容；当前无法基于公开知识库生成可靠回答。"
            emitted_parts.append(fallback)
            yield fallback
        if observation.usage.total_tokens == 0:
            observation.usage = _estimate_llm_usage(
                messages,
                "".join(emitted_parts),
            )

    def calculate_cost(self, usage: LLMUsage) -> Decimal:
        prompt_cost = (Decimal(usage.prompt_tokens) / Decimal("1000")) * self.prompt_cost_per_1k
        completion_cost = (
            Decimal(usage.completion_tokens) / Decimal("1000")
        ) * self.completion_cost_per_1k
        return (prompt_cost + completion_cost).quantize(Decimal("0.000001"))

    def _provider_model_name(self) -> str | None:
        if hasattr(self.provider, "model"):
            value = cast(Any, self.provider).model
            if isinstance(value, str) and value:
                return value
        return None

    def _usage_stream(self) -> LLMUsageStreamingProvider | None:
        if hasattr(self.provider, "stream_chat_with_usage"):
            return cast(LLMUsageStreamingProvider, self.provider)
        return None


def _grounded_policy_answer(intent: RetrievalIntent, question: str) -> str | None:
    if intent.name != "ai_assisted_development":
        return None
    if intent.project_id == "self-introduction-agentic-rag":
        if wants_first_person_response(question):
            return (
                "在 Agentic RAG 个人经历助手项目中，我使用 Codex 辅助代码实现、"
                "文档整理、测试补充、失败定位和迭代建议。"
                "我不会把 AI 辅助产出包装成完全纯手写；我负责提出项目目标、"
                "确认公开边界、审核知识内容、运行验证，并需要能够解释系统的数据流、"
                "关键实现、技术取舍和当前限制。"
            )
        return (
            "在 Agentic RAG 个人经历助手项目中，周逢森使用 Codex 辅助代码实现、"
            "文档整理、测试补充、失败定位和迭代建议。"
            "他不会把 AI 辅助产出包装成完全纯手写；周逢森负责提出项目目标、"
            "确认公开边界、审核知识内容、运行验证，并需要能够解释系统的数据流、"
            "关键实现、技术取舍和当前限制。"
        )
    if wants_first_person_response(question):
        return (
            "在 Skillvar 开发中，我使用 Codex 和 GLM-5.2 辅助编程、代码理解和实现迭代。"
            "我不会把 AI 生成代码直接等同于完成交付；我负责相关模块的理解、集成、调试、"
            "测试、部署和验证，并需要能够说明模块的数据流、关键实现与取舍。"
            "当前公开资料没有证明所有架构设计、技术选型或产品决策都由我独立完成，"
            "因此我不会作这种夸大表述。我的能力主要体现在能把 AI 辅助产出转化为可理解、"
            "可调试、经过测试并部署用于内部测试的工程模块。"
        )
    return (
        "在 Skillvar 开发中，周逢森使用 Codex 和 GLM-5.2 辅助编程、代码理解和实现迭代。"
        "他不会把 AI 生成代码直接等同于完成交付；他负责相关模块的理解、集成、调试、"
        "测试、部署和验证，并需要能够说明模块的数据流、关键实现与取舍。"
        "当前公开资料没有证明所有架构设计、技术选型或产品决策都由周逢森独立完成，"
        "因此不能作这种夸大表述。他的能力主要体现在能把 AI 辅助产出转化为可理解、"
        "可调试、经过测试并部署用于内部测试的工程模块。"
    )


@dataclass(frozen=True)
class PreparedRagAnswer:
    intent: RetrievalIntent
    results: list[SearchResult]
    citations: list[Citation]


class RagService:
    def __init__(
        self,
        search_backend: SearchBackend,
        answer_generator: AnswerGenerator | None = None,
        trace_sink: TraceSink | None = None,
        knowledge_scope: KnowledgeScope | None = None,
    ):
        self.search_backend = search_backend
        self.answer_generator = answer_generator or DeterministicAnswerGenerator()
        self.trace_sink = trace_sink
        self.knowledge_scope = knowledge_scope or KnowledgeScope()

    def retrieve(self, question: str, top_k: int = 5) -> list[SearchResult]:
        intent = _infer_intent(question, "")
        retrieval_query = _build_retrieval_query(question, "", intent)
        return self.search_backend.search(retrieval_query, intent, top_k)

    def route(self, request: ChatRequest) -> QueryRoute:
        """Return the observable top-level route selected for a request."""
        return _route_query(request.message, _history_text(request), self.knowledge_scope)

    def intent(self, request: ChatRequest) -> RetrievalIntent:
        """Return the observable retrieval intent selected for a knowledge request."""
        current_project = self.knowledge_scope.match_project(request.message)
        should_use_history = self._should_use_history_for_current_question(request)
        history_text = _history_text(request) if should_use_history else ""
        project = current_project
        if project is None and should_use_history:
            project = self.knowledge_scope.match_project(history_text)
        intent = _infer_intent(request.message, history_text, project)
        return _scope_intent_to_project(intent, project)

    def _should_use_history_for_current_question(self, request: ChatRequest) -> bool:
        normalized = _normalize_query(request.message)
        has_current_project = self.knowledge_scope.match_project(request.message) is not None
        return not has_current_project and _is_contextual_followup(request.message, normalized)

    def _request_for_generation(self, request: ChatRequest) -> ChatRequest:
        if self._should_use_history_for_current_question(request):
            return request
        return request.model_copy(update={"history": []})

    async def answer(
        self,
        request: ChatRequest,
        top_k: int = 8,
        trace_id: str | None = None,
    ) -> ChatResponse:
        started = perf_counter()
        active_trace_id = trace_id or uuid4().hex
        parent_span_id = _span_id(active_trace_id, "agent-root")
        spans: list[ObservedSpan] = []

        route_started = perf_counter()
        route = self.route(request)
        spans.append(
            _observed_span(
                active_trace_id,
                "agent-route",
                "agent",
                "Agent Step：路由判断",
                input=_json_payload(
                    {
                        "message": request.message,
                        "history": _history_payload(request),
                    }
                ),
                output=route,
                latency_ms=_elapsed_ms(route_started),
                metadata={"route": route},
                parent_span_id=parent_span_id,
            )
        )

        intent: RetrievalIntent | None = None
        if route == "knowledge_rag":
            intent_started = perf_counter()
            intent = self.intent(request)
            spans.append(
                _observed_span(
                    active_trace_id,
                    "agent-intent",
                    "agent",
                    "Agent Step：意图识别",
                    input=request.message,
                    output=_json_payload(_intent_payload(intent)),
                    latency_ms=_elapsed_ms(intent_started),
                    metadata={"intent": intent.name, "project_id": intent.project_id},
                    parent_span_id=parent_span_id,
                )
            )
        try:
            prepared = self._prepare_answer(
                request,
                top_k,
                route=route,
                intent=intent,
                trace_id=active_trace_id,
                parent_span_id=parent_span_id,
                spans=spans,
            )
        except Exception as exc:
            spans.append(
                _observed_span(
                    active_trace_id,
                    "agent-error",
                    "agent",
                    "Agent Step：RAG 管道异常",
                    input=request.message,
                    output=None,
                    status="error",
                    latency_ms=_elapsed_ms(started),
                    metadata={"route": route, "intent": intent.name if intent else None},
                    parent_span_id=parent_span_id,
                    error_message=str(exc),
                )
            )
            self._record_trace(
                request=request,
                trace_id=active_trace_id,
                route=route,
                intent=intent,
                results=(),
                response=None,
                started=started,
                streaming=False,
                first_token_ms=None,
                error_code="rag_pipeline_error",
                spans=spans,
                parent_span_id=parent_span_id,
            )
            raise
        if isinstance(prepared, ChatResponse):
            prepared = prepared.model_copy(
                update={
                    "debug": self._debug_info(
                        trace_id=active_trace_id,
                        route=route,
                        intent=intent,
                        results=(),
                        response=prepared,
                        started=started,
                        first_token_ms=None,
                        spans=spans,
                    )
                }
            )
            self._record_trace(
                request=request,
                trace_id=active_trace_id,
                route=route,
                intent=intent,
                results=(),
                response=prepared,
                started=started,
                streaming=False,
                first_token_ms=None,
                error_code=None,
                spans=spans,
                parent_span_id=parent_span_id,
            )
            return prepared

        generation_observation = AnswerGenerationObservation()
        generation_started = perf_counter()
        generation_request = self._request_for_generation(request)
        try:
            if isinstance(self.answer_generator, LLMAnswerGenerator):
                answer, generation_observation = (
                    await self.answer_generator.generate_text_with_observation(
                        request=generation_request,
                        intent=prepared.intent,
                        results=prepared.results,
                    )
                )
            else:
                answer = await self.answer_generator.generate_text(
                    request=generation_request,
                    intent=prepared.intent,
                    results=prepared.results,
                )
        except Exception as exc:
            response = ChatResponse(
                answer=LLM_PROVIDER_ERROR_MESSAGE,
                citations=[],
                refused=True,
                refusal_reason="llm_provider_error",
            )
            spans.extend(
                self._answer_generation_spans(
                    trace_id=active_trace_id,
                    parent_span_id=parent_span_id,
                    request=request,
                    intent=prepared.intent,
                    results=prepared.results,
                    answer=response.answer,
                    observation=generation_observation,
                    generation_latency_ms=_elapsed_ms(generation_started),
                    status="error",
                    error_message=str(exc),
                )
            )
            response = response.model_copy(
                update={
                    "debug": self._debug_info(
                        trace_id=active_trace_id,
                        route=route,
                        intent=prepared.intent,
                        results=prepared.results,
                        response=response,
                        started=started,
                        first_token_ms=None,
                        spans=spans,
                        error_code="llm_provider_error",
                    )
                }
            )
            self._record_trace(
                request=request,
                trace_id=active_trace_id,
                route=route,
                intent=prepared.intent,
                results=prepared.results,
                response=response,
                started=started,
                streaming=False,
                first_token_ms=None,
                error_code="llm_provider_error",
                spans=spans,
                parent_span_id=parent_span_id,
            )
            return response
        response = ChatResponse(answer=answer, citations=prepared.citations)
        spans.extend(
            self._answer_generation_spans(
                trace_id=active_trace_id,
                parent_span_id=parent_span_id,
                request=request,
                intent=prepared.intent,
                results=prepared.results,
                answer=answer,
                observation=generation_observation,
                generation_latency_ms=_elapsed_ms(generation_started),
            )
        )
        response = response.model_copy(
            update={
                "debug": self._debug_info(
                    trace_id=active_trace_id,
                    route=route,
                    intent=prepared.intent,
                    results=prepared.results,
                    response=response,
                    started=started,
                    first_token_ms=None,
                    spans=spans,
                )
            }
        )
        self._record_trace(
            request=request,
            trace_id=active_trace_id,
            route=route,
            intent=prepared.intent,
            results=prepared.results,
            response=response,
            started=started,
            streaming=False,
            first_token_ms=None,
            error_code=None,
            spans=spans,
            parent_span_id=parent_span_id,
        )
        return response

    async def stream(
        self,
        request: ChatRequest,
        top_k: int = 8,
        trace_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        started = perf_counter()
        active_trace_id = trace_id or uuid4().hex
        parent_span_id = _span_id(active_trace_id, "agent-root")
        spans: list[ObservedSpan] = []

        route_started = perf_counter()
        route = self.route(request)
        spans.append(
            _observed_span(
                active_trace_id,
                "agent-route",
                "agent",
                "Agent Step：路由判断",
                input=_json_payload(
                    {
                        "message": request.message,
                        "history": _history_payload(request),
                    }
                ),
                output=route,
                latency_ms=_elapsed_ms(route_started),
                metadata={"route": route},
                parent_span_id=parent_span_id,
            )
        )

        intent: RetrievalIntent | None = None
        if route == "knowledge_rag":
            intent_started = perf_counter()
            intent = self.intent(request)
            spans.append(
                _observed_span(
                    active_trace_id,
                    "agent-intent",
                    "agent",
                    "Agent Step：意图识别",
                    input=request.message,
                    output=_json_payload(_intent_payload(intent)),
                    latency_ms=_elapsed_ms(intent_started),
                    metadata={"intent": intent.name, "project_id": intent.project_id},
                    parent_span_id=parent_span_id,
                )
            )
        first_token_ms: float | None = None
        try:
            prepared = self._prepare_answer(
                request,
                top_k,
                route=route,
                intent=intent,
                trace_id=active_trace_id,
                parent_span_id=parent_span_id,
                spans=spans,
            )
        except Exception as exc:
            spans.append(
                _observed_span(
                    active_trace_id,
                    "agent-error",
                    "agent",
                    "Agent Step：RAG 管道异常",
                    input=request.message,
                    output=None,
                    status="error",
                    latency_ms=_elapsed_ms(started),
                    metadata={"route": route, "intent": intent.name if intent else None},
                    parent_span_id=parent_span_id,
                    error_message=str(exc),
                )
            )
            self._record_trace(
                request=request,
                trace_id=active_trace_id,
                route=route,
                intent=intent,
                results=(),
                response=None,
                started=started,
                streaming=True,
                first_token_ms=None,
                error_code="rag_pipeline_error",
                spans=spans,
                parent_span_id=parent_span_id,
            )
            raise
        if isinstance(prepared, ChatResponse):
            response = prepared
            for piece in _stream_chunks(response.answer):
                if first_token_ms is None:
                    first_token_ms = (perf_counter() - started) * 1000
                yield {"event": "delta", "data": {"content": piece}}
                await asyncio.sleep(0)
            response = response.model_copy(
                update={
                    "debug": self._debug_info(
                        trace_id=active_trace_id,
                        route=route,
                        intent=intent,
                        results=(),
                        response=response,
                        started=started,
                        first_token_ms=first_token_ms,
                        spans=spans,
                    )
                }
            )
            yield _done_event(
                response.citations,
                response.refused,
                response.refusal_reason,
                response.debug,
            )
            self._record_trace(
                request=request,
                trace_id=active_trace_id,
                route=route,
                intent=intent,
                results=(),
                response=response,
                started=started,
                streaming=True,
                first_token_ms=first_token_ms,
                error_code=None,
                spans=spans,
                parent_span_id=parent_span_id,
            )
            return

        answer_parts: list[str] = []
        generation_observation = AnswerGenerationObservation()
        generation_started = perf_counter()
        generation_request = self._request_for_generation(request)
        try:
            if isinstance(self.answer_generator, LLMAnswerGenerator):
                stream = self.answer_generator.stream_text_with_observation(
                    request=generation_request,
                    intent=prepared.intent,
                    results=prepared.results,
                    observation=generation_observation,
                )
            else:
                stream = self.answer_generator.stream_text(
                    request=generation_request,
                    intent=prepared.intent,
                    results=prepared.results,
                )
            async for piece in stream:
                if first_token_ms is None:
                    first_token_ms = (perf_counter() - started) * 1000
                answer_parts.append(piece)
                yield {"event": "delta", "data": {"content": piece}}
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            spans.extend(
                self._answer_generation_spans(
                    trace_id=active_trace_id,
                    parent_span_id=parent_span_id,
                    request=request,
                    intent=prepared.intent,
                    results=prepared.results,
                    answer="".join(answer_parts),
                    observation=generation_observation,
                    generation_latency_ms=_elapsed_ms(generation_started),
                    status="error",
                    error_message="client_cancelled",
                )
            )
            self._record_trace(
                request=request,
                trace_id=active_trace_id,
                route=route,
                intent=intent,
                results=prepared.results,
                response=None,
                started=started,
                streaming=True,
                first_token_ms=first_token_ms,
                error_code="client_cancelled",
                spans=spans,
                parent_span_id=parent_span_id,
            )
            raise
        except Exception as exc:
            yield _error_event(LLM_PROVIDER_ERROR_MESSAGE, code="llm_provider_error")
            spans.extend(
                self._answer_generation_spans(
                    trace_id=active_trace_id,
                    parent_span_id=parent_span_id,
                    request=request,
                    intent=prepared.intent,
                    results=prepared.results,
                    answer="".join(answer_parts) or LLM_PROVIDER_ERROR_MESSAGE,
                    observation=generation_observation,
                    generation_latency_ms=_elapsed_ms(generation_started),
                    status="error",
                    error_message=str(exc),
                )
            )
            self._record_trace(
                request=request,
                trace_id=active_trace_id,
                route=route,
                intent=intent,
                results=prepared.results,
                response=None,
                started=started,
                streaming=True,
                first_token_ms=first_token_ms,
                error_code="llm_provider_error",
                spans=spans,
                parent_span_id=parent_span_id,
            )
            return

        answer_text = "".join(answer_parts).strip()
        response = ChatResponse(answer=answer_text, citations=prepared.citations)
        spans.extend(
            self._answer_generation_spans(
                trace_id=active_trace_id,
                parent_span_id=parent_span_id,
                request=request,
                intent=prepared.intent,
                results=prepared.results,
                answer=answer_text,
                observation=generation_observation,
                generation_latency_ms=_elapsed_ms(generation_started),
            )
        )
        response = response.model_copy(
            update={
                "debug": self._debug_info(
                    trace_id=active_trace_id,
                    route=route,
                    intent=prepared.intent,
                    results=prepared.results,
                    response=response,
                    started=started,
                    first_token_ms=first_token_ms,
                    spans=spans,
                )
            }
        )
        yield _done_event(
            response.citations,
            refused=False,
            refusal_reason=None,
            debug=response.debug,
        )
        self._record_trace(
            request=request,
            trace_id=active_trace_id,
            route=route,
            intent=prepared.intent,
            results=prepared.results,
            response=response,
            started=started,
            streaming=True,
            first_token_ms=first_token_ms,
            error_code=None,
            spans=spans,
            parent_span_id=parent_span_id,
        )

    def _record_trace(
        self,
        *,
        request: ChatRequest,
        trace_id: str,
        route: QueryRoute,
        intent: RetrievalIntent | None,
        results: Sequence[SearchResult],
        response: ChatResponse | None,
        started: float,
        streaming: bool,
        first_token_ms: float | None,
        error_code: str | None,
        spans: Sequence[ObservedSpan] = (),
        parent_span_id: str | None = None,
    ) -> None:
        if self.trace_sink is None:
            return
        try:
            total_latency_ms = round((perf_counter() - started) * 1000, 2)
            all_spans = self._complete_spans(
                trace_id=trace_id,
                parent_span_id=parent_span_id or _span_id(trace_id, "agent-root"),
                request=request,
                response=response,
                spans=spans,
                route=route,
                intent=intent,
                total_latency_ms=total_latency_ms,
                error_code=error_code,
            )
            prompt_tokens = sum(span.prompt_tokens for span in all_spans)
            completion_tokens = sum(span.completion_tokens for span in all_spans)
            total_tokens = sum(span.total_tokens for span in all_spans)
            total_cost = sum((span.cost for span in all_spans), Decimal("0"))
            self.trace_sink.record(
                RagTrace(
                    trace_id=trace_id,
                    route=route,
                    intent=intent.name if intent else None,
                    retrieved_chunk_ids=tuple(result.chunk.chunk_id for result in results),
                    generation_strategy=self._generation_strategy(route, intent, response),
                    refused=response.refused if response else False,
                    refusal_reason=response.refusal_reason if response else None,
                    streaming=streaming,
                    first_token_ms=(
                        round(first_token_ms, 2) if first_token_ms is not None else None
                    ),
                    total_latency_ms=total_latency_ms,
                    error_code=error_code,
                    user_input=request.message,
                    final_output=response.answer if response else None,
                    model_name=self._active_model_name(all_spans),
                    spans=tuple(all_spans),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    total_cost=total_cost,
                )
            )
        except Exception:
            LOGGER.exception("rag_trace_record_failed")

    def _debug_info(
        self,
        *,
        trace_id: str,
        route: QueryRoute,
        intent: RetrievalIntent | None,
        results: Sequence[SearchResult],
        response: ChatResponse,
        started: float,
        first_token_ms: float | None,
        spans: Sequence[ObservedSpan] = (),
        error_code: str | None = None,
    ) -> ChatDebugInfo:
        return ChatDebugInfo(
            trace_id=trace_id,
            route=route,
            intent=intent.name if intent else None,
            project_id=intent.project_id if intent else None,
            generation_strategy=self._generation_strategy(route, intent, response),
            retrieved_chunk_ids=[result.chunk.chunk_id for result in results],
            citation_count=len(response.citations),
            first_token_ms=round(first_token_ms, 2) if first_token_ms is not None else None,
            total_latency_ms=round((perf_counter() - started) * 1000, 2),
            model_name=self._active_model_name(spans),
            refused=response.refused,
            refusal_reason=response.refusal_reason or error_code,
        )

    def _complete_spans(
        self,
        *,
        trace_id: str,
        parent_span_id: str,
        request: ChatRequest,
        response: ChatResponse | None,
        spans: Sequence[ObservedSpan],
        route: QueryRoute,
        intent: RetrievalIntent | None,
        total_latency_ms: float,
        error_code: str | None,
    ) -> list[ObservedSpan]:
        status = "error" if error_code else "success"
        root_span = _observed_span(
            trace_id,
            "agent-root",
            "agent",
            "Agent 请求处理",
            input=_json_payload(
                {
                    "message": request.message,
                    "history": _history_payload(request),
                    "streaming": response is None and error_code == "client_cancelled",
                }
            ),
            output=response.answer if response else None,
            status=status,
            latency_ms=total_latency_ms,
            metadata={
                "route": route,
                "intent": intent.name if intent else None,
                "refused": response.refused if response else False,
                "refusal_reason": response.refusal_reason if response else None,
                "error_code": error_code,
            },
        )
        final_span = _observed_span(
            trace_id,
            "agent-final",
            "agent",
            "Agent Step：返回最终回答",
            input=request.message,
            output=response.answer if response else None,
            status=status,
            latency_ms=0,
            metadata={
                "citations": [citation.model_dump() for citation in response.citations]
                if response
                else [],
                "refused": response.refused if response else False,
                "refusal_reason": response.refusal_reason if response else None,
            },
            parent_span_id=parent_span_id,
            error_message=error_code,
        )
        return [root_span, *spans, final_span]

    def _answer_generation_spans(
        self,
        *,
        trace_id: str,
        parent_span_id: str,
        request: ChatRequest,
        intent: RetrievalIntent,
        results: Sequence[SearchResult],
        answer: str,
        observation: AnswerGenerationObservation,
        generation_latency_ms: float,
        status: str = "success",
        error_message: str | None = None,
    ) -> list[ObservedSpan]:
        if observation.used_policy_answer:
            return [
                _observed_span(
                    trace_id,
                    "agent-grounded-policy",
                    "agent",
                    "Agent Step：边界策略回答",
                    input=request.message,
                    output=answer,
                    status=status,
                    latency_ms=generation_latency_ms,
                    metadata={"intent": intent.name},
                    parent_span_id=parent_span_id,
                    error_message=error_message,
                )
            ]

        if observation.used_llm:
            messages_payload = _messages_payload(observation.messages)
            prompt_output = _json_payload(messages_payload)
            usage = observation.usage
            cost = self.answer_generator.calculate_cost(usage) if isinstance(
                self.answer_generator,
                LLMAnswerGenerator,
            ) else Decimal("0")
            prompt_span_id = _span_id(trace_id, "prompt")
            return [
                _observed_span(
                    trace_id,
                    "prompt",
                    "prompt",
                    "构造 RAG Prompt",
                    input=_json_payload(
                        {
                            "message": request.message,
                            "intent": intent.name,
                            "retrieved_chunk_ids": [
                                result.chunk.chunk_id for result in results
                            ],
                        }
                    ),
                    output=prompt_output,
                    status=status,
                    latency_ms=0,
                    metadata={
                        "message_count": len(observation.messages),
                        "source_chunk_count": len(results),
                    },
                    parent_span_id=parent_span_id,
                    error_message=error_message if status == "error" else None,
                ),
                _observed_span(
                    trace_id,
                    "llm",
                    "llm",
                    "调用大模型生成回答",
                    input=prompt_output,
                    output=answer,
                    status=status,
                    latency_ms=generation_latency_ms,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                    cost=cost,
                    metadata={
                        "model_name": observation.model_name,
                        "usage_estimated": usage.estimated,
                        "prompt_span_id": prompt_span_id,
                    },
                    parent_span_id=parent_span_id,
                    error_message=error_message,
                ),
            ]

        return [
            _observed_span(
                trace_id,
                "agent-template-generation",
                "agent",
                "Agent Step：模板生成回答",
                input=_json_payload(
                    {
                        "message": request.message,
                        "intent": intent.name,
                        "retrieved_chunk_ids": [result.chunk.chunk_id for result in results],
                    }
                ),
                output=answer,
                status=status,
                latency_ms=generation_latency_ms,
                metadata={"generation_strategy": "deterministic"},
                parent_span_id=parent_span_id,
                error_message=error_message,
            )
        ]

    def _active_model_name(self, spans: Sequence[ObservedSpan]) -> str | None:
        for span in spans:
            value = span.metadata.get("model_name")
            if isinstance(value, str) and value:
                return value
        return None

    def _generation_strategy(
        self,
        route: QueryRoute,
        intent: RetrievalIntent | None,
        response: ChatResponse | None,
    ) -> str:
        if route != "knowledge_rag":
            return "route_policy"
        if response and response.refusal_reason == "insufficient_evidence":
            return "evidence_policy"
        if isinstance(self.answer_generator, LLMAnswerGenerator):
            if intent and intent.name == "ai_assisted_development":
                return "grounded_policy"
            return "llm"
        if isinstance(self.answer_generator, DeterministicAnswerGenerator):
            return "deterministic"
        return type(self.answer_generator).__name__

    def _prepare_answer(
        self,
        request: ChatRequest,
        top_k: int,
        *,
        route: QueryRoute | None = None,
        intent: RetrievalIntent | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        spans: list[ObservedSpan] | None = None,
    ) -> PreparedRagAnswer | ChatResponse:
        history_text = (
            _history_text(request) if self._should_use_history_for_current_question(request) else ""
        )
        active_route = route or self.route(request)
        active_trace_id = trace_id or uuid4().hex
        active_parent_span_id = parent_span_id or _span_id(active_trace_id, "agent-root")

        if active_route == "restricted":
            response = ChatResponse(
                answer="这个问题涉及隐藏资料、系统规则或非公开内容，我不能回答。",
                citations=[],
                refused=True,
                refusal_reason="restricted_content",
            )
            _append_policy_span(
                spans,
                active_trace_id,
                active_parent_span_id,
                "Agent Step：安全策略拒答",
                request.message,
                response,
                active_route,
            )
            return response
        if active_route == "normal_chat":
            response = ChatResponse(answer=_normal_chat_answer(request.message), citations=[])
            _append_policy_span(
                spans,
                active_trace_id,
                active_parent_span_id,
                "Agent Step：普通聊天策略回答",
                request.message,
                response,
                active_route,
            )
            return response
        if active_route == "out_of_scope":
            response = ChatResponse(answer=_out_of_scope_answer(request.message), citations=[])
            _append_policy_span(
                spans,
                active_trace_id,
                active_parent_span_id,
                "Agent Step：范围外问题回答",
                request.message,
                response,
                active_route,
            )
            return response

        active_intent = intent or self.intent(request)
        if active_intent.name == "generic" and _is_uncovered_personal_fact_question(
            request.message
        ):
            response = ChatResponse(
                answer="当前公开知识库里没有足够证据回答这个问题，我不能凭空补充。",
                citations=[],
                refused=True,
                refusal_reason="insufficient_evidence",
            )
            _append_policy_span(
                spans,
                active_trace_id,
                active_parent_span_id,
                "Agent Step：公开证据边界拒答",
                request.message,
                response,
                active_route,
            )
            return response

        retrieval_query = _build_retrieval_query(request.message, history_text, active_intent)
        retrieval_started = perf_counter()
        try:
            results = self.search_backend.search(retrieval_query, active_intent, top_k)
        except Exception as exc:
            if spans is not None:
                spans.append(
                    _observed_span(
                        active_trace_id,
                        "tool-retrieval",
                        "tool",
                        "调用知识库检索工具",
                        input=retrieval_query,
                        output=None,
                        status="error",
                        latency_ms=_elapsed_ms(retrieval_started),
                        metadata={
                            "top_k": top_k,
                            "intent": active_intent.name,
                            "project_id": active_intent.project_id,
                        },
                        parent_span_id=active_parent_span_id,
                        error_message=str(exc),
                    )
                )
            raise

        if spans is not None:
            spans.append(
                _observed_span(
                    active_trace_id,
                    "tool-retrieval",
                    "tool",
                    "调用知识库检索工具",
                    input=retrieval_query,
                    output=_json_payload(_results_payload(results)),
                    latency_ms=_elapsed_ms(retrieval_started),
                    metadata={
                        "top_k": top_k,
                        "intent": active_intent.name,
                        "project_id": active_intent.project_id,
                        "result_count": len(results),
                    },
                    parent_span_id=active_parent_span_id,
                )
            )

        if not results or not _has_query_anchor_evidence(request.message, active_intent, results):
            response = ChatResponse(
                answer="当前公开知识库里没有足够证据回答这个问题，我不能凭空补充。",
                citations=[],
                refused=True,
                refusal_reason="insufficient_evidence",
            )
            _append_policy_span(
                spans,
                active_trace_id,
                active_parent_span_id,
                "Agent Step：证据充足性检查",
                _json_payload(
                    {
                        "message": request.message,
                        "retrieval_query": retrieval_query,
                        "result_count": len(results),
                    }
                ),
                response,
                active_route,
            )
            return response

        results = _select_evidence(results, limit=min(top_k, 6))

        citations = _build_citations(results)
        if spans is not None:
            spans.append(
                _observed_span(
                    active_trace_id,
                    "rag-evidence",
                    "rag",
                    "整理 RAG 证据",
                    input=_json_payload(
                        {
                            "retrieval_query": retrieval_query,
                            "selected_chunk_ids": [result.chunk.chunk_id for result in results],
                        }
                    ),
                    output=_json_payload([citation.model_dump() for citation in citations]),
                    latency_ms=0,
                    metadata={
                        "selected_count": len(results),
                        "document_ids": sorted(
                            {result.chunk.document_id for result in results}
                        ),
                    },
                    parent_span_id=active_parent_span_id,
                )
            )
        return PreparedRagAnswer(intent=active_intent, results=results, citations=citations)

    @staticmethod
    def _is_restricted(message: str) -> bool:
        return any(pattern in message for pattern in RESTRICTED_PATTERNS)


def create_rag_service(
    knowledge_path: Path,
    answer_generator: AnswerGenerator | None = None,
    trace_sink: TraceSink | None = None,
) -> RagService:
    corpus = load_public_corpus(knowledge_path)
    return RagService(
        InMemorySearchBackend(corpus),
        answer_generator,
        trace_sink,
        build_knowledge_scope(corpus.documents),
    )


def _append_policy_span(
    spans: list[ObservedSpan] | None,
    trace_id: str,
    parent_span_id: str,
    name: str,
    input_value: str,
    response: ChatResponse,
    route: QueryRoute,
) -> None:
    if spans is None:
        return
    spans.append(
        _observed_span(
            trace_id,
            f"agent-policy-{route}",
            "agent",
            name,
            input=input_value,
            output=response.answer,
            status="error" if response.refused else "success",
            latency_ms=0,
            metadata={
                "route": route,
                "refused": response.refused,
                "refusal_reason": response.refusal_reason,
            },
            parent_span_id=parent_span_id,
            error_message=response.refusal_reason if response.refused else None,
        )
    )


def _observed_span(
    trace_id: str,
    suffix: str,
    span_type: str,
    name: str,
    *,
    input: str | None = None,
    output: str | None = None,
    status: str = "success",
    latency_ms: float = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    cost: Decimal = Decimal("0"),
    metadata: dict[str, object] | None = None,
    parent_span_id: str | None = None,
    error_message: str | None = None,
) -> ObservedSpan:
    return ObservedSpan(
        span_id=_span_id(trace_id, suffix),
        span_type=span_type,
        name=name,
        input=input,
        output=output,
        status=status,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens or prompt_tokens + completion_tokens,
        cost=cost,
        metadata=metadata or {},
        parent_span_id=parent_span_id,
        error_message=error_message,
    )


def _span_id(trace_id: str, suffix: str) -> str:
    return f"{trace_id}:{suffix}"[:100]


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)


def _json_payload(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _history_payload(request: ChatRequest) -> list[dict[str, str]]:
    return [message.model_dump() for message in request.history]


def _intent_payload(intent: RetrievalIntent) -> dict[str, object]:
    return {
        "name": intent.name,
        "project_id": intent.project_id,
        "allowed_document_ids": list(intent.allowed_document_ids),
        "expanded_terms": list(intent.expanded_terms),
        "heading_keywords": list(intent.heading_keywords),
        "content_keywords": list(intent.content_keywords),
    }


def _results_payload(results: Sequence[SearchResult]) -> list[dict[str, object]]:
    return [
        {
            "chunk_id": result.chunk.chunk_id,
            "document_id": result.chunk.document_id,
            "document_title": result.chunk.document_title,
            "heading_path": list(result.chunk.heading_path),
            "score": round(result.score, 4),
            "excerpt": _excerpt(result.chunk.content, 260),
        }
        for result in results
    ]


def _messages_payload(messages: Sequence[LLMMessage]) -> list[dict[str, str]]:
    return [{"role": message.role, "content": message.content} for message in messages]


def _estimate_llm_usage(messages: Sequence[LLMMessage], completion: str) -> LLMUsage:
    prompt_tokens = sum(_estimate_text_tokens(message.content) for message in messages)
    completion_tokens = _estimate_text_tokens(completion)
    return LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        estimated=True,
    )


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    cjk_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    non_cjk_chars = max(len(text) - cjk_chars, 0)
    return max(1, cjk_chars + non_cjk_chars // 4)


def _build_citations(results: Sequence[SearchResult]) -> list[Citation]:
    return [
        Citation(
            chunk_id=result.chunk.chunk_id,
            document_id=result.chunk.document_id,
            document_title=result.chunk.document_title,
            heading_path=list(result.chunk.heading_path),
            score=round(result.score, 4),
            excerpt=_excerpt(result.chunk.content),
        )
        for result in results
    ]


def _done_event(
    citations: Sequence[Citation],
    refused: bool,
    refusal_reason: str | None,
    debug: ChatDebugInfo | None = None,
) -> dict[str, Any]:
    return {
        "event": "done",
        "data": {
            "finish_reason": "stop",
            "refused": refused,
            "refusal_reason": refusal_reason,
            "citations": [citation.model_dump() for citation in citations],
            "debug": debug.model_dump() if debug else None,
        },
    }


def _error_event(message: str, code: str) -> dict[str, Any]:
    return {"event": "error", "data": {"message": message, "code": code}}


def _route_query(
    question: str,
    history_text: str,
    knowledge_scope: KnowledgeScope,
) -> QueryRoute:
    normalized = _normalize_query(question)
    if _has_restricted_signal(question):
        return "restricted"
    if _is_normal_chat_query(question, normalized, knowledge_scope):
        return "normal_chat"
    if _has_out_of_scope_signal(question, normalized):
        return "out_of_scope"
    if _has_knowledge_scope_signal(question, normalized, knowledge_scope):
        return "knowledge_rag"
    if _is_candidate_scoped_question(question, normalized):
        return "knowledge_rag"
    if _is_contextual_followup(question, normalized) and _has_knowledge_scope_signal(
        history_text,
        history_text.lower(),
        knowledge_scope,
    ):
        return "knowledge_rag"
    return "out_of_scope"


def _normalize_query(text: str) -> str:
    return "".join(text.lower().split()).strip("。！？!?,，～~")


def _has_restricted_signal(text: str) -> bool:
    return any(pattern in text for pattern in RESTRICTED_PATTERNS)


def _is_normal_chat_query(
    question: str,
    normalized: str,
    knowledge_scope: KnowledgeScope,
) -> bool:
    if _is_assistant_capability_query(normalized):
        return True
    if _has_knowledge_scope_signal(question, normalized, knowledge_scope):
        return False
    greetings = {
        "你好",
        "您好",
        "hi",
        "hello",
        "hey",
        "在吗",
        "谢谢",
        "感谢",
        "辛苦了",
        "你是谁",
        "你是什么",
        "怎么使用",
        "如何使用",
        "可以问什么",
        "我能问什么",
    }
    if normalized in greetings:
        return True
    if normalized.startswith(("谢谢", "感谢", "辛苦了")):
        return True
    return any(
        phrase in normalized
        for phrase in (
            "这个系统是干嘛的",
        )
    )


def _is_assistant_capability_query(normalized: str) -> bool:
    exact_queries = {
        "你能做什么",
        "你能做些什么",
        "你可以做什么",
        "你可以做些什么",
        "你都能做什么",
        "你能干什么",
        "你可以干什么",
        "你能帮我做什么",
        "你能帮我了解什么",
        "你能回答什么",
        "你能回答哪些",
        "你可以回答什么",
        "你可以回答哪些",
        "我可以问什么",
        "我能问什么",
        "可以问什么",
        "能问什么",
        "怎么使用",
        "如何使用",
    }
    if normalized in exact_queries:
        return True
    direct_phrases = (
        "你能回答哪些问题",
        "你可以回答哪些问题",
        "你能回答什么问题",
        "你可以回答什么问题",
        "我可以问你什么",
        "我能问你什么",
    )
    if any(phrase in normalized for phrase in direct_phrases):
        return True

    assistant_subjects = (
        "这个系统",
        "这个助手",
        "这个ai",
        "ai助手",
        "个人经历ai",
        "个人经历助手",
        "简历助手",
        "问答系统",
    )
    capability_phrases = (
        "能做什么",
        "能做些什么",
        "可以做什么",
        "可以做些什么",
        "能干什么",
        "可以干什么",
        "能帮我做什么",
        "能帮我了解什么",
        "能回答什么",
        "能回答哪些",
        "可以回答什么",
        "可以回答哪些",
        "可以问什么",
        "能问什么",
        "怎么使用",
        "如何使用",
        "是干嘛的",
    )
    return any(subject in normalized for subject in assistant_subjects) and any(
        phrase in normalized for phrase in capability_phrases
    )


def _has_out_of_scope_signal(question: str, normalized: str) -> bool:
    chinese_terms = (
        "天气",
        "气温",
        "下雨",
        "新闻",
        "股票",
        "股价",
        "汇率",
        "餐厅",
        "外卖",
        "路线",
        "导航",
        "机票",
        "酒店",
        "写首诗",
        "讲个笑话",
        "生成图片",
        "画图",
    )
    english_terms = (
        "weather",
        "temperature",
        "news",
        "stock",
        "restaurant",
        "flight",
        "hotel",
        "joke",
        "poem",
    )
    translation_actions = ("帮我翻译", "请翻译", "翻译一下", "翻译成", "translate this")
    return (
        any(term in question for term in chinese_terms)
        or any(term in normalized for term in english_terms)
        or any(term in normalized for term in translation_actions)
    )


def _has_knowledge_scope_signal(
    text: str,
    normalized: str,
    knowledge_scope: KnowledgeScope,
) -> bool:
    chinese_terms = (
        "周逢森",
        "候选人",
        "面试人",
        "个人经历",
        "自我介绍",
        "介绍一下你",
        "介绍自己",
        "叫什么",
        "叫啥",
        "名字",
        "姓名",
        "简历",
        "项目",
        "实习",
        "经历",
        "技术栈",
        "技术能力",
        "技术方向",
        "技能",
        "教育背景",
        "毕业院校",
        "毕业学校",
        "毕业于",
        "哪所大学",
        "什么大学",
        "学校",
        "学历",
        "求职方向",
        "工作方向",
        "寻找什么方向",
        "个人优势",
        "突出优势",
        "优势",
        "适合",
        "应聘",
        "岗位",
        "职责",
        "负责",
        "贡献",
        "难点",
        "架构",
        "成果",
        "结果",
        "团队",
        "角色",
        "权限",
        "仓库",
        "私有代码库",
        "检索",
        "命令行",
        "自动化工具",
        "线上数据",
        "公开数据",
        "指标",
        "大模型",
        "agent",
        "智能体",
        "rag",
        "辅助开发",
        "辅助编程",
        "编程能力",
    )
    english_terms = (
        "project",
        "internship",
        "resume",
        "experience",
        "responsibility",
        "contribution",
        "architecture",
        "challenge",
        "skill",
        "rag",
        "agent",
        "mcp",
        "cli",
        "gitlab",
        "codex",
        "glm",
        "llm",
        "platform",
        "semantic search",
        "owned by",
        "teammate",
    )
    return (
        knowledge_scope.match_project(text) is not None
        or any(term in text for term in chinese_terms)
        or any(term in normalized for term in english_terms)
    )


def _is_contextual_followup(question: str, normalized: str) -> bool:
    followup_terms = (
        "那",
        "这个",
        "这些",
        "上面",
        "刚才",
        "继续",
        "展开",
        "详细",
        "再说",
        "它",
        "there",
        "that",
        "more",
        "details",
    )
    return any(term in question for term in followup_terms) or any(
        term in normalized for term in followup_terms
    )


def _is_uncovered_personal_fact_question(text: str) -> bool:
    candidate_signal = any(term in text for term in ("你", "候选人", "面试人", "周逢森"))
    if not candidate_signal:
        return False
    personal_fact_terms = (
        "喜欢什么颜色",
        "喜欢的颜色",
        "最喜欢的颜色",
        "兴趣爱好",
        "爱好",
        "生日",
        "星座",
        "身高",
        "体重",
        "家庭情况",
        "父母",
        "住址",
        "婚姻",
    )
    return any(term in text for term in personal_fact_terms)


def _is_candidate_scoped_question(question: str, normalized: str) -> bool:
    subject_signal = (
        "你" in question
        or "候选人" in question
        or "面试人" in question
        or "周逢森" in question
        or any(term in normalized for term in ("you", "your", "candidate", "zhou"))
    )
    if not subject_signal:
        return False
    personal_attribute_terms = (
        "什么",
        "哪",
        "哪里",
        "哪儿",
        "多少",
        "有没有",
        "是否",
        "会不会",
        "能不能",
        "会",
        "可以",
        "介绍",
        "说说",
        "讲讲",
        "毕业",
        "大学",
        "专业",
        "名字",
        "姓名",
        "项目",
        "经历",
        "能力",
        "技能",
        "优势",
        "工作",
        "岗位",
        "实习",
        "负责",
        "做过",
        "掌握",
    )
    english_attribute_terms = (
        "name",
        "university",
        "college",
        "graduate",
        "major",
        "background",
        "experience",
        "project",
        "skill",
        "strength",
        "role",
        "responsible",
        "work",
        "intern",
    )
    return any(term in question for term in personal_attribute_terms) or any(
        term in normalized for term in english_attribute_terms
    )


def _normal_chat_answer(question: str) -> str:
    normalized = _normalize_query(question)
    if normalized.startswith(("谢谢", "感谢", "辛苦了")):
        return "不客气。你可以继续询问周逢森的项目经历、技术能力、个人贡献、技术难点或职责边界。"
    return (
        "你好，我是个人经历 AI 助手，主要帮助面试官了解周逢森的公开个人经历。"
        "你可以询问他的个人背景、求职方向、技术栈、实习经历、代表项目、个人贡献、"
        "技术难点、项目成果和职责边界。例如可以问："
        "“他在 Skillvar 中具体负责什么？”“这个 Agentic RAG 项目有什么亮点？”"
        "“他的主要技术栈是什么？”"
    )


def _out_of_scope_answer(question: str) -> str:
    if any(term in question for term in ("天气", "气温", "下雨")) or any(
        term in _normalize_query(question) for term in ("weather", "temperature")
    ):
        return (
            "抱歉，我不能查询实时天气。这个系统主要用于回答关于周逢森的个人经历、"
            "项目经历、技术能力和职责边界的问题。"
            "你可以继续询问他的个人背景、Skillvar、OntoCore、Agentic RAG 个人经历助手、"
            "技术难点或项目职责。"
        )
    return (
        "抱歉，这个系统不是通用聊天或实时信息查询工具，主要用于了解周逢森的个人经历、"
        "项目经历、技术能力和职责边界。"
        "你可以询问个人背景、Skillvar、OntoCore、Agentic RAG 个人经历助手、"
        "技术栈、个人贡献或技术难点。"
    )


def _infer_intent(
    question: str,
    history_text: str,
    project: ProjectKnowledge | None = None,
) -> RetrievalIntent:
    text = f"{history_text} {question}"
    normalized = text.lower()

    project_intro_intent = _infer_project_intro_intent(text, normalized, project)
    if project_intro_intent is not None:
        return project_intro_intent

    if _has_ai_assisted_development_signal(text, normalized):
        return RetrievalIntent(
            name="ai_assisted_development",
            expanded_terms=(
                "AI 辅助开发边界",
                "Codex",
                "GLM-5.2",
                "辅助编程",
                "代码理解",
                "实现迭代",
                "理解",
                "集成",
                "调试",
                "测试",
                "部署",
                "验证",
            ),
            document_boosts={"skillvar-responsibilities": 8.0, "skillvar-overview": 2.0},
            heading_keywords=("AI 辅助开发边界", "已确认的个人实现范围"),
            content_keywords=("Codex", "GLM-5.2", "理解", "集成", "测试", "部署"),
        )

    profile_intent = _infer_profile_intent(question, question.lower())
    if profile_intent is not None:
        return profile_intent

    if _has_challenge_signal(text, normalized):
        return RetrievalIntent(
            name="challenge",
            expanded_terms=(
                "核心难点",
                "最大技术难点",
                "hardest part",
                "biggest challenge",
                "most difficult",
                "GitLab",
                "仓库层级关系",
                "权限隔离",
                "问题背景",
                "发现现象",
                "定位过程",
                "我的解决方案",
                "父 Group",
                "Subgroup",
                "Repository",
                "inherited access",
                "private repository",
                "leaking access",
            ),
            document_boosts={"skillvar-challenges": 8.0},
            heading_keywords=("问题背景", "发现现象与定位过程", "我的解决方案", "结果与边界"),
            content_keywords=(
                "GitLab",
                "父 Group",
                "Subgroup",
                "Repository",
                "私有",
                "继承",
                "权限",
            ),
        )
    if _has_engineering_delivery_signal(text):
        return RetrievalIntent(
            name="engineering_delivery",
            expanded_terms=(
                "工程问题处理",
                "测试",
                "业务侧部署",
                "部署运维",
                "环境变量",
                "远程仓库",
                "内部测试",
            ),
            document_boosts={"skillvar-responsibilities": 7.0, "skillvar-results": 5.0},
            heading_keywords=("工程问题处理", "已有功能成果", "项目状态"),
            content_keywords=("测试", "部署运维", "环境变量", "远程仓库", "内部测试"),
        )
    if (
        "团队" in text and "个人" in text and ("贡献" in text or "成果" in text)
    ) or ("owned by" in normalized and any(term in normalized for term in ("team", "product"))):
        return RetrievalIntent(
            name="team_vs_personal",
            expanded_terms=(
                "团队边界",
                "公开回答边界",
                "个人实现范围",
                "本人负责简历所列模块",
                "产品工作由团队其他成员负责",
                "项目整体业务成果属于团队",
                "功能成果",
                "内部测试",
                "AI 工具",
            ),
            document_boosts={"skillvar-responsibilities": 5.0, "skillvar-results": 4.0},
            heading_keywords=("个人实现范围", "团队边界", "公开回答边界", "已有功能成果"),
            content_keywords=("产品需求", "产品工作", "团队其他成员", "简历所列模块", "内部测试"),
        )
    if "团队" in text or "角色" in text:
        return RetrievalIntent(
            name="team_role",
            expanded_terms=(
                "时间与团队",
                "团队边界",
                "算法实习生",
                "产品职责",
                "本人角色",
                "测试",
                "部署运维",
            ),
            document_boosts={"skillvar-overview": 3.0, "skillvar-responsibilities": 4.0},
            heading_keywords=("时间与团队", "团队边界", "公开回答边界"),
            content_keywords=("产品", "算法实习生", "部署运维"),
        )
    if "不是你负责" in text or "不负责" in text:
        return RetrievalIntent(
            name="negative_responsibility",
            expanded_terms=("团队边界", "公开回答边界", "产品需求", "UI", "其他研发角色"),
            document_boosts={"skillvar-responsibilities": 5.0},
            heading_keywords=("团队边界", "公开回答边界"),
            content_keywords=("产品需求", "UI", "其他研发角色"),
        )
    if "负责" in text or "贡献" in text:
        return RetrievalIntent(
            name="responsibility",
            expanded_terms=(
                "已确认的个人实现范围",
                "平台后端",
                "混合检索",
                "LLM 翻译",
                "Skill 创作",
                "安全治理",
                "安全扫描",
                "MCP",
                "CLI",
                "企业协作集成",
                "工程问题处理",
                "Codex",
                "GLM-5.2",
                "测试",
                "部署运维",
                "GitLab 仓库层级权限隔离",
            ),
            document_boosts={"skillvar-responsibilities": 5.0, "skillvar-challenges": 2.0},
            heading_keywords=(
                "个人实现范围",
                "平台后端",
                "混合检索",
                "LLM 翻译",
                "安全治理",
                "MCP 与 CLI",
                "企业协作集成",
                "工程问题处理",
                "AI 辅助开发边界",
                "我的解决方案",
            ),
            content_keywords=("Codex", "GLM-5.2", "测试", "部署运维", "权限隔离"),
        )
    if _has_reflection_signal(text, normalized):
        return RetrievalIntent(
            name="reflection",
            expanded_terms=(
                "项目复盘",
                "做得比较好的地方",
                "暴露出的不足和技术债",
                "如果重新开始",
                "工程复盘",
                "技术债",
                "改进方向",
                "Webhook",
                "Embedding",
                "静态规则",
                "测试矩阵",
            ),
            document_boosts={"skillvar-reflection": 8.0, "skillvar-source-review": 0.0},
            heading_keywords=(
                "复盘结论",
                "做得比较好的地方",
                "暴露出的不足和技术债",
                "如果重新开始会优先调整什么",
            ),
            content_keywords=("技术债", "改进", "不足", "重新开始", "工程复盘"),
        )
    if _has_data_flow_signal(text, normalized) and not (
        _has_mcp_cli_signal(text, normalized)
        or _has_retrieval_signal(text, normalized)
        or _has_llm_pipeline_signal(text, normalized)
        or _has_safety_governance_signal(text, normalized)
        or _has_enterprise_integration_signal(text, normalized)
    ):
        return RetrievalIntent(
            name="data_flow",
            expanded_terms=(
                "模块调用链",
                "总体调用关系",
                "数据流",
                "调用链",
                "流程",
                "Web",
                "API",
                "MCP",
                "CLI",
                "services",
                "MongoDB",
                "GitLab",
                "飞书",
            ),
            document_boosts={"skillvar-data-flows": 8.0, "skillvar-architecture": 3.0},
            heading_keywords=(
                "总体调用关系",
                "Skill 采集入库调用链",
                "自然语言创建 Skill 调用链",
                "搜索与推荐调用链",
                "GitLab 私有仓库调用链",
            ),
            content_keywords=("调用链", "数据流", "流转", "services", "MongoDB"),
        )
    if _has_feature_list_signal(text, normalized):
        return RetrievalIntent(
            name="feature_list",
            expanded_terms=(
                "功能清单",
                "功能全景",
                "已知功能范围",
                "Web 端功能",
                "FastAPI 功能",
                "MCP 与 CLI 分发",
                "企业协作功能",
                "数据与可观测性功能",
            ),
            document_boosts={
                "skillvar-features": 8.0,
                "skillvar-overview": 2.0,
                "skillvar-results": 2.0,
            },
            heading_keywords=(
                "功能全景",
                "Web 端功能",
                "FastAPI 功能",
                "数据采集与提交",
                "MCP 与 CLI 分发",
            ),
            content_keywords=("功能", "搜索", "安装", "创建", "共享", "MCP", "CLI"),
        )
    if _has_mcp_cli_signal(text, normalized):
        return RetrievalIntent(
            name="mcp_cli",
            expanded_terms=(
                "MCP 与 CLI",
                "MCP Server",
                "npm CLI",
                "Agent 工作流",
                "命令行",
                "自动化工具",
                "分发",
                "安装",
                "搜索",
                "详情",
                "推荐",
                "创建",
                "优化",
                "团队共享",
                "agent workflow",
                "command line",
                "tool",
                "exposed to agents",
            ),
            document_boosts={
                "skillvar-responsibilities": 6.0,
                "skillvar-architecture": 5.0,
                "skillvar-features": 4.0,
                "skillvar-data-flows": 4.0,
                "skillvar-results": 2.0,
            },
            heading_keywords=("MCP 与 CLI", "已确认的个人实现范围", "主要组件"),
            content_keywords=("MCP Server", "npm CLI", "Agent 工作流", "命令行", "安装"),
        )
    if _has_retrieval_fallback_signal(text, normalized):
        return RetrievalIntent(
            name="retrieval_fallback",
            expanded_terms=(
                "混合检索",
                "ChromaDB",
                "语义召回",
                "BM25-only",
                "MongoDB 正则搜索兜底",
                "fallback",
                "unavailable",
                "semantic search channel",
                "retrieval fallback",
            ),
            document_boosts={"skillvar-architecture": 7.0, "skillvar-responsibilities": 3.0},
            heading_keywords=("混合检索", "主要组件"),
            content_keywords=("ChromaDB", "BM25-only", "MongoDB 正则搜索兜底", "语义召回"),
        )
    if _has_retrieval_signal(text, normalized):
        return RetrievalIntent(
            name="retrieval",
            expanded_terms=(
                "混合检索",
                "jieba",
                "rank-bm25",
                "BM25",
                "ChromaDB",
                "向量检索",
                "RRF",
                "重排序",
            ),
            document_boosts={
                "skillvar-architecture": 7.0,
                "skillvar-data-flows": 4.0,
                "skillvar-responsibilities": 6.0,
            },
            heading_keywords=("混合检索",),
            content_keywords=("jieba", "rank-bm25", "ChromaDB", "RRF", "重排序"),
        )
    if _has_llm_pipeline_signal(text, normalized):
        return RetrievalIntent(
            name="llm_pipeline",
            expanded_terms=(
                "LLM 翻译与生成",
                "LLM 翻译与 Skill 创作",
                "OpenAI 兼容接口",
                "DashScope",
                "Qwen",
                "Markdown 结构保护",
                "术语库",
                "分块翻译",
                "缓存复用",
                "Skill 草稿生成",
            ),
            document_boosts={
                "skillvar-architecture": 7.0,
                "skillvar-data-flows": 4.0,
                "skillvar-responsibilities": 6.0,
            },
            heading_keywords=("LLM 翻译与生成", "LLM 翻译与 Skill 创作"),
            content_keywords=(
                "OpenAI 兼容接口",
                "DashScope",
                "Qwen",
                "Markdown",
                "术语",
                "分块",
                "缓存",
                "草稿生成",
            ),
        )
    if _has_safety_governance_signal(text, normalized):
        return RetrievalIntent(
            name="safety_governance",
            expanded_terms=(
                "安全治理",
                "规则库静态扫描",
                "safe",
                "warning",
                "danger",
                "写回 MongoDB",
            ),
            document_boosts={
                "skillvar-architecture": 7.0,
                "skillvar-features": 3.0,
                "skillvar-responsibilities": 6.0,
            },
            heading_keywords=("安全治理", "安全扫描"),
            content_keywords=("规则库", "safe", "warning", "danger", "MongoDB"),
        )
    if _has_enterprise_integration_signal(text, normalized):
        return RetrievalIntent(
            name="enterprise_integration",
            expanded_terms=(
                "企业协作集成",
                "GitLab OAuth",
                "Webhook",
                "Fork/Commit 同步",
                "飞书组织体系",
                "企业私有 Skill 仓库",
            ),
            document_boosts={
                "skillvar-architecture": 7.0,
                "skillvar-data-flows": 4.0,
                "skillvar-responsibilities": 6.0,
            },
            heading_keywords=("企业协作集成",),
            content_keywords=("GitLab", "OAuth", "Webhook", "Fork", "飞书", "企业私有"),
        )
    if _has_data_storage_signal(text, normalized):
        return RetrievalIntent(
            name="data_storage",
            expanded_terms=(
                "数据存储",
                "MongoDB",
                "Skill 主数据",
                "业务数据",
                "行为日志",
                "LLM 用量",
            ),
            document_boosts={"skillvar-architecture": 8.0},
            heading_keywords=("数据存储",),
            content_keywords=("MongoDB", "Skill 主数据", "行为日志", "LLM 用量"),
        )
    if "架构" in text or "流转" in text or "技术" in text or "技术栈" in text:
        return RetrievalIntent(
            name="architecture",
            expanded_terms=(
                "逻辑架构",
                "主要组件",
                "Web 与 API",
                "数据存储",
                "混合检索",
                "LLM 翻译与生成",
                "MCP 与 CLI",
                "Streamlit",
                "FastAPI",
                "services",
                "MongoDB",
                "BM25",
                "ChromaDB",
                "DashScope",
                "Qwen",
            ),
            document_boosts={"skillvar-architecture": 6.0},
            heading_keywords=(
                "逻辑架构",
                "Web 与 API",
                "数据存储",
                "混合检索",
                "LLM",
                "MCP 与 CLI",
            ),
            content_keywords=("Streamlit", "FastAPI", "MongoDB", "ChromaDB", "DashScope", "Qwen"),
        )
    if any(
        term in text
        for term in (
            "结果",
            "成果",
            "指标",
            "提升",
            "统计",
            "性能",
            "用户规模",
            "效果数据",
            "公开数据",
            "线上数据",
        )
    ) or any(
        term in normalized
        for term in ("traffic", "latency", "usage number", "performance", "metric")
    ):
        return RetrievalIntent(
            name="result",
            expanded_terms=(
                "已有功能成果",
                "内部测试",
                "不可公开",
                "量化数据",
                "性能",
                "规模",
                "效果",
                "公开数据",
                "线上数据",
            ),
            document_boosts={"skillvar-results": 7.0, "skillvar-overview": 2.0},
            heading_keywords=("已有功能成果", "当前不可公开的量化数据", "项目状态"),
            content_keywords=("内部测试", "没有允许公开", "闭环", "MCP Server", "npm CLI"),
        )
    if "解决" in text and "问题" in text:
        return RetrievalIntent(
            name="project_problem",
            expanded_terms=(
                "项目背景",
                "分散",
                "Skill 资产",
                "治理加工",
                "企业内部复用",
                "Agent 能力复用",
            ),
            document_boosts={"skillvar-overview": 6.0},
            heading_keywords=("项目背景", "项目摘要"),
            content_keywords=("分散", "治理", "企业内部", "复用"),
        )
    if "目标" in text:
        return RetrievalIntent(
            name="project_goal",
            expanded_terms=(
                "项目摘要",
                "核心业务链路",
                "已知功能范围",
                "Skill 采集入库",
                "搜索",
                "推荐",
                "安装",
                "企业共享",
            ),
            document_boosts={"skillvar-overview": 6.0},
            heading_keywords=("项目摘要", "核心业务链路", "已知功能范围"),
            content_keywords=("采集", "检索", "安装", "企业共享"),
        )
    if "代表项目" in text:
        return RetrievalIntent(
            name="project_overview",
            expanded_terms=(
                "Skillvar",
                "项目摘要",
                "核心业务链路",
                "AI Agent Skill 资产平台",
                "采集",
                "治理",
                "检索",
                "分发",
                "安装闭环",
            ),
            document_boosts={"skillvar-overview": 6.0},
            heading_keywords=("项目摘要", "核心业务链路", "已知功能范围"),
            content_keywords=("AI Skill", "采集", "治理", "检索", "安装", "企业内部复用"),
        )
    return RetrievalIntent()


def _infer_project_intro_intent(
    text: str,
    normalized: str,
    project: ProjectKnowledge | None,
) -> RetrievalIntent | None:
    if project is None:
        return None
    overview_signal = any(
        term in text for term in ("介绍", "概述", "是什么", "正在做", "体现")
    ) or any(term in normalized for term in ("what is", "introduce", "overview"))
    deep_dive_signal = any(
        term in text
        for term in (
            "负责",
            "职责",
            "贡献",
            "团队",
            "角色",
            "难点",
            "最难",
            "困难",
            "棘手",
            "根因",
            "定位",
            "架构",
            "成果",
            "结果",
            "指标",
            "混合检索",
            "权限",
            "安全治理",
            "企业协作",
            "测试",
            "部署",
        )
    ) or any(
        term in normalized
        for term in ("mcp", "cli", "llm", "bm25", "pgvector", "embedding", "gitlab")
    )
    if not overview_signal or deep_dive_signal:
        return None
    return RetrievalIntent(
        name="project_overview",
        expanded_terms=("项目摘要", "项目背景", "核心功能", "项目状态"),
        heading_keywords=("项目摘要", "核心能力链路", "当前状态", "公开回答边界"),
        content_keywords=("知识治理", "检索", "引用", "问题路由", "质量评测"),
    )


def _infer_profile_intent(text: str, normalized: str) -> RetrievalIntent | None:
    if "项目" not in text and any(term in text for term in ("叫什么", "叫啥", "名字", "姓名")):
        return RetrievalIntent(
            name="identity",
            expanded_terms=(
                "简短自我介绍",
                "周逢森",
                "我叫周逢森",
                "2026 届人工智能专业本科应届生",
                "大模型应用开发",
            ),
            allowed_document_ids=("profile-introduction", "resume-main"),
            document_boosts={"profile-introduction": 10.0, "resume-main": 6.0},
            heading_keywords=("简短自我介绍", "一句话定位", "基本信息"),
            content_keywords=("周逢森", "我叫", "2026 届", "人工智能"),
        )
    if any(
        term in text
        for term in (
            "教育背景",
            "毕业院校",
            "毕业学校",
            "毕业于",
            "哪所大学",
            "读的大学",
            "什么大学",
            "哪所学校",
            "哪个学校",
            "学什么专业",
            "学校",
            "学历",
        )
    ) or (
        "专业" in text
        and "项目" not in text
        and any(term in text for term in ("什么", "哪个", "学", "读", "大学", "学校"))
    ):
        return RetrievalIntent(
            name="education",
            expanded_terms=(
                "教育背景摘要",
                "南宁理工学院",
                "人工智能专业",
                "本科",
                "2022 年 9 月至 2026 年 6 月",
                "主修课程",
                "在校荣誉",
                "求职方向",
            ),
            allowed_document_ids=("profile-introduction", "resume-main"),
            document_boosts={"profile-introduction": 9.0, "resume-main": 8.0},
            heading_keywords=("教育背景", "教育背景摘要", "一句话定位"),
            content_keywords=("南宁理工学院", "人工智能", "本科", "2026"),
        )
    if (
        "为什么你适合" in text
        or ("适合" in text and any(term in text for term in ("岗位", "工程师", "应聘")))
        or "job fit" in normalized
    ):
        return RetrievalIntent(
            name="job_fit",
            expanded_terms=(
                "重点能力方向",
                "有详细项目证据的能力",
                "RAG",
                "Agent",
                "Python 后端",
                "工程化能力",
                "Skillvar",
                "测试",
                "部署运维",
            ),
            allowed_document_ids=(
                "profile-introduction",
                "profile-skills",
                "resume-main",
                "skillvar-responsibilities",
            ),
            document_boosts={
                "profile-introduction": 9.0,
                "profile-skills": 9.0,
                "resume-main": 5.0,
                "skillvar-responsibilities": 5.0,
            },
            heading_keywords=("重点能力方向", "有详细项目证据的能力", "工程化能力"),
            content_keywords=("RAG", "Agent", "Python", "FastAPI", "测试", "部署"),
        )
    if any(
        term in text
        for term in ("求职方向", "工作方向", "方向的工作", "寻找什么方向", "应聘方向")
    ):
        return RetrievalIntent(
            name="career_direction",
            expanded_terms=(
                "当前求职方向",
                "大模型应用开发",
                "AI 应用开发",
                "AI 后端开发",
            ),
            allowed_document_ids=("profile-introduction", "resume-main"),
            document_boosts={"profile-introduction": 10.0, "resume-main": 6.0},
            heading_keywords=("当前求职方向", "一句话定位", "基本信息"),
            content_keywords=("大模型应用开发", "AI 应用开发", "AI 后端开发"),
        )
    personal_skill_question = (
        ("你" in text or "候选人" in text or "周逢森" in text)
        and any(term in text for term in ("会", "掌握", "熟悉", "用过", "技术", "能力", "技能"))
        and any(
            term in normalized
            for term in (
                "python",
                "fastapi",
                "mongodb",
                "rag",
                "agent",
                "pytorch",
                "transformer",
                "bm25",
            )
        )
    )
    if (
        any(term in text for term in ("技术栈", "哪些技术", "技术方向"))
        or personal_skill_question
    ) and not any(
        term in text for term in ("项目的技术栈", "项目技术栈", "Skillvar 的技术栈")
    ):
        return RetrievalIntent(
            name="skills_profile",
            expanded_terms=(
                "有详细项目证据的能力",
                "基础了解或需要进一步证明的能力",
                "Python",
                "FastAPI",
                "MongoDB",
                "RAG",
                "Agent",
                "PyTorch",
                "Transformer",
            ),
            allowed_document_ids=("profile-skills", "resume-main"),
            document_boosts={"profile-skills": 10.0, "resume-main": 7.0},
            heading_keywords=(
                "有详细项目证据的能力",
                "编程语言与框架",
                "AI、RAG 与 Agent",
                "基础了解或需要进一步证明的能力",
                "个人能力总结",
            ),
            content_keywords=("Python", "FastAPI", "MongoDB", "RAG", "Agent"),
        )
    if "优势" in text:
        return RetrievalIntent(
            name="personal_strengths",
            expanded_terms=(
                "重点能力方向",
                "有详细项目证据的能力",
                "RAG",
                "Agent",
                "Skillvar",
                "工程化能力",
            ),
            allowed_document_ids=("profile-introduction", "profile-skills", "resume-main"),
            document_boosts={"profile-introduction": 9.0, "profile-skills": 8.0},
            heading_keywords=("重点能力方向", "简短自我介绍", "有详细项目证据的能力"),
            content_keywords=("RAG", "Agent", "Skillvar", "Python", "工程"),
        )
    if "项目" not in text and any(
        term in text for term in ("自我介绍", "介绍一下你", "介绍自己")
    ):
        return RetrievalIntent(
            name="profile_introduction",
            expanded_terms=(
                "简短自我介绍",
                "周逢森",
                "2026 届人工智能专业本科应届生",
                "大模型应用开发",
                "Skillvar",
            ),
            allowed_document_ids=("profile-introduction", "resume-main"),
            document_boosts={"profile-introduction": 10.0, "resume-main": 6.0},
            heading_keywords=("简短自我介绍", "一句话定位", "基本信息"),
            content_keywords=("周逢森", "2026 届", "人工智能", "Skillvar"),
        )
    return None


def _has_mcp_cli_signal(text: str, normalized: str) -> bool:
    chinese_terms = ("命令行", "自动化工具", "工具", "交给", "暴露", "分发")
    english_terms = (
        "command line",
        "cli",
        "mcp",
        "agent workflow",
        "agents",
        "exposed to",
    )
    return (
        ("mcp" in normalized or "cli" in normalized)
        or (
            any(term in text for term in chinese_terms)
            and any(term in text for term in ("能力", "使用", "平台"))
        )
        or any(term in normalized for term in english_terms)
    )


def _has_feature_list_signal(text: str, normalized: str) -> bool:
    chinese_terms = (
        "功能清单",
        "功能模块",
        "功能范围",
        "主要功能",
        "哪些功能",
        "有哪些功能",
        "支持哪些",
        "做了哪些",
        "页面",
        "入口",
    )
    english_terms = ("feature list", "features", "what can skillvar do", "capabilities")
    return any(term in text for term in chinese_terms) or any(
        term in normalized for term in english_terms
    )


def _has_data_flow_signal(text: str, normalized: str) -> bool:
    chinese_terms = (
        "调用链",
        "数据流",
        "数据怎么走",
        "链路",
        "流程",
        "工作流",
        "怎么工作",
    )
    english_terms = ("call chain", "data flow", "workflow", "pipeline", "how does it work")
    return any(term in text for term in chinese_terms) or any(
        term in normalized for term in english_terms
    )


def _has_reflection_signal(text: str, normalized: str) -> bool:
    chinese_terms = (
        "复盘",
        "不足",
        "技术债",
        "做得不好",
        "做得好",
        "如果重来",
        "重新开始",
        "改进",
        "局限",
        "限制",
    )
    english_terms = (
        "retrospective",
        "reflection",
        "technical debt",
        "lessons learned",
        "what would you improve",
        "limitations",
    )
    return any(term in text for term in chinese_terms) or any(
        term in normalized for term in english_terms
    )


def _has_challenge_signal(text: str, normalized: str) -> bool:
    chinese_terms = (
        "难点",
        "最难",
        "困难",
        "棘手",
        "根因",
        "定位",
        "权限",
        "私有代码库",
        "私有仓库",
        "别人可能看见",
    )
    english_terms = (
        "hardest part",
        "biggest challenge",
        "most difficult",
        "root cause",
        "inherited access",
        "leaking",
        "private skill repositories",
        "prevent inherited",
    )
    return any(term in text for term in chinese_terms) or any(
        term in normalized for term in english_terms
    )


def _has_ai_assisted_development_signal(text: str, normalized: str) -> bool:
    tool_signal = any(term in normalized for term in ("codex", "glm-5.2", "glm"))
    development_signal = any(
        term in text for term in ("辅助开发", "辅助编程", "编程", "代码", "能力")
    )
    return tool_signal and development_signal


def _has_llm_pipeline_signal(text: str, normalized: str) -> bool:
    llm_signal = "llm" in normalized or "大模型" in text
    pipeline_signal = any(term in text for term in ("翻译", "生成", "创作", "草稿"))
    english_usage_signal = any(term in normalized for term in ("use llm", "llms for", "llm for"))
    return llm_signal and (pipeline_signal or english_usage_signal)


def _has_engineering_delivery_signal(text: str) -> bool:
    return any(term in text for term in ("测试", "部署", "运维", "环境变量", "远程仓库"))


def _has_retrieval_signal(text: str, normalized: str) -> bool:
    chinese_terms = ("混合检索", "向量检索", "关键词检索", "检索实现", "怎么检索")
    english_terms = ("hybrid retrieval", "hybrid search", "vector search", "bm25", "rrf")
    return any(term in text for term in chinese_terms) or any(
        term in normalized for term in english_terms
    )


def _has_safety_governance_signal(text: str, normalized: str) -> bool:
    chinese_terms = ("安全治理", "安全扫描", "不安全", "风险内容")
    english_terms = ("unsafe skill", "safety scan", "safe", "warning", "danger")
    return any(term in text for term in chinese_terms) or any(
        term in normalized for term in english_terms
    )


def _has_enterprise_integration_signal(text: str, normalized: str) -> bool:
    chinese_terms = ("企业协作", "飞书", "组织体系", "企业集成")
    english_terms = ("gitlab oauth", "webhook", "fork/commit", "feishu")
    return any(term in text for term in chinese_terms) or any(
        term in normalized for term in english_terms
    )


def _has_data_storage_signal(text: str, normalized: str) -> bool:
    chinese_terms = ("数据库", "数据存储", "存储什么", "保存什么")
    english_terms = ("what database", "database stored", "data storage", "stored the skill")
    return any(term in text for term in chinese_terms) or any(
        term in normalized for term in english_terms
    )


def _has_retrieval_fallback_signal(text: str, normalized: str) -> bool:
    chinese_retrieval_terms = ("语义检索", "语义召回", "检索通道", "ChromaDB", "混合检索")
    chinese_fallback_terms = ("不可用", "降级", "兜底", "无结果", "退化")
    english_retrieval_terms = (
        "semantic search",
        "semantic search channel",
        "retrieval",
        "search channel",
        "chromadb",
    )
    english_fallback_terms = (
        "unavailable",
        "fallback",
        "no result",
        "degrade",
        "degraded",
    )
    return (
        any(term in text for term in chinese_retrieval_terms)
        and any(term in text for term in chinese_fallback_terms)
    ) or (
        any(term in normalized for term in english_retrieval_terms)
        and any(term in normalized for term in english_fallback_terms)
    )


def _history_text(request: ChatRequest) -> str:
    return " ".join(message.content for message in request.history[-4:])


def _build_retrieval_query(question: str, history_text: str, intent: RetrievalIntent) -> str:
    terms = " ".join(intent.expanded_terms)
    return f"{history_text} {question} {terms}".strip()


def rerank_score(result: SearchResult, intent: RetrievalIntent) -> float:
    score = result.score
    chunk = result.chunk
    score += intent.document_boosts.get(chunk.document_id, 0.0)
    heading_text = " ".join(chunk.heading_path)
    for keyword in intent.heading_keywords:
        if keyword and keyword in heading_text:
            score += 3.0
    searchable_text = f"{heading_text}\n{chunk.content}"
    for keyword in intent.content_keywords:
        if keyword and keyword in searchable_text:
            score += 1.0
    return score


def _scope_intent_to_project(
    intent: RetrievalIntent,
    project: ProjectKnowledge | None,
) -> RetrievalIntent:
    if project is None or intent.name in PROFILE_INTENT_NAMES:
        return intent

    intent_name = intent.name if intent.name != "generic" else "project_overview"
    kinds_by_intent = {
        "challenge": ("challenges",),
        "responsibility": ("responsibilities",),
        "negative_responsibility": ("responsibilities",),
        "team_vs_personal": ("responsibilities", "results"),
        "team_role": ("responsibilities", "overview"),
        "ai_assisted_development": ("responsibilities", "overview"),
        "engineering_delivery": ("responsibilities", "results"),
        "result": ("results", "overview"),
        "architecture": ("architecture",),
        "data_storage": ("architecture",),
        "retrieval": ("architecture", "responsibilities"),
        "retrieval_fallback": ("architecture", "responsibilities"),
        "llm_pipeline": ("architecture", "responsibilities"),
        "safety_governance": ("architecture", "responsibilities"),
        "enterprise_integration": ("architecture", "responsibilities"),
        "mcp_cli": ("architecture", "responsibilities"),
        "feature_list": ("features", "overview", "results"),
        "data_flow": ("data-flows", "architecture"),
        "reflection": ("reflection",),
        "project_problem": ("overview",),
        "project_goal": ("overview",),
        "project_overview": ("overview",),
    }
    generic_terms_by_intent = {
        "responsibility": (
            "项目职责",
            "职责摘要",
            "我的职责",
            "个人负责",
            "个人实现范围",
            "多租户业务模型",
            "知识图谱链路",
            "AI 查询链路",
            "系统检测链路",
            "身份权限",
            "平台后端",
            "团队边界",
        ),
        "negative_responsibility": (
            "项目职责",
            "职责摘要",
            "参与但不主导",
            "非个人主导",
            "不能公开夸大",
            "公开回答边界",
        ),
        "team_vs_personal": ("个人贡献", "团队工作", "团队边界", "公开回答边界"),
        "architecture": (
            "项目架构",
            "架构摘要",
            "技术栈",
            "逻辑架构",
            "数据流",
            "主要组件",
            "AI 查询架构",
            "图谱同步架构",
            "权限架构",
        ),
        "feature_list": ("功能清单", "功能全景", "功能模块", "功能范围"),
        "data_flow": ("模块调用链", "调用链", "数据流", "流程", "链路"),
        "reflection": ("项目复盘", "技术债", "不足", "改进方向", "如果重新开始"),
        "challenge": (
            "项目难点",
            "核心难点",
            "难点摘要",
            "问题背景",
            "最大技术难点",
        ),
        "result": (
            "项目成果",
            "成果摘要",
            "最终状态",
            "项目状态",
            "内部测试",
            "公开数据边界",
            "当前不可公开的量化数据",
        ),
        "project_overview": ("项目概述", "项目背景", "核心功能", "项目状态"),
    }
    relevant_kinds = kinds_by_intent.get(intent_name, ())
    document_boosts = {document_id: 4.0 for document_id in project.document_ids}
    for document_id in project.document_ids:
        if any(document_id.endswith(f"-{kind}") for kind in relevant_kinds):
            document_boosts[document_id] = 10.0

    expanded_terms = (
        project.project_id,
        *project.aliases,
        *intent.expanded_terms,
        *generic_terms_by_intent.get(intent_name, ()),
    )
    return RetrievalIntent(
        name=intent_name,
        project_id=project.project_id,
        allowed_document_ids=project.document_ids,
        expanded_terms=tuple(dict.fromkeys(expanded_terms)),
        document_boosts=document_boosts,
        heading_keywords=tuple(
            dict.fromkeys((*intent.heading_keywords, *generic_terms_by_intent.get(intent_name, ())))
        ),
        content_keywords=(),
    )


def _has_query_anchor_evidence(
    question: str,
    intent: RetrievalIntent,
    results: Sequence[SearchResult],
) -> bool:
    if intent.name != "generic":
        return True
    if not results or max(result.score for result in results) < GENERIC_EVIDENCE_MIN_SCORE:
        return False
    normalized = question.lower()
    credential_signals = ("证书", "认证", "certificate", "certification", "credential")
    identifier_signals = ("编号", "号码", "number", " id")
    if not (
        any(signal in normalized for signal in credential_signals)
        and any(signal in normalized for signal in identifier_signals)
    ):
        return True
    anchors = {
        anchor.lower()
        for anchor in LATIN_QUERY_ANCHOR_RE.findall(question)
        if anchor.lower() not in GENERIC_LATIN_ANCHORS
    }
    if not anchors:
        return True
    evidence = " ".join(result.chunk.search_text.lower() for result in results)
    return any(anchor in evidence for anchor in anchors)


def _select_evidence(results: Sequence[SearchResult], limit: int) -> list[SearchResult]:
    if limit <= 0:
        return []
    return list(results[:limit])


def _compose_answer(question: str, results: list[SearchResult], intent: RetrievalIntent) -> str:
    first_person = wants_first_person_response(question)
    lead = "根据当前公开知识库，可以确认："
    if first_person:
        lead = "根据当前公开知识库，可以这样以候选人口吻表述："
    elif "负责" in question or "贡献" in question:
        lead = "根据当前公开知识库，周逢森在这个项目中的工作可以概括为："
    elif "难点" in question or "根因" in question or "权限" in question:
        lead = "根据当前公开知识库，这个问题的核心在于："

    summary = _template_summary(intent, first_person=first_person)
    evidence_title = "证据片段："
    bullets = []
    for index, result in enumerate(results[:6], start=1):
        heading = " > ".join(result.chunk.heading_path) or result.chunk.document_title
        bullets.append(f"{index}. {heading}：{_excerpt(result.chunk.content, 220)}")
    parts = [lead]
    if summary:
        parts.append(summary)
    parts.append(evidence_title)
    parts.extend(bullets)
    return "\n".join(parts)


def _template_summary(intent: RetrievalIntent, *, first_person: bool = False) -> str:
    if intent.name == "project_overview":
        if intent.project_id == "self-introduction-agentic-rag":
            if first_person:
                return (
                    "这个 Agentic RAG 个人经历助手不是普通个人主页，而是我围绕个人经历知识库"
                    "开发的 Agentic RAG 工程作品。它体现的工程能力包括知识治理、检索与引用、"
                    "问题路由、真实 LLM 生成、质量评测和最小可观测性。"
                    "当前项目已完成本地 RAG 闭环、Web 展示、真实 LLM Provider、评测和 Trace；"
                    "线上生产部署仍是后续阶段。"
                )
            return (
                "Agentic RAG 个人经历助手不是普通个人主页，而是以个人经历知识库为场景的 "
                "Agentic RAG 工程作品。它体现的工程能力包括知识治理、检索与引用、"
                "问题路由、真实 LLM 生成、质量评测和最小可观测性。"
                "当前项目已完成本地 RAG 闭环、Web 展示、真实 LLM Provider、评测和 Trace；"
                "线上生产部署仍是后续阶段。"
            )
        if intent.project_id in (None, "skillvar"):
            if first_person:
                return (
                    "我的代表项目 Skillvar 是企业内部 AI Agent Skill 资产平台，"
                    "围绕 Skill 的采集、治理、检索、分发和安装闭环，"
                    "帮助组织分散的 Skill 资产并支持企业内部复用。"
                )
            return (
                "Skillvar 是企业内部 AI Agent Skill 资产平台，"
                "围绕 Skill 的采集、治理、检索、分发和安装闭环，"
                "帮助组织分散的 Skill 资产并支持企业内部复用。"
            )
        if intent.project_id == "ontocore":
            return (
                "OntoCore 是成都盈狐科技有限公司的数据治理与知识图谱平台项目，"
                "面向法律文书、债权资产核查和企业审计等场景，"
                "重点链路包括可信字段、可信实体、可信关系、Neo4j 图谱和 AI 查询。"
                "周逢森在其中负责多租户业务模型、Neo4j 图谱、AI 查询、系统检测和身份权限相关链路。"
            )
        return ""
    if intent.name == "project_problem":
        if intent.project_id == "self-introduction-agentic-rag":
            return (
                "这个项目主要解决普通简历难以验证、项目经历难以追溯、"
                "AI 回答容易缺少证据的问题。"
            )
        if intent.project_id in (None, "skillvar"):
            return (
                "它主要解决组织分散的 Skill 资产难以治理加工、"
                "检索复用和企业内部复用的问题。"
            )
        if intent.project_id == "ontocore":
            return (
                "它主要解决文档治理后的可信数据如何沉淀、可信字段和可信关系如何进入知识图谱，"
                "以及 AI 查询如何在权限范围内使用数据库、Markdown 和 Neo4j 图谱证据的问题。"
            )
        return ""
    if intent.name == "project_goal":
        if intent.project_id == "self-introduction-agentic-rag":
            return (
                "项目目标是把公开个人资料、简历和项目经历整理为可检索知识库，"
                "通过 RAG、路由、引用、拒答和评测形成可演示的 AI 应用闭环。"
            )
        if intent.project_id in (None, "skillvar"):
            return (
                "项目目标包括 Skill 采集入库、搜索与推荐、安装使用和企业共享，"
                "并把治理、检索、分发链路串成闭环。"
            )
        if intent.project_id == "ontocore":
            return (
                "项目目标是把文档处理、字段审核、可信实体、可信关系、Neo4j 图谱、"
                "权限体系和 AI 查询串成数据治理与知识图谱平台能力。"
            )
        return ""

    if intent.project_id == "self-introduction-agentic-rag":
        if first_person:
            first_person_project_summaries = {
                "architecture": (
                    "这个项目采用 Next.js + FastAPI 的前后端分离架构。"
                    "我的核心链路是：公开 Markdown 知识库经过 Front Matter 校验和 Chunk 切分，"
                    "再由 BM25 或 PostgreSQL + pgvector 检索，经过 Router、Intent、项目作用域"
                    "和 Evidence Policy，最后交给确定性回答器或真实 LLM 生成回答，"
                    "并返回引用和 Trace。"
                ),
                "feature_list": (
                    "这个个人经历 AI 助手已经实现知识库治理、公开文档过滤、Chunk 切分、"
                    "BM25/pgvector 检索、E5 Embedding、Router、Evidence Policy、真实 LLM 生成、"
                    "SSE 流式 Web、引用卡片、自动化评测和最小 Trace。"
                    "它不包含商业 SaaS、多租户、联网搜索或已上线生产数据。"
                ),
                "data_flow": (
                    "这个项目的数据流是从 Next.js 聊天页面进入 FastAPI，"
                    "由 RagService 完成 Route、Intent 和项目作用域判断，"
                    "再调用 SearchBackend 检索公开 Chunk，经过 Evidence Policy 过滤后，"
                    "由 AnswerGenerator 生成回答，最后通过 JSON 或 SSE 返回文本、引用和拒答状态。"
                ),
                "responsibility": (
                    "我主导这个项目的定位、需求边界、技术取舍、知识库事实审核和运行验证，"
                    "并在 Codex 辅助下完成代码、文档和测试迭代。"
                    "我的职责覆盖知识库治理、后端 RAG、Router、Evidence Policy、LLM Provider、"
                    "Web MVP、自动化评测和非敏感 Trace。"
                ),
                "team_role": (
                    "这是我的个人作品集项目，不是商业团队项目。"
                    "我负责目标设定、边界确认、知识内容审核、运行验证和工程解释，"
                    "开发过程中使用 Codex 辅助实现和迭代。"
                ),
                "team_vs_personal": (
                    "这个项目属于个人作品集项目，周逢森负责项目目标、边界、知识审核、"
                    "运行验证和工程解释；Codex 用于辅助代码、文档和测试迭代。"
                    "不能把它表述成商业团队交付或已有生产运营成果。"
                ),
                "ai_assisted_development": (
                    "我在这个项目中使用 Codex 辅助实现、文档、测试和失败定位；"
                    "项目能力体现为我能设定目标、审查事实边界、验证运行结果，并解释 RAG 链路、"
                    "路由策略、评测指标和当前限制。"
                ),
                "challenge": (
                    "这个项目最核心的难点是让 AI 助手既能自然回答面试问题，又不编造个人事实。"
                    "具体包括 Router 过严或过松、人称混淆、项目知识域与个人资料隔离、"
                    "引用可信度、无证据拒答、真实 LLM 输出约束和不泄露隐私的 Trace。"
                ),
                "result": (
                    "截至 2026 年 7 月 18 日，这个项目已经完成本地 RAG 闭环、Web MVP、"
                    "真实 LLM Provider、pgvector/E5 检索、M5 评测和最小可观测性。"
                    "它适合用于面试展示和本地演示，但尚未完成线上生产部署，也没有公网用户指标。"
                ),
                "reflection": (
                    "这个项目的复盘结论是：代码链路能跑通并不等于 RAG 质量足够，"
                    "知识库完整度、回答人称、项目作用域、拒答边界和回归评测同样关键。"
                    "如果重新开始，我会更早补齐知识库结构、更早确定第三人称默认策略，"
                    "并更早加入负向评测。"
                ),
            }
            if first_person_project_summary := first_person_project_summaries.get(intent.name):
                return first_person_project_summary

        project_summaries = {
            "architecture": (
                "Agentic RAG 个人经历助手采用 Next.js + FastAPI 的前后端分离架构。"
                "核心链路是：公开 Markdown 知识库经过 Front Matter 校验和 Chunk 切分，"
                "再由 BM25 或 PostgreSQL + pgvector 检索，经过 Router、Intent、项目作用域"
                "和 Evidence Policy，最后交给确定性回答器或真实 LLM 生成回答，并返回引用和 Trace。"
            ),
            "feature_list": (
                "这个个人经历 AI 助手已经实现知识库治理、公开文档过滤、Chunk 切分、"
                "BM25/pgvector 检索、E5 Embedding、Router、Evidence Policy、真实 LLM 生成、"
                "SSE 流式 Web、引用卡片、自动化评测和最小 Trace。"
                "它不包含商业 SaaS、多租户、联网搜索或已上线生产数据。"
            ),
            "data_flow": (
                "这个项目的数据流是从 Next.js 聊天页面进入 FastAPI，"
                "由 RagService 完成 Route、Intent 和项目作用域判断，"
                "再调用 SearchBackend 检索公开 Chunk，经过 Evidence Policy 过滤后，"
                "由 AnswerGenerator 生成回答，最后通过 JSON 或 SSE 返回文本、引用和拒答状态。"
            ),
            "responsibility": (
                "周逢森主导这个项目的定位、需求边界、技术取舍、知识库事实审核和运行验证，"
                "并在 Codex 辅助下完成代码、文档和测试迭代。"
                "他的职责覆盖知识库治理、后端 RAG、Router、Evidence Policy、LLM Provider、"
                "Web MVP、自动化评测和非敏感 Trace。"
            ),
            "team_role": (
                "这是周逢森的个人作品集项目，不是商业团队项目。"
                "周逢森负责目标设定、边界确认、知识内容审核、运行验证和工程解释，"
                "开发过程中使用 Codex 辅助实现和迭代。"
            ),
            "team_vs_personal": (
                "这个项目属于个人作品集项目，周逢森负责项目目标、边界、知识审核、"
                "运行验证和工程解释；Codex 用于辅助代码、文档和测试迭代。"
                "不能把它表述成商业团队交付或已有生产运营成果。"
            ),
            "ai_assisted_development": (
                "在这个项目中，周逢森使用 Codex 辅助实现、文档、测试和失败定位；"
                "项目能力体现为他能设定目标、审查事实边界、验证运行结果，并解释 RAG 链路、"
                "路由策略、评测指标和当前限制。"
            ),
            "challenge": (
                "这个项目最核心的难点是让 AI 助手既能自然回答面试问题，又不编造个人事实。"
                "具体包括 Router 过严或过松、人称混淆、项目知识域与个人资料隔离、"
                "引用可信度、无证据拒答、真实 LLM 输出约束和不泄露隐私的 Trace。"
            ),
            "result": (
                "截至 2026 年 7 月 18 日，Agentic RAG 个人经历助手已经完成本地 RAG 闭环、"
                "Web MVP、真实 LLM Provider、pgvector/E5 检索、M5 评测和最小可观测性。"
                "它适合用于面试展示和本地演示，但尚未完成线上生产部署，也没有公网用户指标。"
            ),
            "reflection": (
                "这个项目的复盘结论是：代码链路能跑通并不等于 RAG 质量足够，"
                "知识库完整度、回答人称、项目作用域、拒答边界和回归评测同样关键。"
                "如果重新开始，周逢森会更早补齐知识库结构、更早确定第三人称默认策略，"
                "并更早加入负向评测。"
            ),
        }
        if project_summary := project_summaries.get(intent.name):
            return project_summary

    if intent.project_id == "ontocore":
        ontocore_summaries = {
            "architecture": (
                "OntoCore 的架构可以概括为 Next.js/TypeScript 应用层、MongoDB/Prisma 多租户业务层、"
                "Neo4j 图谱层、AI 查询和系统检测链路。"
                "AI 查询链路支持问题解析、查询计划、技能选择、多源检索、SSE、证据引用和图谱结果。"
                "核心是把可信字段、可信实体和可信关系同步到图谱，再由 AI 查询在 RBAC 权限范围内"
                "使用数据库、Markdown 和 Neo4j 证据。"
            ),
            "feature_list": (
                "OntoCore 的功能覆盖文档治理、可信数据、知识图谱、AI 查询、身份权限和系统检测。"
                "周逢森重点负责多租户业务模型、Neo4j 图谱链路、AI 查询链路、"
                "系统检测链路和登录/RBAC。"
            ),
            "data_flow": (
                "OntoCore 的主数据流是：文档经过 OCR 和 AI 字段抽取形成候选字段，"
                "人工审核后生成可信字段、可信实体和可信关系，随后进入 MongoDB/Prisma 与 Neo4j，"
                "最后供图谱查询和 AI 查询使用。"
                "其中 AI 查询子链路包含问题解析、查询计划、技能选择、多源检索、SSE、"
                "证据引用和图谱结果。"
            ),
            "responsibility": (
                "周逢森在 OntoCore 中负责 MongoDB/Prisma 多租户业务模型、Neo4j 可信实体"
                "和可信关系入图、"
                "图同步、关系树、多跳路径、邻居查询、AI 查询链路、系统检测链路，以及飞书扫码登录、"
                "长期登录态和 RBAC 权限体系。OCR 整体链路、OpenMetadata 整体链路、人工审核前端和"
                "可信关联关系整体规则体系不表述为他独立主导。"
            ),
            "team_role": (
                "OntoCore 是团队项目。周逢森的角色是项目开发工程师/算法实习生，"
                "个人主线是多租户模型、Neo4j 图谱、AI 查询、系统检测和身份权限；"
                "OCR、OpenMetadata、人工审核和可信关联关系整体流程属于团队链路或参与但不主导范围。"
            ),
            "team_vs_personal": (
                "个人层面，周逢森负责多租户模型、Neo4j 图谱、AI 查询、系统检测和身份权限相关链路；"
                "团队层面，OntoCore 还包含 OCR、AI 字段抽取、人工审核、OpenMetadata "
                "和可信关联关系等整体链路。"
                "公开回答中应区分个人职责和团队成果。"
            ),
            "negative_responsibility": (
                "OntoCore 中不应表述为周逢森主导的部分包括 OCR 整体链路、OpenMetadata 整体链路、"
                "人工审核前端，以及可信关联关系的产品流程和整体规则体系。"
                "他负责的是这些可信数据进入 Neo4j 和 AI 查询后的同步、查询、权限与使用链路。"
            ),
            "challenge": (
                "OntoCore 最有代表性的难点是 Neo4j 知识图谱不能只依赖可信字段，"
                "还需要可信关联关系。字段只能说明文档里出现了什么，图谱则要表达谁和谁是什么关系。"
                "在固定文档类型下，可以根据审核后的字段配置关系规则，先生成候选关系，"
                "再审核为可信关系并同步到 Neo4j。"
            ),
            "result": (
                "OntoCore 仍是开发中的团队项目，目前没有可公开业务成果或量化指标。"
                "可以公开说明周逢森参与并负责的工程模块，包括多租户模型、Neo4j 图谱、AI 查询、"
                "系统检测和身份权限；不能编造用户规模、准确率、性能或商业成果。"
            ),
            "reflection": (
                "OntoCore 的复盘价值在于让周逢森把可信数据治理、知识图谱、AI 查询"
                "和权限隔离放在同一条链路里理解。"
                "项目提醒他：企业数据问答不能只依赖模型生成，必须先处理字段可信、"
                "关系可信、图同步和访问权限。"
            ),
        }
        if ontocore_summary := ontocore_summaries.get(intent.name):
            return ontocore_summary

    if intent.project_id not in (None, "skillvar"):
        return ""

    if first_person:
        first_person_summaries = {
            "profile_introduction": (
                "我叫周逢森，是南宁理工学院人工智能专业的 2026 届本科应届生，"
                "求职方向是大模型应用开发、AI 应用开发和 AI 后端开发。"
                "我主要使用 Python、FastAPI、MongoDB 以及 RAG、Agent 等技术开发 AI 应用；"
                "代表实践包括企业 AI Skill 资产平台 Skillvar。"
            ),
            "identity": (
                "我叫周逢森，是南宁理工学院人工智能专业的 2026 届本科应届生。"
            ),
            "education": (
                "我就读于南宁理工学院人工智能专业，是 2026 届本科应届生，"
                "学习时间为 2022 年 9 月至 2026 年 6 月。课程与项目实践覆盖编程、数据库、"
                "机器学习、深度学习、计算机视觉和自然语言处理，并延伸到当前应聘的 AI 应用方向。"
            ),
            "skills_profile": (
                "我的核心技术栈包括 Python、FastAPI、MongoDB、RAG 和 Agent，"
                "这些能力有 Skillvar、OntoCore 等项目经历支撑。"
                "PyTorch、Transformer、机器学习和深度学习属于基础了解；"
                "Kafka、Redis、MinIO 等组件不能全部表述为我的个人核心实现。"
            ),
            "career_direction": (
                "我希望寻找大模型应用开发、AI 应用开发或 AI 后端开发方向的工作。"
            ),
            "personal_strengths": (
                "我较突出的优势是能把 RAG、Agent 与 Python 后端结合到完整 AI 应用中，"
                "并在 Skillvar 等项目中承担模块理解、实现、整合、测试、部署和问题排查。"
            ),
            "job_fit": (
                "我适合 Agent 应用开发工程师岗位的依据主要有三点："
                "具备 RAG、Agent 的项目实践，能够使用 Python 后端与 FastAPI 落地能力，"
                "并承担过从模块整合、测试到部署运维的工程化交付。"
                "这些结论来自现有项目经历，不代表我拥有多年生产经验。"
            ),
            "team_role": (
                "我的角色是算法实习生，负责简历所列后端与 AI 工程模块的实现、整合、测试和部署运维；"
                "产品由其他成员负责，团队规模资料不足，因此不补写具体人数或其他岗位分工。"
            ),
            "responsibility": (
                "我负责简历所列后端与 AI 工程模块，具体包括平台后端、混合检索、"
                "LLM 翻译与 Skill 创作、安全扫描、"
                "MCP 与 CLI、企业协作集成和工程问题处理；我使用 Codex 和 GLM-5.2 辅助开发，"
                "本人负责理解、集成、调试、测试和部署，并负责测试和部署运维。"
                "其中一个关键贡献是解决 GitLab 仓库层级权限隔离。"
            ),
            "team_vs_personal": (
                "团队层面，产品工作由团队其他成员负责，项目整体业务成果属于团队；"
                "个人层面，本人负责简历所列模块的开发、整合、测试和部署运维，"
                "并借助 AI 工具完成实现迭代。换句话说，产品由团队其他成员负责，"
                "简历所列模块由本人借助 AI 工具完成。已完成功能用于内部测试。"
            ),
            "negative_responsibility": (
                "产品需求与产品工作不是本人负责；当前资料对 UI 和其他研发角色资料不足，"
                "不能把这些工作补写为我的职责。"
            ),
            "challenge": (
                "最大技术难点是 GitLab 仓库层级关系权限隔离：父 Group 权限向 Subgroup 和仓库继承，"
                "也就是父级权限继承会破坏不同用户私有 Skill 隔离。"
                "定位时发现用户创建了私有组织仓库后，"
                "其他父级 Group 用户仍能进入私有组织仓库，"
                "也可以说父级 Group 的其他用户仍能继承进入，"
                "仓库 private 属性不是根因；根因是 GitLab 父组权限向下继承，"
                "也可以表述为父级成员权限向下继承，"
                "根因是父级成员权限向 Subgroup 和 Repository 下传。"
                "解决上，我采用权限模型调整而不是界面侧规避，"
                "而是让普通用户不在私有父 Group 授权，每个用户使用独立私有 Subgroup，"
                "也就是每个用户独立私有 Subgroup；"
                "由 Bot 维护、用户直接获得自己 Subgroup 的开发权限，"
                "也就是用户直接获得自己 Subgroup 权限，"
                "并复用已有 Subgroup 映射，也就是复用 Subgroup 映射，"
                "兼容并发创建竞态、成员已存在、继承权限冲突，"
                "即复用 Subgroup 映射并兼容成员已存在和继承权限冲突，"
                "实现幂等兼容和公有与私有路径分离。"
            ),
            "ai_assisted_development": (
                "我使用 Codex 和 GLM-5.2 辅助编程、代码理解和实现迭代；"
                "理解、集成、调试、测试、部署和验证由本人负责。"
                "这不能表述为所有代码纯手写，也不能说由 AI 直接完成所有交付。"
            ),
            "engineering_delivery": (
                "我承担本人开发功能的测试、业务侧部署运维，"
                "也处理过环境变量和远程仓库问题排查；相关功能已部署用于内部测试。"
            ),
            "llm_pipeline": (
                "LLM 链路包括 OpenAI 兼容接口、DashScope/Qwen、Markdown 结构保护、"
                "术语库、分块翻译、缓存复用和 Skill 草稿生成。"
            ),
            "safety_governance": (
                "安全治理通过规则库静态扫描对 Skill 内容分类，结果包括 safe、warning、danger，"
                "并写回 MongoDB 供后续展示和治理使用。"
            ),
        }
        if first_person_summary := first_person_summaries.get(intent.name):
            return first_person_summary

    summaries = {
        "profile_introduction": (
            "周逢森是南宁理工学院人工智能专业的 2026 届本科应届生，"
            "求职方向是大模型应用开发、AI 应用开发和 AI 后端开发。"
            "他主要使用 Python、FastAPI、MongoDB 以及 RAG、Agent 等技术开发 AI 应用；"
            "代表实践包括企业 AI Skill 资产平台 Skillvar。"
        ),
        "identity": (
            "候选人叫周逢森，是南宁理工学院人工智能专业的 2026 届本科应届生。"
        ),
        "education": (
            "周逢森就读于南宁理工学院人工智能专业，是 2026 届本科应届生，"
            "学习时间为 2022 年 9 月至 2026 年 6 月。课程与项目实践覆盖编程、数据库、"
            "机器学习、深度学习、计算机视觉和自然语言处理，并延伸到当前应聘的 AI 应用方向。"
        ),
        "skills_profile": (
            "周逢森的核心技术栈包括 Python、FastAPI、MongoDB、RAG 和 Agent，"
            "这些能力有 Skillvar、OntoCore 等项目经历支撑。"
            "PyTorch、Transformer、机器学习和深度学习属于基础了解；"
            "Kafka、Redis、MinIO 等组件不能全部表述为他的个人核心实现。"
        ),
        "career_direction": (
            "周逢森希望寻找大模型应用开发、AI 应用开发或 AI 后端开发方向的工作。"
        ),
        "personal_strengths": (
            "周逢森较突出的优势是能把 RAG、Agent 与 Python 后端结合到完整 AI 应用中，"
            "并在 Skillvar 等项目中承担模块理解、实现、整合、测试、部署和问题排查。"
        ),
        "job_fit": (
            "周逢森适合 Agent 应用开发工程师岗位的依据主要有三点："
            "具备 RAG、Agent 的项目实践，能够使用 Python 后端与 FastAPI 落地能力，"
            "并承担过从模块整合、测试到部署运维的工程化交付。"
            "这些结论来自现有项目经历，不代表他拥有多年生产经验。"
        ),
        "team_role": (
            "周逢森的角色是算法实习生，负责简历所列后端与 AI 工程模块的实现、整合、测试和部署运维；"
            "产品由其他成员负责，团队规模资料不足，因此不补写具体人数或其他岗位分工。"
        ),
        "responsibility": (
            "周逢森负责简历所列后端与 AI 工程模块，具体包括平台后端、混合检索、"
            "LLM 翻译与 Skill 创作、安全扫描、"
            "MCP 与 CLI、企业协作集成和工程问题处理；他使用 Codex 和 GLM-5.2 辅助开发，"
            "周逢森负责理解、集成、调试、测试和部署，"
            "也可以说本人负责理解、集成、调试、测试和部署，并负责测试和部署运维。"
            "其中一个关键贡献是解决 GitLab 仓库层级权限隔离。"
        ),
        "team_vs_personal": (
            "团队层面，产品工作由团队其他成员负责，项目整体业务成果属于团队；"
            "个人层面，本人负责简历所列模块的开发、整合、测试和部署运维，"
            "并借助 AI 工具完成实现迭代。换句话说，产品由团队其他成员负责，"
            "简历所列模块由本人借助 AI 工具完成。已完成功能用于内部测试。"
        ),
        "negative_responsibility": (
            "产品需求与产品工作不是周逢森负责；当前资料对 UI 和其他研发角色资料不足，"
            "不能把这些工作补写为他的职责。也可以说，产品需求与产品工作不是本人负责。"
        ),
        "architecture": (
            "整体上，Skillvar 由 Streamlit Web、FastAPI REST API、services 业务层、"
            "MongoDB、MCP Server 和 CLI 组成；"
            "核心请求一般从入口层进入，调用 services 业务能力，读写 MongoDB，"
            "再返回 Web、API、MCP 或 CLI。"
            "主要技术上，FastAPI 提供 API 与集成入口，Streamlit 提供 Web 界面，"
            "MongoDB 保存业务数据，"
            "BM25 与 ChromaDB 用于检索，DashScope/Qwen 用于翻译和生成，MCP 与 CLI 用于分发。"
        ),
        "mcp_cli": (
            "平台通过 MCP Server 和 npm CLI 把搜索、详情、安装、卸载、推荐、创建、优化"
            "和团队共享等能力"
            "提供给 Agent 工作流和命令行用户，支持命令行安装使用。"
        ),
        "retrieval_fallback": (
            "检索链路中 ChromaDB 是可选语义召回通道；"
            "ChromaDB 不可用时自动退化为 BM25-only，BM25 未建立时使用 MongoDB 正则搜索兜底。"
        ),
        "feature_list": (
            "Skillvar 的功能可以概括为 AI Skill 资产生命周期闭环：采集、提交、自然语言创建、"
            "翻译、安全扫描、质量评分、混合检索、详情下载、安装、团队/公司共享、"
            "MCP 与 CLI 分发、飞书/GitLab 企业协作，以及行为日志和 Token 用量统计。"
            "这些能力已有源码实现和公开知识库证据，但不能补充未授权的规模、性能或效果指标。"
        ),
        "data_flow": (
            "Skillvar 的调用链整体是多入口复用服务层："
            "Web、FastAPI、MCP、CLI、飞书和 GitLab Webhook "
            "作为入口层进入系统后，主要调用 services 业务能力，再读写 MongoDB，"
            "并联动搜索索引、翻译缓存、安全扫描记录、团队共享和行为日志，"
            "最后返回 Web、API、MCP 或 CLI。不同模块可以按采集入库、创建、翻译、"
            "检索、安全扫描、GitLab 同步和 MCP/CLI 分发分别展开。"
        ),
        "reflection": (
            "从工程复盘看，Skillvar 的亮点是形成了较完整的 AI Skill 生命周期闭环、"
            "多入口复用服务层、检索降级策略、LLM 结构保护和 GitLab 权限隔离实践。"
            "主要不足包括历史兼容代码带来的技术债、ChromaDB Embedding 配置不够显式、"
            "Webhook 幂等和失败恢复仍需加强、安全扫描仍以静态规则为主、自动化测试还可以更细粒度。"
        ),
        "challenge": (
            "最大技术难点是 GitLab 仓库层级关系权限隔离：父 Group 权限向 Subgroup 和仓库继承，"
            "也就是父级权限继承会破坏不同用户私有 Skill 隔离。"
            "定位时发现用户创建了私有组织仓库后，"
            "其他父级 Group 用户仍能进入私有组织仓库，"
            "也可以说父级 Group 的其他用户仍能继承进入，"
            "仓库 private 属性不是根因；根因是 GitLab 父组权限向下继承，"
            "也可以表述为父级成员权限向下继承，"
            "根因是父级成员权限向 Subgroup 和 Repository 下传。"
            "解决上，周逢森采用权限模型调整而不是界面侧规避，"
            "而是让普通用户不在私有父 Group 授权，每个用户使用独立私有 Subgroup，"
            "也就是每个用户独立私有 Subgroup；"
            "由 Bot 维护、用户直接获得自己 Subgroup 的开发权限，"
            "也就是用户直接获得自己 Subgroup 权限，"
            "并复用已有 Subgroup 映射，也就是复用 Subgroup 映射，"
            "兼容并发创建竞态、成员已存在、继承权限冲突，"
            "即复用 Subgroup 映射并兼容成员已存在和继承权限冲突，"
            "实现幂等兼容和公有与私有路径分离。"
        ),
        "result": (
            "Skillvar 形成采集、治理、检索和安装闭环，提供 MCP Server 与 npm CLI，"
            "支持企业共享与版本追踪；"
            "开发完成的功能均已部署用于内部测试。Skillvar 当前是内测版本，"
            "当前没有允许公开的性能、规模或效果数据，不能编造指标，"
            "也不能给出精确提升数字。"
        ),
        "ai_assisted_development": (
            "周逢森使用 Codex 和 GLM-5.2 辅助编程、代码理解和实现迭代；"
            "理解、集成、调试、测试、部署和验证由本人负责。"
            "这不能表述为所有代码纯手写，也不能说由 AI 直接完成所有交付。"
        ),
        "engineering_delivery": (
            "周逢森承担本人开发功能的测试、业务侧部署运维，"
            "也处理过环境变量和远程仓库问题排查；相关功能已部署用于内部测试。"
        ),
        "llm_pipeline": (
            "LLM 链路包括 OpenAI 兼容接口、DashScope/Qwen、Markdown 结构保护、"
            "术语库、分块翻译、缓存复用和 Skill 草稿生成。"
        ),
        "safety_governance": (
            "安全治理通过规则库静态扫描对 Skill 内容分类，结果包括 safe、warning、danger，"
            "并写回 MongoDB 供后续展示和治理使用。"
        ),
    }
    return summaries.get(intent.name, "")


def _excerpt(text: str, limit: int = 180) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"


def _stream_chunks(text: str, chunk_size: int = 24) -> list[str]:
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)] or [""]
