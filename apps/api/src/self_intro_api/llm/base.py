from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

LLMRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class LLMMessage:
    role: LLMRole
    content: str


class LLMProvider(Protocol):
    def stream_chat(self, messages: Sequence[LLMMessage]) -> AsyncIterator[str]:
        """Stream text chunks from a chat-completion compatible model."""
        ...
