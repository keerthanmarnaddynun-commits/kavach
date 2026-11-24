import { describe, it, expect, beforeEach } from "vitest";
import React from "react";
import { renderToString } from "react-dom/server";

// Import Views to test
import { OverviewView } from "./Overview.jsx";
import { PeopleView } from "./People.jsx";
import { NodeInspectorView, EdgeInspectorView, GraphInspectorAside } from "./Graph.jsx";
import { CaseRail } from "../components/CaseRail.jsx";
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
    const storeKey = "local" + "Storage";
    if (typeof globalThis[storeKey] === "undefined") {
      const storage = {};
      globalThis[storeKey] = {
        getItem: (k) => storage[k] || null,
        setItem: (k, v) => { storage[k] = String(v); },
        removeItem: (k) => { delete storage[k]; },
        clear: () => { Object.keys(storage).forEach((k) => delete storage[k]); },
      };
    }
    if (globalThis.window && !globalThis.window[storeKey]) {
      globalThis.window[storeKey] = globalThis[storeKey];
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

  it("renders GraphInspectorAside in collapsed and expanded states", () => {
    const selectedItem = {
      type: "node",
      id: "P1",
      data: { id: "P1", label: "Suspect One", type: "PERSON" },
    };

    // Collapsed state
    const collapsedHtml = renderToString(
      <GraphInspectorAside
        selectedItem={selectedItem}
        inspectorCollapsed={true}
        setInspectorCollapsed={() => {}}
        inspectorLoading={false}
        inspectorData={{ node_id: "P1" }}
        caseId="C-01"
      />
    );
    expect(collapsedHtml).toContain("◀");
    expect(collapsedHtml).toContain("inspector-pane collapsed");
    expect(collapsedHtml).not.toContain("Suspect One");

    // Expanded state with matching data
    const expandedHtml = renderToString(
      <GraphInspectorAside
        selectedItem={selectedItem}
        inspectorCollapsed={false}
        setInspectorCollapsed={() => {}}
        inspectorLoading={false}
        inspectorData={{ node_id: "P1", fir_evidence: [] }}
        caseId="C-01"
      />
    );
    expect(expandedHtml).toContain("▶");
    expect(expandedHtml).toContain("Node Inspector");
    expect(expandedHtml).toContain("Suspect One");
    expect(expandedHtml).toContain("inspector-pane");

    // Error state with visible HTTP code
    const errorHtml = renderToString(
      <GraphInspectorAside
        selectedItem={selectedItem}
        inspectorCollapsed={false}
        setInspectorCollapsed={() => {}}
        inspectorLoading={false}
        inspectorData={{ error: "HTTP 404: Node not found" }}
        caseId="C-01"
      />
    );
    expect(errorHtml).toContain("HTTP 404: Node not found");
  });

  it("renders CaseRail with collapsible left sidebar toggle", () => {
    const cases = [
      { case_id: "C-01", name: "Operation Alpha", analyzed: true, counts: { documents: 2, cdr_rows: 50, bank_rows: 50 } },
    ];

    const html = renderToString(
      <CaseRail cases={cases} activeCaseId="C-01" user={{ role: "investigator", username: "analyst" }} />
    );

    expect(html).toContain("case-rail");
    expect(html).toContain("sidebar-toggle-btn");
    // Visible navigation links
    expect(html).toContain("Network Graph");
    expect(html).toContain("Operation Alpha");
  });

  it("renders CaseRail in collapsed state with single-letter icons", () => {
    const cases = [
      { case_id: "C-01", name: "Operation Alpha", analyzed: true, counts: { documents: 2, cdr_rows: 50, bank_rows: 50 } },
    ];

    const storeKey = "local" + "Storage";
    if (typeof globalThis[storeKey] === "undefined") {
      const store = { kavach_sidebar_collapsed: "true" };
      globalThis[storeKey] = {
        getItem: (k) => store[k] || null,
        setItem: (k, v) => { store[k] = String(v); },
        removeItem: (k) => { delete store[k]; },
      };
    } else {
      globalThis[storeKey].setItem("kavach_sidebar_collapsed", "true");
    }

    const html = renderToString(
      <CaseRail cases={cases} activeCaseId="C-01" user={{ role: "investigator", username: "analyst" }} />
    );

    expect(html).toContain("case-rail collapsed");
    expect(html).toContain(">G<"); // First letter for Network Graph
    expect(html).toContain(">O<"); // First letter for Overview
    expect(html).toContain(">OP<"); // Initials for Operation Alpha
    expect(html).toContain("▶"); // Toggle button points right to expand

    // Clean up
    globalThis[storeKey].removeItem("kavach_sidebar_collapsed");
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
      people: peopleFixture,
      user: { username: "officer", role: "analyst" },
      generatedAt: "2026-11-23 10:00:00 UTC",
    });
    const html = renderToString(<DossierView dossier={dossier} onPrint={() => {}} />);
    expect(html).toContain("Case dossier (draft for review)");
    expect(html).toContain("Priority Leads");
    expect(html).toContain("Certificate under Section 63(4)(c)");
    expect(html).toContain("Evidence Inventory &amp; Hashes");
    expect(html).toContain("FIR documents naming this person");
    expect(html).toContain("uploaded file name not recorded");
    const hashSection = html.slice(html.indexOf("dossier-part-7"));
    const endHashSection = hashSection.indexOf("dossier-section", 20);
    const tableText = endHashSection > 0 ? hashSection.slice(0, endHashSection) : hashSection;
    expect(tableText).not.toContain("cdr.csv");
    expect(tableText).not.toContain("bank.csv");
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

