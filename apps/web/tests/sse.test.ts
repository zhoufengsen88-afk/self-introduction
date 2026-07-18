import { describe, expect, it } from "vitest";
import { parseSseFrames } from "../lib/sse";

describe("parseSseFrames", () => {
  it("returns parsed events and trailing partial frame", () => {
    const result = parseSseFrames(
      'event: delta\ndata: {"content":"你好"}\n\n' +
        'event: done\ndata: {"finish_reason":"stop","refused":false,"refusal_reason":null,"citations":[]}\n\n' +
        "event: delta\n",
    );

    expect(result.events).toHaveLength(2);
    expect(result.events[0]).toEqual({ event: "delta", data: { content: "你好" } });
    expect(result.events[1].event).toBe("done");
    expect(result.rest).toBe("event: delta\n");
  });
});
