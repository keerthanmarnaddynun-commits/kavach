import React, { useState, useEffect, useMemo } from "react";
import { request } from "../api/client.js";
import { Table } from "../components/Table.jsx";
import { chipLabel, chipTooltip } from "../lib/chips.js";
import {
  getLimitations,
  extractDocId,
  buildPriorityLeadsData,
} from "./overviewHelpers.js";

export function Overview({ caseId, activeCase, onLimitsLoaded }) {
  const [leadsData, setLeadsData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState(null);
  const [showStructural, setShowStructural] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    setErrorText(null);

    request(`/cases/${caseId}/leads`)
      .then((data) => {
        setLeadsData(data);
        if (onLimitsLoaded) {
          onLimitsLoaded(getLimitations(true, data.limitations));
        }
      })
      .catch((err) => {
        setErrorText(err.message || "Failed to load leads");
        if (onLimitsLoaded) {
          onLimitsLoaded(getLimitations(false, null));
        }
      })
      .finally(() => {
        setLoading(false);
      });
  }, [caseId, onLimitsLoaded]);

  const caseObj = activeCase && activeCase.case ? activeCase.case : {};
  const isAnalyzed = Boolean(caseObj.analyzed);
  const docCount = activeCase && activeCase.documents ? activeCase.documents.length : 0;
  const cdrRows = activeCase && activeCase.files && activeCase.files.cdr ? (activeCase.files.cdr.rows || activeCase.files.cdr.row_count || 0) : 0;
  const bankRows = activeCase && activeCase.files && activeCase.files.bank ? (activeCase.files.bank.rows || activeCase.files.bank.row_count || 0) : 0;

  const priorityLeads = useMemo(() => {
    if (!leadsData) return [];
    return buildPriorityLeadsData(
      leadsData.money_flow,
      leadsData.role_chips,
      leadsData.structural_explanation
    );
  }, [leadsData]);

  const priorityColumns = useMemo(() => {
    const hasTied = priorityLeads.some((r) => r.tied);

    const cols = [
      {
        key: "rank",
        header: "Rank",
        isNumeric: true,
        align: "right",
        headerStyle: { width: "60px" },
      },
    ];

    if (hasTied) {
      cols.push({
        key: "tied",
        header: "Tied",
        headerStyle: { width: "60px" },
        render: (tied) => (tied ? "tied" : ""),
      });
    }

    cols.push(
      {
        key: "name",
        header: "Name",
        render: (name, row) => (
          <div>
            <strong>{name}</strong>
            <div className="mono" style={{ fontSize: "10px", color: "var(--muted)" }}>
              {row.person_id}
            </div>
          </div>
        ),
      },
      {
        key: "score",
        header: "Money-Flow Score",
        isNumeric: true,
        align: "right",
        headerStyle: { width: "130px" },
        render: (val) => (typeof val === "number" ? val.toFixed(4) : "-"),
      },
      {
        key: "accounts",
        header: "Accounts",
        headerStyle: { minWidth: "160px" },
        render: (accs) =>
          Array.isArray(accs) && accs.length > 0 ? (
            <span className="mono" style={{ fontSize: "11px" }}>
              {accs.join(", ")}
            </span>
          ) : (
            "-"
          ),
      },
      {
        key: "roles",
        header: "Role Chips",
        render: (roles) => (
          <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
            {Array.isArray(roles) && roles.length > 0
              ? roles.map((r, i) => {
                  const label = chipLabel(r);
                  const tip = chipTooltip(r);
                  return (
                    <span key={i} className="role-chip" title={tip}>
                      {label}
                    </span>
                  );
                })
              : "-"}
          </div>
        ),
      },
      {
        key: "reasons",
        header: "Reasons",
        headerStyle: { minWidth: "220px" },
        render: (reasons) => {
          const text = Array.isArray(reasons) ? reasons.join("; ") : (reasons || "-");
          return (
            <div
              title={text}
              style={{
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                fontSize: "11px",
                lineHeight: "1.3",
              }}
            >
              {text}
            </div>
          );
        },
      },
      {
        key: "evidence",
        header: "Evidence",
        headerStyle: { width: "100px" },
        render: (_, row) => {
          const docId = extractDocId(row.person_id, "FIR_01");
          return (
            <a href={`#/case/${caseId}/evidence/doc/${docId}`} className="table-link">
              FIR evidence
            </a>
          );
        },
      }
    );

    if (showStructural) {
      cols.push(
        {
          key: "degree",
          header: "Degree (explanation only, not a ranking)",
          isNumeric: true,
          align: "right",
          render: (v) => (typeof v === "number" ? v.toFixed(4) : "-"),
        },
        {
          key: "betweenness",
          header: "Betweenness (explanation only, not a ranking)",
          isNumeric: true,
          align: "right",
          render: (v) => (typeof v === "number" ? v.toFixed(4) : "-"),
        },
        {
          key: "eigenvector",
          header: "Eigenvector (explanation only, not a ranking)",
          isNumeric: true,
          align: "right",
          render: (v) => (typeof v === "number" ? v.toFixed(4) : "-"),
        },
        {
          key: "composite",
          header: "Composite (explanation only, not a ranking)",
          isNumeric: true,
          align: "right",
          render: (v) => (typeof v === "number" ? v.toFixed(4) : "-"),
        }
      );
    }

    return cols;
  }, [showStructural, caseId]);

  const muleColumns = [
    {
      key: "id",
      header: "Account ID",
      isIdentifier: true,
      headerStyle: { width: "160px" },
    },
    {
      key: "score",
      header: "Mule Score",
      isNumeric: true,
      align: "right",
      headerStyle: { width: "100px" },
      render: (v) => (typeof v === "number" ? v.toFixed(4) : "-"),
    },
    {
      key: "flagged",
      header: "Flagged",
      headerStyle: { width: "80px" },
      render: (f) => (f ? "Yes" : "No"),
    },
    {
      key: "reasons",
      header: "Reasons",
      headerStyle: { minWidth: "220px" },
      render: (reasons) => {
        const text = Array.isArray(reasons) ? reasons.join("; ") : (reasons || "-");
        return (
          <div
            title={text}
            style={{
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              fontSize: "11px",
              lineHeight: "1.3",
            }}
          >
            {text}
          </div>
        );
      },
    },
    {
      key: "evidence",
      header: "Evidence",
      headerStyle: { width: "120px" },
      render: (_, row) => {
        const rows = row.evidence_rows ? row.evidence_rows.rows || [] : [];
        const fileParam = row.evidence_rows && row.evidence_rows.file && row.evidence_rows.file.includes("bank") ? "bank" : "cdr";
        const queryParts = [];
        if (rows.length > 0) queryParts.push(`rows=${rows.join(",")}`);
        if (row.id) queryParts.push(`highlight=${encodeURIComponent(row.id)}`);
        const queryStr = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";
        return (
          <a
            href={`#/case/${caseId}/evidence/rows/${fileParam}${queryStr}`}
            className="table-link"
          >
            Rows ({rows.length})
          </a>
        );
      },
    },
  ];

  const burnerColumns = [
    {
      key: "id",
      header: "Phone Number",
      isIdentifier: true,
      headerStyle: { width: "160px" },
    },
    {
      key: "score",
      header: "Burner Score",
      isNumeric: true,
      align: "right",
      headerStyle: { width: "100px" },
      render: (v) => (typeof v === "number" ? v.toFixed(4) : "-"),
    },
    {
      key: "flagged",
      header: "Flagged",
      headerStyle: { width: "80px" },
      render: (f) => (f ? "Yes" : "No"),
    },
    {
      key: "reasons",
      header: "Reasons",
      headerStyle: { minWidth: "220px" },
      render: (reasons) => {
        const text = Array.isArray(reasons) ? reasons.join("; ") : (reasons || "-");
        return (
          <div
            title={text}
            style={{
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              fontSize: "11px",
              lineHeight: "1.3",
            }}
          >
            {text}
          </div>
        );
      },
    },
    {
      key: "evidence",
      header: "Evidence",
      headerStyle: { width: "120px" },
      render: (_, row) => {
        const rows = row.evidence_rows ? row.evidence_rows.rows || [] : [];
        const fileParam = row.evidence_rows && row.evidence_rows.file && row.evidence_rows.file.includes("bank") ? "bank" : "cdr";
        const queryParts = [];
        if (rows.length > 0) queryParts.push(`rows=${rows.join(",")}`);
        if (row.id) queryParts.push(`highlight=${encodeURIComponent(row.id)}`);
        const queryStr = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";
        return (
          <a
            href={`#/case/${caseId}/evidence/rows/${fileParam}${queryStr}`}
            className="table-link"
          >
            Rows ({rows.length})
          </a>
        );
      },
    },
  ];

  return (
    <OverviewView
      caseId={caseId}
      caseObj={caseObj}
      isAnalyzed={isAnalyzed}
      docCount={docCount}
      cdrRows={cdrRows}
      bankRows={bankRows}
      leadsData={leadsData}
      errorText={errorText}
      loading={loading}
      showStructural={showStructural}
      setShowStructural={setShowStructural}
      priorityLeads={priorityLeads}
      priorityColumns={priorityColumns}
      muleColumns={muleColumns}
      burnerColumns={burnerColumns}
    />
  );
}

