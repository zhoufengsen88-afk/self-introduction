export type StreamEvent =
  | { event: "delta"; data: { content: string } }
  | {
      event: "done";
      data: {
        finish_reason: string;
        refused: boolean;
        refusal_reason: string | null;
        citations: Array<{
          chunk_id: string;
          document_id: string;
          document_title: string;
          heading_path: string[];
          score: number | null;
          excerpt: string | null;
        }>;
      };
    }
  | { event: "error"; data: { message: string; code?: string } }
  | { event: string; data: unknown };

export function parseSseFrames(buffer: string): { events: StreamEvent[]; rest: string } {
  const events: StreamEvent[] = [];
  let rest = buffer;
  let boundary = rest.indexOf("\n\n");
  while (boundary !== -1) {
    const frame = rest.slice(0, boundary);
    rest = rest.slice(boundary + 2);
    let event = "message";
    let data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) {
        event = line.slice("event:".length).trim();
      }
      if (line.startsWith("data:")) {
        data += line.slice("data:".length).trim();
      }
    }
    events.push({ event, data: data ? JSON.parse(data) : {} } as StreamEvent);
    boundary = rest.indexOf("\n\n");
  }
  return { events, rest };
}
