const baseUrl = process.argv[2] ?? "http://127.0.0.1:8010";
const mode = process.argv[3] ?? "normal";

function parseFrames(buffer, onEvent) {
  let boundary = buffer.indexOf("\n\n");
  while (boundary !== -1) {
    const frame = buffer.slice(0, boundary);
    buffer = buffer.slice(boundary + 2);
    const event = { event: "message", data: "" };
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event.event = line.slice(6).trim();
      if (line.startsWith("data:")) event.data += line.slice(5).trim();
    }
    if (event.data) event.data = JSON.parse(event.data);
    onEvent(event);
    boundary = buffer.indexOf("\n\n");
  }
  return buffer;
}

const payload = {
  message: "Skillvar SSE fetch client",
  chunks: 4,
  delay_ms: 20,
};
if (mode === "error") payload.fail_at = 1;
if (mode === "cancelled") payload.cancel_at = 1;
if (mode === "client-cancel") {
  payload.chunks = 50;
  payload.delay_ms = 100;
}

const controller = new AbortController();
const response = await fetch(`${baseUrl}/stream`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
  signal: controller.signal,
});

const contentType = response.headers.get("content-type") ?? "";
if (!contentType.startsWith("text/event-stream")) {
  throw new Error(`expected text/event-stream, got ${contentType}`);
}

const events = [];
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
let sessionId = null;
try {
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = parseFrames(buffer, (event) => {
      events.push(event);
      sessionId = event.data.session_id ?? sessionId;
      if (mode === "client-cancel" && event.event === "delta") {
        controller.abort();
      }
    });
  }
} catch (error) {
  if (mode !== "client-cancel" || error.name !== "AbortError") {
    throw error;
  }
}

let debug = null;
if (mode === "client-cancel" && sessionId) {
  const deadline = Date.now() + 3000;
  while (Date.now() < deadline) {
    debug = await fetch(`${baseUrl}/debug/sessions/${sessionId}`).then((item) => item.json());
    if (debug.cancelled) break;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}

console.log(JSON.stringify({ mode, events, debug }, null, 2));
