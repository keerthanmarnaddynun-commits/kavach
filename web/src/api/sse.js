/**
 * Pure SSE parser for stream chunks.
 */

export class SSEParser {
  constructor() {
    this.buffer = "";
    this.currentEvent = null;
    this.currentData = null;
  }

  feed(chunk) {
    this.buffer += chunk;
    const lines = this.buffer.split("\n");
    // Retain incomplete trailing line in the buffer
    this.buffer = lines.pop() || "";

    const events = [];

    for (const rawLine of lines) {
      const line = rawLine.trimEnd();

      // Comment / keepalive line: ignore
      if (line.startsWith(":")) {
        continue;
      }

      // Empty line indicates event boundary
      if (line === "") {
        if (this.currentEvent || this.currentData !== null) {
          let parsedData = this.currentData;
          if (this.currentData !== null) {
            try {
              parsedData = JSON.parse(this.currentData);
            } catch {
              parsedData = this.currentData;
            }
          }
          events.push({
            event: this.currentEvent || "message",
            data: parsedData,
          });
          this.currentEvent = null;
          this.currentData = null;
        }
        continue;
      }

      if (line.startsWith("event:")) {
        this.currentEvent = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const val = line.slice(5).trim();
        this.currentData = this.currentData === null ? val : `${this.currentData}\n${val}`;
      }
    }

    return events;
  }
}

export function parseSSEEvents(rawText) {
  const parser = new SSEParser();
  return parser.feed(rawText);
}
