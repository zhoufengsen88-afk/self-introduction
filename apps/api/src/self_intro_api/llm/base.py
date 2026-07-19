from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

LLMRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class LLMMessage:
    role: LLMRole
    content: str


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated: bool = False


@dataclass(frozen=True)
class LLMStreamChunk:
    content: str = ""
    usage: LLMUsage | None = None


class LLMProvider(Protocol):
    def stream_chat(self, messages: Sequence[LLMMessage]) -> AsyncIterator[str]:
        """Stream text chunks from a chat-completion compatible model."""
        ...


class LLMUsageStreamingProvider(Protocol):
    def stream_chat_with_usage(
        self,
        messages: Sequence[LLMMessage],
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream text chunks and optional provider token usage."""
        ...
