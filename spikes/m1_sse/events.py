import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class SseEvent:
    event: str
    data: Dict[str, Any]
    event_id: Optional[str] = None


def encode_sse(event: str, data: Dict[str, Any], event_id: Optional[str] = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for line in payload.splitlines() or [""]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def parse_sse_frame(frame: str) -> SseEvent:
    event = "message"
    event_id = None
    data_lines = []
    for line in frame.splitlines():
        if not line or line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event = value
        elif field == "id":
            event_id = value
        elif field == "data":
            data_lines.append(value)
    data = json.loads("\n".join(data_lines)) if data_lines else {}
    return SseEvent(event=event, data=data, event_id=event_id)
