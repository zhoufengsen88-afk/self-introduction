import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import httpx

from self_intro_api.llm.base import LLMMessage, LLMStreamChunk, LLMUsage


@dataclass(frozen=True)
class OpenAICompatibleLLMProvider:
    base_url: str
    model: str
    api_key: str = ""
    temperature: float = 0.2
    timeout_seconds: float = 30.0
    transport: httpx.AsyncBaseTransport | None = None

    async def stream_chat(self, messages: Sequence[LLMMessage]) -> AsyncIterator[str]:
        async for chunk in self.stream_chat_with_usage(messages):
            if chunk.content:
                yield chunk.content

    async def stream_chat_with_usage(
        self,
        messages: Sequence[LLMMessage],
    ) -> AsyncIterator[LLMStreamChunk]:
        if not self.base_url:
            raise ValueError("LLM_BASE_URL is required when ANSWER_GENERATOR=llm")
        if not self.model:
            raise ValueError("LLM_MODEL is required when ANSWER_GENERATOR=llm")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "temperature": self.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            transport=self.transport,
        ) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    chunk = _parse_sse_line(line)
                    if chunk is None:
                        continue
                    if chunk == "[DONE]":
                        break
                    usage = _extract_usage(chunk)
                    if usage is not None:
                        yield LLMStreamChunk(usage=usage)
                    content = _extract_delta_content(chunk)
                    if content:
                        yield LLMStreamChunk(content=content)


def _parse_sse_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("data:"):
        return stripped.removeprefix("data:").strip()
    return None


def _extract_delta_content(raw_payload: str) -> str:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return ""

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""

    delta = first_choice.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        return content if isinstance(content, str) else ""

    message = first_choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        return content if isinstance(content, str) else ""

    return ""


def _extract_usage(raw_payload: str) -> LLMUsage | None:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None

    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None

    prompt_tokens = _int_usage_value(usage.get("prompt_tokens"))
    completion_tokens = _int_usage_value(usage.get("completion_tokens"))
    total_tokens = _int_usage_value(usage.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    if prompt_tokens == completion_tokens == total_tokens == 0:
        return None
    return LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated=False,
    )


def _int_usage_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0
