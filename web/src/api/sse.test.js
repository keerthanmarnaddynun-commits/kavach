import { describe, it, expect } from "vitest";
import { SSEParser } from "./sse.js";

describe("SSE Parser", () => {
  it("parses progress event with JSON payload", () => {
    const parser = new SSEParser();
    const chunk = "event: progress\ndata: {\"status\": \"running\", \"progress\": {\"done\": 1, \"total\": 2}}\n\n";
    const events = parser.feed(chunk);
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("progress");
    expect(events[0].data).toEqual({
      status: "running",
      progress: { done: 1, total: 2 },
    });
  });

  it("ignores keepalive comments", () => {
    const parser = new SSEParser();
    const chunk = ": keepalive\n: another comment\n\n";
    const events = parser.feed(chunk);
    expect(events).toHaveLength(0);
  });

  it("handles chunks split across multiple feeds", () => {
    const parser = new SSEParser();
    const part1 = "event: progress\ndata: {\"status\":";
    const part2 = " \"done\"}\n\n";

    const ev1 = parser.feed(part1);
    expect(ev1).toHaveLength(0);

    const ev2 = parser.feed(part2);
    expect(ev2).toHaveLength(1);
    expect(ev2[0].event).toBe("progress");
    expect(ev2[0].data).toEqual({ status: "done" });
  });

  it("handles malformed JSON gracefully by returning raw string", () => {
    const parser = new SSEParser();
    const chunk = "event: progress\ndata: not_valid_json{\n\n";
    const events = parser.feed(chunk);
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("progress");
    expect(events[0].data).toBe("not_valid_json{");
  });
});
