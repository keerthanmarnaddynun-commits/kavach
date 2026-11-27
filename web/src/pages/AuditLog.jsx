import React, { useState, useEffect, useCallback, useMemo } from "react";
import { request } from "../api/client.js";
import { hasRole } from "../lib/roles.js";
import {
  formatAuditDetail,
  formatAuditTime,
  formatShortHash,
  filterAuditEntries,
  calculatePagination,
} from "./auditHelpers.js";

const PAGE_SIZE = 50;

export function AuditLogView({
  user,
  entries = [],
  loading = false,
  error = null,
  offset = 0,
  limit = PAGE_SIZE,
  filterText = "",
  onFilterChange,
  onPrevPage,
  onNextPage,
  verifyResult = null,
  verifyTime = null,
  verifying = false,
  verifyError = null,
  onVerifyChain,
}) {
  const isAdmin = user && hasRole(user.role, "admin");

  if (!isAdmin) {
    return (
      <div
        className="admin-access-required"
        data-testid="admin-access-required"
        style={{
          padding: "24px",
          color: "var(--danger)",
          fontSize: "14px",
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          margin: "16px",
        }}
      >
        Admin access required
      </div>
    );
  }

  // Filter current page entries and sort newest first (highest seq first)
  const displayedEntries = useMemo(() => {
    const filtered = filterAuditEntries(entries, filterText);
    return [...filtered].sort((a, b) => (b.seq || 0) - (a.seq || 0));
  }, [entries, filterText]);

  const totalKnown = verifyResult?.entries ?? null;
  const pagination = calculatePagination(offset, limit, entries.length, totalKnown);

  return (
    <div className="audit-log-page" style={{ padding: "20px" }}>
      <div style={{ marginBottom: "16px" }}>
        <h2 style={{ margin: "0 0 6px 0", fontSize: "20px" }}>Audit Log</h2>
        <p style={{ margin: "0", fontSize: "12px", color: "var(--muted)", lineHeight: "1.4" }}>
          The chain is unkeyed: someone with file access could rewrite the whole log, and removal of the last entries would not be detected.
        </p>
      </div>

      {/* Action / Toolbar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          marginBottom: "16px",
          padding: "12px",
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <button
            type="button"
            className="primary"
            data-testid="verify-chain-btn"
            onClick={onVerifyChain}
            disabled={verifying}
            style={{ fontSize: "12px", padding: "6px 12px", cursor: verifying ? "not-allowed" : "pointer" }}
          >
            {verifying ? "Verifying..." : "Verify chain"}
          </button>

          {verifyResult && (
            <div
              data-testid="verify-result"
              style={{
                fontSize: "13px",
                fontWeight: 600,
                color: verifyResult.ok ? "var(--accent)" : "var(--danger)",
              }}
            >
              {verifyResult.ok
                ? `Chain intact: ${verifyResult.entries} entries verified`
                : `Chain broken at entry ${verifyResult.first_bad_index}`}
              {verifyTime && (
                <span style={{ fontSize: "11px", fontWeight: "normal", color: "var(--muted)", marginLeft: "8px" }}>
                  (checked {verifyTime})
                </span>
              )}
            </div>
          )}

          {verifyError && (
            <div className="error-text" data-testid="verify-error" style={{ fontSize: "12px" }}>
              {verifyError}
            </div>
          )}
        </div>

        <div>
          <input
            type="text"
            data-testid="audit-filter-input"
            placeholder="Filter by user or action..."
            value={filterText}
            onChange={(e) => onFilterChange && onFilterChange(e.target.value)}
            style={{
              padding: "6px 10px",
              fontSize: "12px",
              minWidth: "220px",
              boxSizing: "border-box",
            }}
          />
        </div>
      </div>

      {error && (
        <div
          className="error-text"
          data-testid="audit-error"
          style={{
            marginBottom: "16px",
            padding: "8px 12px",
            backgroundColor: "var(--surface)",
            border: "1px solid var(--danger)",
            borderRadius: "4px",
          }}
        >
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div style={{ padding: "20px", color: "var(--muted)", fontSize: "13px" }}>Loading audit records...</div>
      ) : displayedEntries.length === 0 ? (
        <div
          style={{
            padding: "24px",
            textAlign: "center",
            color: "var(--muted)",
            fontSize: "13px",
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
          }}
        >
          {entries.length === 0 ? "No audit log entries found." : "No matching entries for the current filter."}
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="data-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border)", backgroundColor: "var(--surface)" }}>
                <th style={{ textAlign: "left", padding: "8px" }}>Seq</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Time</th>
                <th style={{ textAlign: "left", padding: "8px" }}>User</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Action</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Case</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Details</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Prev Hash</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Entry Hash</th>
              </tr>
            </thead>
            <tbody>
              {displayedEntries.map((entry) => (
                <tr key={entry.hash || entry.seq} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td className="mono" style={{ padding: "8px", verticalAlign: "top" }}>
                    {entry.seq}
                  </td>
                  <td style={{ padding: "8px", whiteSpace: "nowrap", verticalAlign: "top" }}>
                    {formatAuditTime(entry.ts)}
                  </td>
                  <td style={{ padding: "8px", verticalAlign: "top" }}>
                    <strong>{entry.actor}</strong>
                    {entry.role && (
                      <span className="role-chip" style={{ marginLeft: "4px", fontSize: "10px" }}>
                        {entry.role}
                      </span>
                    )}
                  </td>
                  <td className="mono" style={{ padding: "8px", verticalAlign: "top" }}>
                    {entry.action}
                  </td>
                  <td style={{ padding: "8px", verticalAlign: "top" }}>
                    {entry.case_id ? (
                      <a href={`#/case/${entry.case_id}/overview`} className="mono">
                        {entry.case_id}
                      </a>
                    ) : (
                      <span style={{ color: "var(--muted)" }}>-</span>
                    )}
                  </td>
                  <td style={{ padding: "8px", fontSize: "11px", maxWidth: "280px", wordBreak: "break-all", verticalAlign: "top" }}>
                    {formatAuditDetail(entry.detail)}
                  </td>
                  <td className="mono" style={{ padding: "8px", verticalAlign: "top" }} title={entry.prev_hash}>
                    {formatShortHash(entry.prev_hash)}
                  </td>
                  <td className="mono" style={{ padding: "8px", verticalAlign: "top" }} title={entry.hash}>
                    {formatShortHash(entry.hash)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination Controls */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: "16px",
          fontSize: "12px",
          color: "var(--text)",
        }}
      >
        <div>
          Showing {entries.length > 0 ? `${pagination.rangeStart} - ${pagination.rangeEnd}` : "0"}
          {totalKnown !== null && ` of ${totalKnown}`}
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            type="button"
            data-testid="audit-prev-btn"
            onClick={onPrevPage}
            disabled={!pagination.hasPrev || loading}
            style={{ padding: "4px 12px", fontSize: "12px", cursor: pagination.hasPrev ? "pointer" : "not-allowed" }}
          >
            Previous
          </button>
          <span style={{ display: "flex", alignItems: "center", padding: "0 4px" }}>
            Page {pagination.currentPage}
          </span>
          <button
            type="button"
            data-testid="audit-next-btn"
            onClick={onNextPage}
            disabled={!pagination.hasNext || loading}
            style={{ padding: "4px 12px", fontSize: "12px", cursor: pagination.hasNext ? "pointer" : "not-allowed" }}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

export function AuditLog({ user }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [offset, setOffset] = useState(0);
  const [filterText, setFilterText] = useState("");
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifyTime, setVerifyTime] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState(null);

  const isAdmin = user && hasRole(user.role, "admin");

  const loadPage = useCallback((pageOffset) => {
    if (!isAdmin) return;
    setLoading(true);
    setError(null);
    request(`/admin/audit?limit=${PAGE_SIZE}&offset=${pageOffset}`)
      .then((data) => {
        setEntries(data || []);
      })
      .catch((err) => {
        setError(err.message || "Failed to load audit records");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [isAdmin]);

  // Load audit records only if admin
  useEffect(() => {
    if (isAdmin) {
      loadPage(offset);
    }
  }, [isAdmin, offset, loadPage]);

  function handleVerifyChain() {
    if (!isAdmin || verifying) return;
    setVerifying(true);
    setVerifyError(null);
    request("/admin/audit/verify")
      .then((res) => {
        setVerifyResult(res);
        setVerifyTime(new Date().toLocaleTimeString());
      })
      .catch((err) => {
        setVerifyError(err.message || "Failed to verify chain");
      })
      .finally(() => {
        setVerifying(false);
      });
  }

  function handlePrev() {
    setOffset((prev) => Math.max(0, prev - PAGE_SIZE));
  }

  function handleNext() {
    setOffset((prev) => prev + PAGE_SIZE);
  }

  return (
    <AuditLogView
      user={user}
      entries={entries}
      loading={loading}
      error={error}
      offset={offset}
      limit={PAGE_SIZE}
      filterText={filterText}
      onFilterChange={setFilterText}
      onPrevPage={handlePrev}
      onNextPage={handleNext}
      verifyResult={verifyResult}
      verifyTime={verifyTime}
      verifying={verifying}
      verifyError={verifyError}
      onVerifyChain={handleVerifyChain}
    />
  );
}

export default AuditLog;
