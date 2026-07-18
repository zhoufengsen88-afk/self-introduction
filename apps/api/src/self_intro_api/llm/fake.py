from collections.abc import AsyncIterator

from self_intro_api.schemas.chat import ChatRequest, ChatResponse, Citation


class FakeLLMProvider:
    async def answer(self, request: ChatRequest) -> ChatResponse:
        if "忽略之前的规则" in request.message or "隐藏资料" in request.message:
            return ChatResponse(
                answer="这个问题涉及隐藏资料或系统规则，我不能回答。",
                citations=[],
                refused=True,
                refusal_reason="restricted_content",
            )

        citation = Citation(
            chunk_id="m2-fake-provider--contract--001",
            document_id="m2-fake-provider",
            document_title="M2 Fake Provider",
        )
        return ChatResponse(
            answer=(
                "这是 M2 工程骨架中的 Fake Provider 回答。"
                "它用于验证流式接口、前端消费和测试契约，真实 LLM 生成会在后续阶段接入。"
            ),
            citations=[citation],
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[dict[str, object]]:
        response = await self.answer(request)
        for index in range(0, len(response.answer), 18):
            yield {"event": "delta", "data": {"content": response.answer[index : index + 18]}}
        yield {
            "event": "done",
            "data": {
                "finish_reason": "stop",
                "refused": response.refused,
                "refusal_reason": response.refusal_reason,
                "citations": [item.model_dump() for item in response.citations],
            },
        }
