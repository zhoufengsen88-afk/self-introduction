import json
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import Dict, Iterator, List

import httpx

from spikes.m1_sse.events import SseEvent, parse_sse_frame


ROOT = Path(__file__).resolve().parents[3]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def iter_sse_events(response: httpx.Response) -> Iterator[SseEvent]:
    frame_lines: List[str] = []
    for line in response.iter_lines():
        if line:
            frame_lines.append(line)
            continue
        if frame_lines:
            yield parse_sse_frame("\n".join(frame_lines))
            frame_lines = []


class LiveSseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "spikes.m1_sse.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                stdout, stderr = cls.proc.communicate(timeout=1)
                raise RuntimeError(f"uvicorn exited early\nstdout={stdout}\nstderr={stderr}")
            try:
                with httpx.Client(timeout=1) as client:
                    if client.get(f"{cls.base_url}/healthz").json() == {"ok": True}:
                        return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("uvicorn did not become ready")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
            cls.proc.communicate(timeout=5)

    def setUp(self):
        with httpx.Client(timeout=5) as client:
            client.post(f"{self.base_url}/debug/reset")

    def read_until_terminal(self, payload: Dict[str, object]) -> List[SseEvent]:
        events = []
        with httpx.Client(timeout=10) as client:
            with client.stream("POST", f"{self.base_url}/stream", json=payload) as response:
                self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
                self.assertEqual(response.headers["cache-control"], "no-cache")
                for event in iter_sse_events(response):
                    events.append(event)
                    if event.event in {"done", "error", "cancelled"}:
                        break
        return events

    def test_stream_emits_delta_and_done_events(self):
        session_id = "test-normal"
        events = self.read_until_terminal(
            {
                "session_id": session_id,
                "message": "Skillvar SSE",
                "chunks": 3,
                "delay_ms": 5,
            }
        )
        self.assertEqual([event.event for event in events], ["delta", "delta", "delta", "done"])
        self.assertEqual([event.data["index"] for event in events[:-1]], [0, 1, 2])
        with httpx.Client(timeout=5) as client:
            state = client.get(f"{self.base_url}/debug/sessions/{session_id}").json()
        self.assertTrue(state["completed"])
        self.assertFalse(state["cancelled"])

    def test_stream_emits_error_event(self):
        events = self.read_until_terminal(
            {
                "session_id": "test-error",
                "message": "Skillvar SSE",
                "chunks": 4,
                "delay_ms": 5,
                "fail_at": 1,
            }
        )
        self.assertEqual([event.event for event in events], ["delta", "error"])
        self.assertEqual(events[-1].data["code"], "stream_error")

    def test_stream_emits_server_cancelled_event(self):
        events = self.read_until_terminal(
            {
                "session_id": "test-server-cancel",
                "message": "Skillvar SSE",
                "chunks": 4,
                "delay_ms": 5,
                "cancel_at": 1,
            }
        )
        self.assertEqual([event.event for event in events], ["delta", "cancelled"])
        self.assertEqual(events[-1].data["reason"], "server_cancelled")

    def test_client_disconnect_marks_session_cancelled(self):
        session_id = "test-client-cancel"
        with httpx.Client(timeout=10) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/stream",
                json={
                    "session_id": session_id,
                    "message": "Skillvar SSE",
                    "chunks": 50,
                    "delay_ms": 100,
                },
            ) as response:
                first_event = next(iter_sse_events(response))
                self.assertEqual(first_event.event, "delta")

        deadline = time.time() + 3
        last_state = {}
        with httpx.Client(timeout=5) as client:
            while time.time() < deadline:
                last_state = client.get(f"{self.base_url}/debug/sessions/{session_id}").json()
                if last_state.get("cancelled"):
                    break
                time.sleep(0.05)
        self.assertTrue(last_state.get("cancelled"), json.dumps(last_state, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
