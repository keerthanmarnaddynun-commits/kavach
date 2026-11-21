/**
 * Pure reducers and view models for Intake page and Job Progress.
 */

export function reduceUploadResult(state, action) {
  switch (action.type) {
    case "UPLOAD_START":
      return {
        ...state,
        uploading: true,
        error: null,
        rowErrors: null,
      };

    case "DOCUMENT_UPLOAD_SUCCESS": {
      const newDocs = action.payload.documents || [];
      const updatedDocs = [...state.documents];
      for (const d of newDocs) {
        const existingIdx = updatedDocs.findIndex((x) => x.doc_id === d.doc_id);
        if (existingIdx >= 0) {
          updatedDocs[existingIdx] = { ...updatedDocs[existingIdx], ...d };
        } else {
          updatedDocs.push(d);
        }
      }
      return {
        ...state,
        uploading: false,
        error: null,
        documents: updatedDocs,
        activeJobId: action.payload.job_id || state.activeJobId,
      };
    }

    case "CSV_UPLOAD_SUCCESS": {
      const fileKind = action.payload.kind; // 'cdr' or 'bank'
      return {
        ...state,
        uploading: false,
        error: null,
        rowErrors: null,
        files: {
          ...state.files,
          [fileKind]: action.payload.fileInfo,
        },
      };
    }

    case "UPLOAD_ERROR": {
      const err = action.payload;
      return {
        ...state,
        uploading: false,
        error: err.message || "Upload failed",
        rowErrors: err.details && Array.isArray(err.details) ? err.details : null,
      };
    }

    case "CLEAR_ERROR":
      return {
        ...state,
        error: null,
        rowErrors: null,
      };

    default:
      return state;
  }
}

export function buildRowErrorViewModel(rawErrors) {
  if (!rawErrors || !Array.isArray(rawErrors)) {
    return { errors: [], totalCount: 0, displayedCount: 0 };
  }
  const totalCount = rawErrors.length;
  const displayedErrors = rawErrors.slice(0, 50).map((item) => ({
    row: item.row !== undefined ? item.row : "-",
    column: item.column || "-",
    code: item.code || "invalid",
    message: item.message || "Row validation error",
  }));
  return {
    errors: displayedErrors,
    totalCount,
    displayedCount: displayedErrors.length,
  };
}

export function reduceJobProgress(state, jobData) {
  if (!jobData) return state;

  const status = jobData.status || "queued";
  const progress = jobData.progress || {};
  const done = typeof progress.done === "number" ? progress.done : 0;
  const total = typeof progress.total === "number" ? progress.total : 0;
  const current = progress.current || "";
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const errors = jobData.errors || [];

  return {
    jobId: jobData.job_id || state.jobId,
    kind: jobData.kind || state.kind,
    status,
    done,
    total,
    current,
    percent,
    isComplete: status === "done" || status === "failed",
    isSuccess: status === "done",
    isFailed: status === "failed",
    errors,
  };
}
