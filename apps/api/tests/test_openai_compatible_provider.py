import json
from collections.abc import Iterator

import httpx
import pytest
from self_intro_api.llm.base import LLMMessage
from self_intro_api.llm.openai_compatible import OpenAICompatibleLLMProvider


def _sse_frames(payloads: Iterator[dict[str, object] | str]) -> bytes:
    lines = []
    for payload in payloads:
        data = payload if isinstance(payload, str) else json.dumps(payload)
        lines.append(f"data: {data}\n")
    return "\n".join(lines).encode()


@pytest.mark.asyncio
async def test_openai_compatible_provider_streams_delta_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.test/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-v4-flash"
        return httpx.Response(
            200,
            content=_sse_frames(
                iter(
                    (
                        {"choices": [{"delta": {"content": "你好"}}]},
                        {"choices": [{"delta": {"content": "，面试官"}}]},
                        "[DONE]",
                    )
                )
            ),
            request=request,
        )

    provider = OpenAICompatibleLLMProvider(
        base_url="https://example.test/v1",
        model="deepseek-v4-flash",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    chunks = [
        chunk
        async for chunk in provider.stream_chat(
            [LLMMessage(role="user", content="介绍一下 Skillvar")]
        )
    ]

    assert chunks == ["你好", "，面试官"]
