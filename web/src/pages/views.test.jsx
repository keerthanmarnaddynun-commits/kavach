import { describe, it, expect, beforeEach } from "vitest";
import React from "react";
import { renderToString } from "react-dom/server";

// Import Views to test
import { OverviewView } from "./Overview.jsx";
import { PeopleView } from "./People.jsx";
import { NodeInspectorView, EdgeInspectorView } from "./Graph.jsx";
import { EvidenceDocView } from "./EvidenceDoc.jsx";
import { EvidenceRowsView } from "./EvidenceRows.jsx";
import { IntakeDocumentsTable, RowErrorTable } from "./Intake.jsx";
import { LoginFormView } from "./Login.jsx";
import { BreakView } from "./Break.jsx";
import { TimelineView } from "./Timeline.jsx";
import { DossierView } from "./Dossier.jsx";
import { ErrorBoundaryFallback } from "../App.jsx";
import { buildDossier } from "../lib/dossier.js";

// Import Real Fixtures
import nodeDetailFixture from "../fixtures/node_detail.json";
import edgeDetailFirFixture from "../fixtures/edge_detail_fir.json";
import edgeDetailCsvFixture from "../fixtures/edge_detail_csv.json";
import documentFixture from "../fixtures/document.json";
import rowsFixture from "../fixtures/rows.json";
import caseDetailFixture from "../fixtures/case_detail.json";
import leadsFixture from "../fixtures/leads.json";
import peopleFixture from "../fixtures/people.json";
import breakResultFixture from "../fixtures/break_result.json";
import timelineDayFixture from "../fixtures/timeline_day.json";
import graphFixture from "../fixtures/graph.json";

