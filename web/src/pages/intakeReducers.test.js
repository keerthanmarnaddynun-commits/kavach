import { describe, it, expect } from "vitest";
import {
  mayOpenStream,
  formatDocChars,
  formatDocError,
  reduceUploadResult,
  buildRowErrorViewModel,
  reduceJobProgress,
} from "./intakeReducers.js";

describe("mayOpenStream", () => {
  it("returns false for null or undefined", () => {
    expect(mayOpenStream(null)).toBe(false);
    expect(mayOpenStream(undefined)).toBe(false);
  });

  it("returns false when job status is done or failed", () => {
    expect(mayOpenStream({ status: "done" })).toBe(false);
    expect(mayOpenStream({ status: "failed" })).toBe(false);
    expect(mayOpenStream({ isComplete: true })).toBe(false);
  });

  it("returns true when job is queued, running, or a jobId string", () => {
    expect(mayOpenStream("J-123456789012")).toBe(true);
    expect(mayOpenStream({ status: "queued" })).toBe(true);
    expect(mayOpenStream({ status: "running" })).toBe(true);
  });
});

describe("document table formatting helpers", () => {
  it("formats characters correctly", () => {
    expect(formatDocChars(1268)).toBe("1268");
    expect(formatDocChars(0)).toBe("0");
    expect(formatDocChars(null)).toBe("-");
    expect(formatDocChars(undefined)).toBe("-");
  });

  it("formats document error code correctly", () => {
    expect(formatDocError({ code: "corrupt_file", message: "unreadable" })).toBe("corrupt_file");
    expect(formatDocError("unsupported_encoding")).toBe("unsupported_encoding");
    expect(formatDocError(null)).toBe("-");
    expect(formatDocError(undefined)).toBe("-");
  });
});

describe("buildRowErrorViewModel", () => {
  it("handles error_count exceeding 50 items", () => {
    const items = Array.from({ length: 60 }, (_, i) => ({
      row: i + 1,
      column: "amount",
      code: "invalid_value",
      message: `Error in row ${i + 1}`,
    }));

    const vm = buildRowErrorViewModel({ errors: items, error_count: 150 });
    expect(vm.totalCount).toBe(150);
    expect(vm.displayedCount).toBe(50);
    expect(vm.errors).toHaveLength(50);
    expect(vm.errors[0].row).toBe(1);
    expect(vm.errors[49].row).toBe(50);
  });

  it("handles array with explicit total count", () => {
    const items = [{ row: 1, column: "from_acct", code: "missing", message: "Required" }];
    const vm = buildRowErrorViewModel(items, 85);
    expect(vm.totalCount).toBe(85);
    expect(vm.displayedCount).toBe(1);
  });

  it("handles empty or null errors safely", () => {
    const vm = buildRowErrorViewModel(null);
    expect(vm.totalCount).toBe(0);
    expect(vm.displayedCount).toBe(0);
    expect(vm.errors).toEqual([]);
  });
});

describe("reduceUploadResult", () => {
  const initial = {
    uploading: false,
    error: null,
    rowErrors: null,
    rowErrorCount: 0,
    documents: [],
    files: {},
    activeJobId: null,
  };

  it("handles UPLOAD_START", () => {
    const next = reduceUploadResult(initial, { type: "UPLOAD_START" });
    expect(next.uploading).toBe(true);
    expect(next.error).toBe(null);
  });

  it("handles DOCUMENT_UPLOAD_SUCCESS merging documents", () => {
    const state = {
      ...initial,
      documents: [{ doc_id: "DOC_1", filename: "old.txt" }],
    };
    const action = {
      type: "DOCUMENT_UPLOAD_SUCCESS",
      payload: {
        documents: [
          { doc_id: "DOC_1", filename: "new.txt" },
          { doc_id: "DOC_2", filename: "other.txt" },
        ],
        job_id: "JOB_123",
      },
    };
    const next = reduceUploadResult(state, action);
    expect(next.documents).toHaveLength(2);
    expect(next.documents[0].filename).toBe("new.txt");
    expect(next.activeJobId).toBe("JOB_123");
  });

  it("handles UPLOAD_ERROR storing error and row error count", () => {
    const errPayload = {
      message: "CSV validation failed",
      details: [{ row: 3, column: "mode", message: "Unknown" }],
      errorCount: 15,
    };
    const next = reduceUploadResult(initial, { type: "UPLOAD_ERROR", payload: errPayload });
    expect(next.error).toBe("CSV validation failed");
    expect(next.rowErrors).toHaveLength(1);
    expect(next.rowErrorCount).toBe(15);
  });
});

describe("reduceJobProgress", () => {
  it("calculates percentage accurately", () => {
    const res = reduceJobProgress({}, {
      job_id: "J-01",
      kind: "analyze",
      status: "running",
      progress: { done: 3, total: 10, current: "building graph" },
    });
    expect(res.percent).toBe(30);
    expect(res.isComplete).toBe(false);
    expect(res.current).toBe("building graph");
  });

  it("handles completion flag", () => {
    const res = reduceJobProgress({}, {
      job_id: "J-01",
      status: "done",
      progress: { done: 10, total: 10 },
    });
    expect(res.percent).toBe(100);
    expect(res.isComplete).toBe(true);
    expect(res.isSuccess).toBe(true);
  });
});
