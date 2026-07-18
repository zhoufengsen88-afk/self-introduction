import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .events import encode_sse


app = FastAPI(title="M1 SSE Spike")
STREAM_STATE: Dict[str, Dict[str, Any]] = {}
HTML_PATH = Path(__file__).with_name("browser_client.html")


class StreamRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    chunks: int = Field(default=4, ge=1, le=100)
    delay_ms: int = Field(default=20, ge=0, le=1000)
    fail_at: Optional[int] = Field(default=None, ge=0)
    cancel_at: Optional[int] = Field(default=None, ge=0)


def _new_state(payload: StreamRequest) -> Dict[str, Any]:
    state = {
        "session_id": payload.session_id,
        "started": True,
        "completed": False,
        "cancelled": False,
        "error": None,
        "events": [],
        "started_at": time.time(),
        "finished_at": None,
    }
    STREAM_STATE[payload.session_id] = state
    return state


def _tokens(message: str, chunks: int) -> List[str]:
    words = message.strip().split()
    if not words:
        words = ["empty"]
    return [f"{words[index % len(words)]}-{index + 1}" for index in range(chunks)]


async def event_stream(payload: StreamRequest, request: Request):
    state = _new_state(payload)
    try:
        for index, token in enumerate(_tokens(payload.message, payload.chunks)):
            if await request.is_disconnected():
                state["cancelled"] = True
                return

            if payload.cancel_at is not None and index == payload.cancel_at:
                state["cancelled"] = True
                state["events"].append("cancelled")
                yield encode_sse(
                    "cancelled",
                    {
                        "session_id": payload.session_id,
                        "reason": "server_cancelled",
                        "index": index,
                    },
                    event_id=f"{payload.session_id}:cancelled",
                )
                return

            if payload.fail_at is not None and index == payload.fail_at:
                raise RuntimeError("simulated stream failure")

            if payload.delay_ms:
                await asyncio.sleep(payload.delay_ms / 1000)

            state["events"].append("delta")
            yield encode_sse(
                "delta",
                {
                    "session_id": payload.session_id,
                    "index": index,
                    "content": token,
                },
                event_id=f"{payload.session_id}:{index}",
            )

        state["completed"] = True
        state["events"].append("done")
        yield encode_sse(
            "done",
            {"session_id": payload.session_id, "finish_reason": "stop"},
            event_id=f"{payload.session_id}:done",
        )
    except asyncio.CancelledError:
        state["cancelled"] = True
        raise
    except Exception as exc:
        state["error"] = str(exc)
        state["events"].append("error")
        yield encode_sse(
            "error",
            {
                "session_id": payload.session_id,
                "code": "stream_error",
                "message": str(exc),
            },
            event_id=f"{payload.session_id}:error",
        )
    finally:
        state["finished_at"] = time.time()


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/")
async def browser_client():
    return HTMLResponse(HTML_PATH.read_text(encoding="utf-8"))


@app.post("/stream")
async def stream(payload: StreamRequest, request: Request):
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_stream(payload, request),
        media_type="text/event-stream",
        headers=headers,
    )


@app.get("/debug/sessions/{session_id}")
async def debug_session(session_id: str):
    state = STREAM_STATE.get(session_id)
    if not state:
        return JSONResponse({"found": False}, status_code=404)
    return {"found": True, **state}


@app.post("/debug/reset")
async def debug_reset():
    STREAM_STATE.clear()
    return {"ok": True}