export function OverviewView({
  caseId,
  caseObj = {},
  isAnalyzed = false,
  docCount = 0,
  cdrRows = 0,
  bankRows = 0,
  leadsData = null,
  errorText = null,
  loading = false,
  showStructural = false,
  setShowStructural,
  priorityLeads = [],
  priorityColumns = [],
  muleColumns = [],
  burnerColumns = [],
}) {
  return (
    <div>
      {/* Case Facts Line */}
      <div
        style={{
          padding: "8px 12px",
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          marginBottom: "12px",
          fontSize: "12px",
          display: "flex",
          gap: "16px",
          flexWrap: "wrap",
        }}
      >
        <span>
          <strong>Case:</strong> {caseObj.name || caseId} (<span className="mono">{caseId}</span>)
        </span>
        <span>
          <strong>Status:</strong> {isAnalyzed ? "analyzed" : "not analyzed"}
        </span>
        <span>
          <strong>Documents:</strong> {docCount}
        </span>
        <span>
          <strong>CDR Rows:</strong> {cdrRows}
        </span>
        <span>
          <strong>Bank Rows:</strong> {bankRows}
        </span>
        <span>
          <strong>Type:</strong> {caseObj.synthetic ? "synthetic" : "standard"}
        </span>
      </div>

      {/* Verbatim Disclaimer */}
      {leadsData && leadsData.disclaimer && (
        <div className="disclaimer-box" style={{ marginBottom: "12px" }}>
          {leadsData.disclaimer}
        </div>
      )}

      {errorText && (
        <div className="error-text" style={{ marginBottom: "12px" }}>
          {errorText}
        </div>
      )}

      {loading && <div>Loading leads...</div>}

      {!isAnalyzed && !loading && (
        <div style={{ padding: "16px", backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}>
          Case is not analyzed yet. Run analysis from the Intake page to generate leads.
        </div>
      )}

      {isAnalyzed && leadsData && (
        <div>
          {/* Priority Leads Section */}
          <div style={{ marginBottom: "28px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <h3 style={{ margin: 0 }}>Priority Leads</h3>
              <label style={{ fontSize: "11px", display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={showStructural}
                  onChange={(e) => setShowStructural && setShowStructural(e.target.checked)}
                />
                Show structural explanation metrics (explanation only, not a ranking)
              </label>
            </div>
            <p style={{ margin: "0 0 10px 0", fontSize: "12px", color: "var(--muted)" }}>
              Ordered by money flow; structural scores are explanation only
            </p>
            <Table
              columns={priorityColumns}
              data={priorityLeads}
              keyField="person_id"
              initialSortKey="rank"
              initialSortDir="asc"
              emptyMessage="No priority leads identified."
            />
          </div>

          {/* Mule Leads Section */}
          <div style={{ marginBottom: "28px" }}>
            <h3 style={{ marginBottom: "6px" }}>Mule Account Leads</h3>
            <p style={{ margin: "0 0 10px 0", fontSize: "12px", color: "var(--muted)" }}>
              Accounts flagged with rapid pass-through or structuring patterns
            </p>
            <Table
              columns={muleColumns}
              data={leadsData.mule_accounts || []}
              keyField="id"
              initialSortKey="score"
              initialSortDir="desc"
              emptyMessage="No mule accounts detected."
            />
          </div>

          {/* Burner Leads Section */}
          <div style={{ marginBottom: "28px" }}>
            <h3 style={{ marginBottom: "6px" }}>Burner Phone Leads</h3>
            <p style={{ margin: "0 0 10px 0", fontSize: "12px", color: "var(--muted)" }}>
              Phone numbers flagged with short active lifespan or concentrated contacts
            </p>
            <Table
              columns={burnerColumns}
              data={leadsData.burner_phones || []}
              keyField="id"
              initialSortKey="score"
              initialSortDir="desc"
              emptyMessage="No burner phones detected."
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default Overview;
