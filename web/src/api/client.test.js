import { describe, it, expect } from "vitest";
import { mapError } from "./client.js";

describe("API Error Mapping", () => {
  it("maps 401 to unauthorized", () => {
    const err = mapError(401, { error: { code: "unauthorized" } });
    expect(err.message).toBe("Invalid or expired token");
    expect(err.status).toBe(401);
  });

  it("maps 403 to role restriction", () => {
    const err = mapError(403, { error: { code: "forbidden" } });
    expect(err.message).toBe("Your role cannot do this");
  });

  it("maps 413 to file too large", () => {
    const err = mapError(413, { error: { code: "upload_too_large" } });
    expect(err.message).toBe("File too large");
  });

  it("maps 429 to retry seconds message", () => {
    const err = mapError(429, { error: { code: "too_many_requests" } }, { "retry-after": "45" });
    expect(err.message).toBe("Too many requests. Retry after 45 seconds.");
  });

  it("maps 409 retaining existing doc id message", () => {
    const msg = "Document already exists with id FIR_01";
    const err = mapError(409, { error: { code: "duplicate_document", message: msg } });
    expect(err.message).toBe(msg);
  });

  it("maps 422 with row error details", () => {
    const body = {
      error: {
        code: "invalid_csv",
        message: "Invalid CSV format",
        errors: [{ row: 12, column: "amount", message: "Negative amount" }],
      },
    };
    const err = mapError(422, body);
    expect(err.message).toBe("Invalid CSV format");
    expect(err.details).toHaveLength(1);
    expect(err.details[0].row).toBe(12);
  });
});
