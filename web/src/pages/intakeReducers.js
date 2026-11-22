/**
 * Pure reducers and view models for Intake page and Job Progress.
 */

export function mayOpenStream(jobState) {
  if (!jobState) return false;
  if (typeof jobState === "string") {
    return true;
  }
  const status = jobState.status || "";
  if (status === "done" || status === "failed" || jobState.isComplete) {
    return false;
  }
  return true;
}

export function formatDocChars(chars) {
  if (chars === null || chars === undefined) return "-";
  return String(chars);
}

export function formatDocError(error) {
  if (!error) return "-";
  if (typeof error === "string") return error;
  return error.code || "-";
}

export function reduceUploadResult(state, action) {
  switch (action.type) {
    case "UPLOAD_START":
      return {
        ...state,
        uploading: true,
        error: null,
        rowErrors: null,
        rowErrorCount: 0,
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
        rowErrorCount: 0,
        files: {
          ...state.files,
          [fileKind]: action.payload.fileInfo,
        },
      };
    }

    case "UPLOAD_ERROR": {
      const err = action.payload;
      const rawDetails = err.details && Array.isArray(err.details) ? err.details : null;
      return {
        ...state,
        uploading: false,
        error: err.message || "Upload failed",
        rowErrors: rawDetails,
        rowErrorCount: err.errorCount || (rawDetails ? rawDetails.length : 0),
      };
    }

    case "CLEAR_ERROR":
      return {
        ...state,
        error: null,
        rowErrors: null,
        rowErrorCount: 0,
      };

    default:
      return state;
  }
}

export function buildRowErrorViewModel(rawErrors, totalErrorCount) {
  let list = [];
  let total = 0;
  if (Array.isArray(rawErrors)) {
    list = rawErrors;
    total = typeof totalErrorCount === "number" ? totalErrorCount : list.length;
  } else if (rawErrors && typeof rawErrors === "object") {
    list = Array.isArray(rawErrors.errors) ? rawErrors.errors : [];
    total = typeof rawErrors.error_count === "number"
      ? rawErrors.error_count
      : (typeof totalErrorCount === "number" ? totalErrorCount : list.length);
  } else {
    return { errors: [], totalCount: 0, displayedCount: 0 };
  }

  const displayedErrors = list.slice(0, 50).map((item) => ({
    row: item.row !== undefined ? item.row : "-",
    column: item.column || "-",
    code: item.code || "invalid",
    message: item.message || "Row validation error",
  }));

  return {
    errors: displayedErrors,
    totalCount: total,
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
