import { describe, it, expect } from "vitest";
import {
  reduceUploadResult,
  buildRowErrorViewModel,
  reduceJobProgress,
} from "./intakeReducers.js";

describe("Intake Reducers and View Models", () => {
  it("handles document upload success", () => {
    const initialState = {
      uploading: true,
      error: null,
      documents: [{ doc_id: "FIR_01", filename: "FIR_01.txt" }],
      activeJobId: null,
    };
    const action = {
      type: "DOCUMENT_UPLOAD_SUCCESS",
      payload: {
        documents: [{ doc_id: "FIR_02", filename: "FIR_02.txt" }],
        job_id: "J-000000000001",
      },
    };
    const nextState = reduceUploadResult(initialState, action);
    expect(nextState.uploading).toBe(false);
    expect(nextState.documents).toHaveLength(2);
    expect(nextState.activeJobId).toBe("J-000000000001");
  });

  it("handles upload error with row errors", () => {
    const initialState = { uploading: true, error: null, rowErrors: null };
    const action = {
      type: "UPLOAD_ERROR",
      payload: {
        message: "CSV validation failed",
        details: [{ row: 5, column: "amount", code: "invalid_amount", message: "negative" }],
      },
    };
    const nextState = reduceUploadResult(initialState, action);
    expect(nextState.uploading).toBe(false);
    expect(nextState.error).toBe("CSV validation failed");
    expect(nextState.rowErrors).toHaveLength(1);
  });

  it("formats row error view model cutting at 50 errors", () => {
    const rawErrors = Array.from({ length: 65 }, (_, i) => ({
      row: i + 1,
      column: "a_party",
      code: "invalid_phone",
      message: "Phone number must be 10 digits",
    }));

    const vm = buildRowErrorViewModel(rawErrors);
    expect(vm.totalCount).toBe(65);
    expect(vm.displayedCount).toBe(50);
    expect(vm.errors).toHaveLength(50);
    expect(vm.errors[0].row).toBe(1);
  });

  it("reduces job progress state accurately", () => {
    const initialState = {
      jobId: null,
      status: "queued",
      done: 0,
      total: 0,
      percent: 0,
    };
    const jobUpdate = {
      job_id: "J-0123456789ab",
      kind: "extract",
      status: "running",
      progress: { done: 3, total: 10, current: "processing FIR_03" },
    };
    const state = reduceJobProgress(initialState, jobUpdate);
    expect(state.status).toBe("running");
    expect(state.done).toBe(3);
    expect(state.total).toBe(10);
    expect(state.percent).toBe(30);
    expect(state.isComplete).toBe(false);

    const completed = reduceJobProgress(state, {
      ...jobUpdate,
      status: "done",
      progress: { done: 10, total: 10 },
    });
    expect(completed.isComplete).toBe(true);
    expect(completed.isSuccess).toBe(true);
    expect(completed.percent).toBe(100);
  });
});
