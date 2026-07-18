import json
from collections.abc import AsyncIterator
from typing import Any


def encode_sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


async def encode_event_stream(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    async for item in events:
        event = str(item.get("event", "message"))
        data = item.get("data", {})
        yield encode_sse(event, data if isinstance(data, dict) else {})
