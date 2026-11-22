import React, { useState, useEffect, useMemo } from "react";
import { request } from "../api/client.js";
import { Table } from "../components/Table.jsx";
import { filterPeople } from "./peopleHelpers.js";

export function People({ caseId }) {
  const [people, setPeople] = useState([]);
  const [filterText, setFilterText] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState(null);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    setErrorText(null);

    request(`/cases/${caseId}/people`)
      .then((data) => {
        setPeople(data || []);
      })
      .catch((err) => {
        setErrorText(err.message || "Failed to load people");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [caseId]);

  const filteredPeople = useMemo(() => {
    return filterPeople(people, filterText);
  }, [people, filterText]);

  const columns = useMemo(() => [
    {
      key: "name",
      header: "Name",
      headerStyle: { width: "160px" },
      render: (name, row) => (
        <div>
          <strong>{name}</strong>
          {row.canonical_name && row.canonical_name !== name && (
            <div style={{ fontSize: "11px", color: "var(--muted)" }}>({row.canonical_name})</div>
          )}
          <div className="mono" style={{ fontSize: "10px", color: "var(--muted)" }}>
            {row.id || row.person_id}
          </div>
        </div>
      ),
    },
    {
      key: "aliases",
      header: "Aliases",
      render: (aliases) =>
        Array.isArray(aliases) && aliases.length > 0 ? (
          <span className="mono" style={{ fontSize: "11px" }}>
            {aliases.join(", ")}
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
                const label = typeof r === "object" && r !== null ? (r.chip || r.name || r.role || "") : String(r);
                const tip = typeof r === "object" && r !== null ? (r.reason || undefined) : undefined;
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
      key: "owned_phones",
      header: "Owned Phones",
      render: (phones) =>
        Array.isArray(phones) && phones.length > 0 ? (
          <span className="mono" style={{ fontSize: "11px" }}>
            {phones.join(", ")}
          </span>
        ) : (
          "-"
        ),
    },
    {
      key: "controlled_accounts",
      header: "Controlled Accounts",
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
      key: "documents",
      header: "Documents",
      render: (docs) =>
        Array.isArray(docs) && docs.length > 0 ? (
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
            {docs.map((d) => (
              <a
                key={d}
                href={`#/case/${caseId}/evidence/doc/${d}`}
                className="mono table-link"
              >
                {d}
              </a>
            ))}
          </div>
        ) : (
          "-"
        ),
    },
    {
      key: "suggested_same_person",
      header: "Possible Same Person",
      render: (suggestions) => {
        if (!Array.isArray(suggestions) || suggestions.length === 0) return "-";
        return (
          <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "11px" }}>
            {suggestions.map((s, idx) => (
              <li key={idx}>
                <span className="mono">{s.other_person_id}</span>
                {s.reasons && (
                  <span style={{ color: "var(--muted)", marginLeft: "4px" }}>
                    ({Array.isArray(s.reasons) ? s.reasons.join(", ") : s.reasons})
                  </span>
                )}
              </li>
            ))}
          </ul>
        );
      },
    },
  ], [caseId]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <h3 style={{ margin: 0 }}>People in Case ({filteredPeople.length})</h3>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <label htmlFor="people-filter" style={{ fontSize: "11px", color: "var(--muted)" }}>
            Filter:
          </label>
          <input
            id="people-filter"
            type="text"
            placeholder="Search name, phone, account, doc..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            style={{ width: "260px" }}
          />
        </div>
      </div>

      {errorText && (
        <div className="error-text" style={{ marginBottom: "12px" }}>
          {errorText}
        </div>
      )}

      {loading && <div>Loading people directory...</div>}

      {!loading && (
        <Table
          columns={columns}
          data={filteredPeople}
          keyField="id"
          initialSortKey="name"
          initialSortDir="asc"
          emptyMessage={filterText ? "No people match the filter criteria." : "No people records in this case."}
        />
      )}
    </div>
  );
}

export default People;
