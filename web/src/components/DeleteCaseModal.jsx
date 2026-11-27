import React, { useState } from "react";
import { request } from "../api/client.js";
import { clearCaseCaches } from "../pages/breakHelpers.js";

export function DeleteCaseModal({ isOpen, caseId, caseName, onClose, onDeleted }) {
  const [confirmInput, setConfirmInput] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  if (!isOpen || !caseId) return null;

  const targetName = (caseName || "").trim();
  const targetId = (caseId || "").trim();
  const trimmedInput = confirmInput.trim();

  // Match either the case name or case ID
  const isMatch = (targetName && trimmedInput === targetName) || (targetId && trimmedInput === targetId);

  async function handleDelete(e) {
    e.preventDefault();
    if (!isMatch || deleting) return;

    setDeleting(true);
    setDeleteError(null);
    try {
      await request(`/cases/${caseId}`, {
        method: "DELETE",
      });

      // Clear all in-memory page caches for this case
      clearCaseCaches(caseId);

      setDeleting(false);
      setConfirmInput("");
      if (onDeleted) {
        onDeleted(caseId);
      }
    } catch (err) {
      setDeleting(false);
      setDeleteError(err.message || "Failed to delete case");
    }
  }

  function handleCancel() {
    setConfirmInput("");
    setDeleteError(null);
    setDeleting(false);
    onClose && onClose();
  }

  return (
    <div
      className="modal-backdrop"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "var(--modal-backdrop)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1100,
      }}
      onClick={handleCancel}
    >
      <div
        className="delete-case-modal"
        style={{
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          padding: "20px",
          maxWidth: "480px",
          width: "90%",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <strong style={{ fontSize: "14px", color: "var(--danger)" }}>Delete Case</strong>
          <button type="button" onClick={handleCancel} style={{ fontSize: "12px", cursor: "pointer" }}>
            Close
          </button>
        </div>

        <p style={{ fontSize: "12px", lineHeight: "1.5", marginBottom: "12px", color: "var(--text)" }}>
          This action will permanently delete case{" "}
          <strong>{targetName || targetId}</strong> (<span className="mono">{targetId}</span>) and all associated documents, records, and analysis files.
        </p>

        <p style={{ fontSize: "12px", marginBottom: "8px", fontWeight: "600" }}>
          To confirm, please type the case name <code>{targetName || targetId}</code> or ID <code>{targetId}</code>:
        </p>

        <form onSubmit={handleDelete}>
          <input
            type="text"
            data-testid="delete-case-input"
            value={confirmInput}
            onChange={(e) => setConfirmInput(e.target.value)}
            placeholder={`Type "${targetName || targetId}" or "${targetId}"`}
            autoFocus
            style={{
              width: "100%",
              padding: "6px 8px",
              fontSize: "12px",
              marginBottom: "12px",
              boxSizing: "border-box",
            }}
          />

          {deleteError && (
            <div
              className="error-text"
              data-testid="delete-case-error"
              style={{
                color: "var(--danger)",
                fontSize: "11px",
                marginBottom: "12px",
                padding: "6px 8px",
                backgroundColor: "var(--surface)",
                border: "1px solid var(--danger)",
                borderRadius: "2px",
              }}
            >
              {deleteError}
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
            <button type="button" onClick={handleCancel} disabled={deleting} style={{ padding: "4px 12px" }}>
              Cancel
            </button>
            <button
              type="submit"
              data-testid="delete-case-confirm-button"
              disabled={!isMatch || deleting}
              style={{
                padding: "4px 12px",
                backgroundColor: isMatch ? "var(--danger)" : "var(--muted)",
                color: "var(--badge-danger-text)",
                border: "none",
                cursor: isMatch && !deleting ? "pointer" : "not-allowed",
                opacity: isMatch && !deleting ? 1 : 0.6,
              }}
            >
              {deleting ? "Deleting..." : "Delete case"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default DeleteCaseModal;
