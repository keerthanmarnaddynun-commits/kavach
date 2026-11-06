/**
 * services/api.js
 * Handles API communication with the FastAPI backend (http://127.0.0.1:8000).
 */

const API_BASE_URL = "http://127.0.0.1:8000";

export async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/`, {
      method: "GET",
      headers: { "Accept": "application/json" }
    });
    if (res.ok) {
      const data = await res.json();
      return { online: true, data };
    }
    return { online: false, error: `HTTP ${res.status}` };
  } catch (err) {
    return { online: false, error: err.message };
  }
}

export async function analyzeNetwork(text, docId = "FIR_45_2026") {
  if (!text || !text.trim()) {
    throw new Error("Report or evidence text cannot be empty.");
  }

  const response = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    body: JSON.stringify({
      text: text,
      doc_id: docId
    })
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // ignore json parse error
    }
    throw new Error(errorDetail);
  }

  const data = await response.json();
  return data;
}

