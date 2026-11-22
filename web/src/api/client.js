/**
 * HTTP client and error mapping for KAVACH backend API.
 */

const TOKEN_KEY = "kavach_token";

let unauthorizedHandler = null;

export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

export function getToken() {
  if (typeof sessionStorage === "undefined") return null;
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.setItem(TOKEN_KEY, token);
  }
}

export function clearToken() {
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.removeItem(TOKEN_KEY);
  }
}

export function mapError(status, errorBody, headers = {}) {
  const errObj = errorBody && errorBody.error ? errorBody.error : {};
  const code = errObj.code || `http_${status}`;
  let message = errObj.message || "An error occurred";
  let details = errObj.details || null;
  const rawList = errObj.errors || errObj.row_errors || null;
  const errorCount = typeof errObj.error_count === "number"
    ? errObj.error_count
    : (Array.isArray(rawList) ? rawList.length : 0);

  if (status === 401) {
    message = errObj.message || "Invalid or expired token";
  } else if (status === 403) {
    message = "Your role cannot do this";
  } else if (status === 413) {
    message = "File too large";
  } else if (status === 429) {
    const retryAfter = (headers && (headers["retry-after"] || headers["Retry-After"])) || "60";
    message = `Too many requests. Retry after ${retryAfter} seconds.`;
  } else if (status === 409) {
    message = errObj.message || "Resource conflict";
  } else if (status === 422) {
    message = errObj.message || "Validation failed";
    details = rawList;
  }

  return { code, message, details, errorCount, status };
}

export async function request(path, options = {}) {
  const headers = { ...options.headers };
  const token = getToken();
  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const url = path.startsWith("/api") ? path : `/api${path}`;
  const response = await fetch(url, {
    ...options,
    headers,
  });

  const contentType = response.headers.get("content-type") || "";
  let data = null;
  if (contentType.includes("application/json")) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
      if (unauthorizedHandler) {
        unauthorizedHandler();
      } else if (typeof window !== "undefined") {
        window.location.hash = "#/login";
      }
    }
    const errMap = mapError(response.status, data, Object.fromEntries(response.headers.entries()));
    const error = new Error(errMap.message);
    error.code = errMap.code;
    error.status = response.status;
    error.details = errMap.details;
    error.errorCount = errMap.errorCount;
    throw error;
  }

  return data;
}