describe("Render Smoke Tests (Repair 1)", () => {
  beforeEach(() => {
    // Stub window and sessionStorage if needed in node test environment
    if (typeof globalThis.window === "undefined") {
      globalThis.window = {
        location: { hash: "" },
      };
    }
    if (typeof globalThis.sessionStorage === "undefined") {
      const storage = {};
      globalThis.sessionStorage = {
        getItem: (k) => storage[k] || null,
        setItem: (k, v) => { storage[k] = String(v); },
        removeItem: (k) => { delete storage[k]; },
        clear: () => { Object.keys(storage).forEach((k) => delete storage[k]); },
      };
    }
  });

  it("renders OverviewView with chip objects without throwing", () => {
    const priorityLeadsWithChipObjects = [
      {
        rank: 1,
        person_id: "PERSON:FIR_01:ent_02",
        name: "Test Person",
        score: 1.2345,
        accounts: ["ACCT1234"],
        roles: [
          { chip: "Mule", reason: "Structuring transactions" },
          { chip: "Operator", reason: "High call frequency" },
        ],
        reasons: ["Frequent fund movements"],
      },
    ];

    const html = renderToString(
      <OverviewView
        caseId="C-01"
        caseObj={caseDetailFixture.case || {}}
        isAnalyzed={true}
        docCount={5}
        cdrRows={100}
        bankRows={100}
        leadsData={leadsFixture}
        priorityLeads={priorityLeadsWithChipObjects}
        priorityColumns={[
          { key: "rank", header: "Rank" },
          { key: "name", header: "Name", render: (n) => <strong>{n}</strong> },
          {
            key: "roles",
            header: "Role Chips",
            render: (roles) => (
              <div>
                {(roles || []).map((r, i) => (
                  <span key={i} className="role-chip">
                    {typeof r === "object" ? r.chip : String(r)}
                  </span>
                ))}
              </div>
            ),
          },
        ]}
      />
    );
    expect(html).toContain("Priority Leads");
    expect(html).toContain("Mule");
  });

  it("renders PeopleView with chip objects without throwing", () => {
    const peopleWithChipObjects = (peopleFixture || []).slice(0, 3).map((p) => ({
      ...p,
      roles: [{ chip: "Suspect", reason: "Named in FIR" }],
    }));

    const html = renderToString(
      <PeopleView
        caseId="C-01"
        people={peopleWithChipObjects}
        totalCount={peopleWithChipObjects.length}
        filterText=""
        columns={[
          { key: "name", header: "Name", render: (n) => <strong>{n}</strong> },
          {
            key: "roles",
            header: "Role Chips",
            render: (roles) => (
              <div>
                {(roles || []).map((r, i) => (
                  <span key={i} className="role-chip">
                    {typeof r === "object" ? r.chip : String(r)}
                  </span>
                ))}
              </div>
            ),
          },
        ]}
      />
    );
    expect(html).toContain("People in Case");
    expect(html).toContain("Suspect");
  });

  it("renders NodeInspectorView with real node_detail fixture without throwing", () => {
    const nid = nodeDetailFixture.node_id || nodeDetailFixture.id || "NODE:1";
    const selectedItem = {
      type: "node",
      id: nid,
      data: {
        id: nid,
        label: nodeDetailFixture.label || nid,
        type: nodeDetailFixture.type || "PERSON",
        ai_confidence: 0.95,
      },
    };

    const html = renderToString(
      <NodeInspectorView
        caseId="C-01"
        selectedItem={selectedItem}
        data={nodeDetailFixture}
        onNeighbourClick={() => {}}
      />
    );
    expect(html).toContain("Type");
    expect(html).toContain(nid);
  });

  it("renders EdgeInspectorView with real edge_detail_fir fixture without throwing", () => {
    const eid = edgeDetailFirFixture.edge_id || edgeDetailFirFixture.id || "EDGE:1";
    const selectedItem = {
      type: "edge",
      id: eid,
      data: {
        id: eid,
        label: edgeDetailFirFixture.relation || "CALLS",
        source: edgeDetailFirFixture.source,
        target: edgeDetailFirFixture.target,
      },
    };

    const html = renderToString(
      <EdgeInspectorView
        caseId="C-01"
        selectedItem={selectedItem}
        data={edgeDetailFirFixture}
        onNeighbourClick={() => {}}
      />
    );
    expect(html).toContain("Relation");
    expect(html).toContain(eid);
  });

  it("renders EdgeInspectorView with real edge_detail_csv fixture without throwing", () => {
    const eid = edgeDetailCsvFixture.edge_id || edgeDetailCsvFixture.id || "EDGE:2";
    const selectedItem = {
      type: "edge",
      id: eid,
      data: {
        id: eid,
        label: edgeDetailCsvFixture.relation || "TRANSFERS_TO",
        source: edgeDetailCsvFixture.source,
        target: edgeDetailCsvFixture.target,
      },
    };

    const html = renderToString(
      <EdgeInspectorView
        caseId="C-01"
        selectedItem={selectedItem}
        data={edgeDetailCsvFixture}
        onNeighbourClick={() => {}}
      />
    );
    expect(html).toContain("Relation");
    expect(html).toContain(eid);
  });

  it("renders EvidenceDocView with real document fixture without throwing", () => {
    const segments = [
      { text: "Suspect statement segment ", isHighlighted: false },
      { text: "Vikash Sharma", isHighlighted: true, spans: [{ surface: "Vikash Sharma", start: 26, end: 39 }] },
    ];

    const html = renderToString(
      <EvidenceDocView
        caseId="C-01"
        docId={documentFixture.doc_id || "FIR_01"}
        docList={caseDetailFixture.documents || []}
        docData={documentFixture}
        segments={segments}
        outOfRangeCount={0}
      />
    );
    expect(html).toContain("Document:");
    expect(html).toContain(documentFixture.doc_id || "FIR_01");
  });

  it("renders EvidenceRowsView with real rows fixture without throwing", () => {
    const html = renderToString(
      <EvidenceRowsView
        caseId="C-01"
        fileKind="cdr"
        data={rowsFixture}
        rows={rowsFixture.rows || []}
        columns={[
          { key: "row", header: "Row #" },
          { key: "a_party", header: "A PARTY" },
        ]}
      />
    );
    expect(html).toContain("File:");
    expect(html).toContain("cdr");
  });

  it("renders IntakeDocumentsTable with real case_detail documents without throwing", () => {
    const html = renderToString(
      <IntakeDocumentsTable documents={caseDetailFixture.documents || []} />
    );
    expect(html).toContain("Case Documents");
  });

  it("renders RowErrorTable without throwing", () => {
    const rowErrorVm = {
      totalCount: 2,
      errors: [
        { row: 12, column: "a_party", code: "invalid_phone", message: "Phone invalid" },
        { row: 15, column: "amount", code: "negative_amount", message: "Amount negative" },
      ],
    };
    const html = renderToString(<RowErrorTable rowErrorVm={rowErrorVm} />);
    expect(html).toContain("CSV Validation Errors");
    expect(html).toContain("invalid_phone");
  });

  it("renders LoginFormView without throwing", () => {
    const html = renderToString(
      <LoginFormView
        username="analyst_user"
        password=""
        errorText="Invalid credentials"
        loading={false}
      />
    );
    expect(html).toContain("Login to KAVACH");
    expect(html).toContain("Invalid credentials");
  });

  it("renders BreakView with real break_result fixture without throwing", () => {
    const vm = {
      finite: true,
      size: breakResultFixture.size || 1,
      cut: breakResultFixture.cut || [],
      directLink: Boolean(breakResultFixture.direct_link),
      bridgingPhones: breakResultFixture.bridging_unowned_phones || [],
      note: breakResultFixture.note || "",
      disclaimer: breakResultFixture.disclaimer || "",
      isEmptyCut: false,
      emptyCutMessage: "No observed link between the groups on the call layer.",
    };
    const html = renderToString(
      <BreakView
        caseId="C-01"
        people={peopleFixture || []}
        breakVm={vm}
      />
    );
    expect(html).toContain("Courier Break Analysis");
    expect(html).toContain("Persons in Cut");
  });

  it("renders TimelineView with real timeline_day fixture without throwing", () => {
    const html = renderToString(
      <TimelineView
        caseId="C-01"
        bucket="day"
        data={timelineDayFixture}
      />
    );
    expect(html).toContain("Activity Timeline");
    expect(html).toContain("Calls Volume");
    expect(html).toContain("Transfers Volume");
  });

  it("renders ErrorBoundaryFallback without throwing", () => {
    const error = new Error("Simulated rendering exception for test");
    const html = renderToString(<ErrorBoundaryFallback error={error} onRetry={() => {}} />);
    expect(html).toContain("View rendering error");
    expect(html).toContain("Simulated rendering exception for test");
  });

  it("renders DossierView with real analyzed case fixture without throwing", () => {
    const dossier = buildDossier({
      caseDetail: caseDetailFixture,
      leads: leadsFixture,
      graph: graphFixture,
      user: { username: "officer", role: "analyst" },
      generatedAt: "2026-11-23 10:00:00 UTC",
    });
    const html = renderToString(<DossierView dossier={dossier} onPrint={() => {}} />);
    expect(html).toContain("Case dossier (draft for review)");
    expect(html).toContain("Priority Leads");
    expect(html).toContain("Certificate under Section 63(4)(c)");
    expect(html).toContain("Evidence Inventory &amp; Hashes");
  });

  it("renders DossierView for unanalyzed case showing limited sections", () => {
    const unanalyzedCase = {
      case: { ...caseDetailFixture.case, analyzed: false },
      documents: caseDetailFixture.documents,
      files: caseDetailFixture.files,
    };
    const dossier = buildDossier({
      caseDetail: unanalyzedCase,
      leads: null,
      graph: null,
      user: { username: "officer", role: "analyst" },
      generatedAt: "2026-11-23 10:00:00 UTC",
    });
    const html = renderToString(<DossierView dossier={dossier} onPrint={() => {}} />);
    expect(html).toContain("Case not analyzed: no leads or graph summary.");
    expect(html).not.toContain("Priority Leads");
    expect(html).not.toContain("Certificate under Section 63(4)(c)");
  });
});
