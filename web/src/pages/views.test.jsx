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
import {
  parseHighlightIdsFromUrl,
  saveHighlightIds,
  getSavedHighlightIds,
} from "./graphHelpers.js";

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

  it("renders NodeInspectorView with first_record activity and counterparts", () => {
    const selectedItem = {
      type: "node",
      id: "PHONE:9876543210",
      data: {
        id: "PHONE:9876543210",
        label: "9876543210",
        type: "PHONE",
        value: "9876543210",
      },
    };
    const inspectorData = {
      node_id: "PHONE:9876543210",
      first_fir: {
        first_fir_id: "FIR_01",
        date: "2026-01-01",
        related_entities: [{ id: "PERSON:1", label: "John Doe", relation: "OWNS_DEVICE" }],
        other_entities: [],
      },
      first_record: {
        file: "cdr",
        timestamp: "2026-01-01T08:00:00",
        rows: [1, 2],
        counterparts: ["9876543211", "351756051523999"],
      },
    };

    const html = renderToString(
      <NodeInspectorView
        caseId="C-01"
        selectedItem={selectedItem}
        data={inspectorData}
        onNeighbourClick={() => {}}
      />
    );

    expect(html).toContain("First seen in records");
    expect(html).toContain("2026-01-01T08:00:00");
    expect(html).toContain("9876543211");
    expect(html).toContain("351756051523999");
    expect(html).toContain("#/case/C-01/evidence/rows/cdr?rows=1,2&amp;highlight=9876543210");
  });

  it("renders NodeInspectorView when neither FIR nor records exist", () => {
    const selectedItem = {
      type: "node",
      id: "IMEI:351756051523999",
      data: {
        id: "IMEI:351756051523999",
        label: "351756051523999",
        type: "IMEI",
        value: "351756051523999",
      },
    };
    const emptyData = {
      node_id: "IMEI:351756051523999",
      first_fir: null,
      first_record: null,
    };

    const html = renderToString(
      <NodeInspectorView
        caseId="C-01"
        selectedItem={selectedItem}
        data={emptyData}
        onNeighbourClick={() => {}}
      />
    );

    expect(html).toContain("Not mentioned in any FIR and no activity in the records");
  });

  it("renders NodeInspectorView when only record activity exists without FIR", () => {
    const selectedItem = {
      type: "node",
      id: "ACCOUNT:ACCT_100",
      data: {
        id: "ACCOUNT:ACCT_100",
        label: "ACCT_100",
        type: "ACCOUNT",
        value: "ACCT_100",
      },
    };
    const recordOnlyData = {
      node_id: "ACCOUNT:ACCT_100",
      first_fir: { first_fir_id: null, date: null, related_entities: [], other_entities: [] },
      first_record: {
        file: "bank",
        timestamp: "2026-01-01T10:00:00",
        rows: [5],
        counterparts: ["ACCT_200"],
      },
    };

    const html = renderToString(
      <NodeInspectorView
        caseId="C-01"
        selectedItem={selectedItem}
        data={recordOnlyData}
        onNeighbourClick={() => {}}
      />
    );

    expect(html).toContain("Not mentioned in any FIR");
    expect(html).toContain("First seen in records");
    expect(html).toContain("ACCT_200");
    expect(html).toContain("#/case/C-01/evidence/rows/bank?rows=5&amp;highlight=ACCT_100");
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

  it("renders NodeInspectorView with First FIR mention and related entities", () => {
    const selectedItem = {
      type: "node",
      id: "ACCOUNT:95217729622",
      data: { id: "ACCOUNT:95217729622", label: "95217729622", type: "ACCOUNT" },
    };
    const dataWithFirstFir = {
      node_id: "ACCOUNT:95217729622",
      first_fir: {
        first_fir_id: "FIR_01",
        date: "2026-01-05",
        related_entities: [
          { id: "PERSON:1", label: "Rajendra Singh", type: "PERSON", relation: "CONTROLS_ACCOUNT" },
        ],
        other_entities: [
          { id: "VEHICLE:1", label: "DL-5C-AB-5012", type: "VEHICLE" },
        ],
      },
    };

    const html = renderToString(
      <NodeInspectorView
        caseId="C-01"
        selectedItem={selectedItem}
        data={dataWithFirstFir}
        onShowFirstFir={() => {}}
      />
    );
    expect(html).toContain("First FIR Mention");
    expect(html).toContain("First FIR mention:");
    expect(html).toContain("FIR_01");
    expect(html).toContain("#/case/C-01/evidence/doc/FIR_01");
    expect(html).toContain("Show first FIR mention");
    expect(html).toContain("Rajendra Singh");
    expect(html).toContain("CONTROLS_ACCOUNT");
    expect(html).toContain("Also mentioned in this FIR (1)");
    expect(html).toContain("DL-5C-AB-5012");
  });

  it("renders NodeInspectorView for CSV-only node saying Not mentioned in any FIR", () => {
    const selectedItem = {
      type: "node",
      id: "ACCOUNT:999999",
      data: { id: "ACCOUNT:999999", label: "999999", type: "ACCOUNT" },
    };
    const csvOnlyData = {
      node_id: "ACCOUNT:999999",
      first_fir: {
        first_fir_id: null,
        date: null,
        related_entities: [],
        other_entities: [],
      },
    };

    const html = renderToString(
      <NodeInspectorView
        caseId="C-01"
        selectedItem={selectedItem}
        data={csvOnlyData}
      />
    );
    expect(html).toContain("First FIR Mention");
    expect(html).toContain("Not mentioned in any FIR");
    expect(html).not.toContain("Show first FIR mention");
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

  it("renders BreakView example buttons when examples are provided", () => {
    const examples = [
      {
        label: "Example 1: 2 + 2 people, 1 bridge",
        groupA: ["P1", "P2"],
        groupB: ["P3", "P4"],
        result: { finite: true, size: 1, cut: [{ person_id: "P5", name: "Farooq" }] },
      },
      {
        label: "Example 2: 2 + 2 people, 2 bridges",
        groupA: ["P6", "P7"],
        groupB: ["P8", "P9"],
        result: { finite: true, size: 2, cut: [{ person_id: "P10" }, { person_id: "P11" }] },
      },
    ];

    const html = renderToString(
      <BreakView
        caseId="C-01"
        people={peopleFixture || []}
        examples={examples}
        loadingExamples={false}
      />
    );
    expect(html).toContain("Try an example:");
    expect(html).toContain("Example 1: 2 + 2 people, 1 bridge");
    expect(html).toContain("Example 2: 2 + 2 people, 2 bridges");
  });

  it("renders Finding examples... loading state when loadingExamples is true", () => {
    const html = renderToString(
      <BreakView
        caseId="C-01"
        people={peopleFixture || []}
        examples={[]}
        loadingExamples={true}
      />
    );
    expect(html).toContain("Finding examples...");
  });

  it("renders selected example with checked checkboxes and Show on graph link", () => {
    const example = {
      label: "Example 1: 2 + 2 people, 1 bridge",
      groupA: ["PERSON:FIR_01:ent_02", "PERSON:FIR_02:ent_02"],
      groupB: ["PERSON:FIR_01:ent_09", "PERSON:FIR_06:ent_02"],
      result: {
        finite: true,
        size: 1,
        cut: [{ person_id: "PERSON:FIR_23:ent_05", name: "Farooq Ahmed" }],
        direct_link: false,
        bridging_unowned_phones: [],
        note: "Only observed calls used.",
        disclaimer: "Leads are decision support.",
      },
    };

    const vm = {
      finite: true,
      size: 1,
      cut: example.result.cut,
      directLink: false,
      bridgingPhones: [],
      note: example.result.note,
      disclaimer: example.result.disclaimer,
      isEmptyCut: false,
      emptyCutMessage: "No observed link between the groups on the call layer.",
    };

    const html = renderToString(
      <BreakView
        caseId="C-927fc7de12"
        people={[
          { id: "PERSON:FIR_01:ent_02", name: "Vikas Sharma" },
          { id: "PERSON:FIR_02:ent_02", name: "Pankaj Tiwari" },
          { id: "PERSON:FIR_01:ent_09", name: "Bikas Sharma" },
          { id: "PERSON:FIR_06:ent_02", name: "Aslam Parvez" },
        ]}
        groupA={example.groupA}
        groupB={example.groupB}
        breakVm={vm}
        examples={[example]}
      />
    );

    expect(html).toContain("Show on graph");
    expect(html).toContain("Farooq Ahmed");
    expect(html).toContain("#/case/C-927fc7de12/graph?select=PERSON%3AFIR_23%3Aent_05");
  });

  it("renders BreakView with Connects column, Clear button, and footnote", () => {
    const vm = {
      finite: true,
      size: 1,
      cut: [{ person_id: "PERSON:1", name: "Rashid Khan" }],
      cutDetails: {
        "PERSON:1": {
          person_id: "PERSON:1",
          connects: [{ pair_text: "Aslam Parvez <-> Suresh Pal" }],
          highlight_ids: ["PERSON:1", "PHONE:123"],
        },
      },
      directLink: false,
      bridgingPhones: [],
      note: "Only observed calls used.",
      disclaimer: "Leads are decision support.",
      isEmptyCut: false,
    };

    const html = renderToString(
      <BreakView
        caseId="C-927fc7de12"
        people={[{ id: "PERSON:1", name: "Rashid Khan" }]}
        breakVm={vm}
      />
    );

    expect(html).toContain("Connects");
    expect(html).toContain("Aslam Parvez &lt;-&gt; Suresh Pal");
    expect(html).toContain("Clear");
    expect(html).toContain("Each person in the cut links the pairs shown; not every person links every member.");
    expect(html).toContain("hl=PERSON%3A1%2CPHONE%3A123");
  });

  it("renders BreakView with Clear A and Clear B buttons in group headers", () => {
    const html = renderToString(
      <BreakView
        caseId="C-927fc7de12"
        people={[{ id: "P1", name: "Alice" }]}
        groupA={["P1"]}
        groupB={[]}
      />
    );

    expect(html).toContain("Clear A");
    expect(html).toContain("Clear B");
    expect(html).toContain("Filter Group A...");
    expect(html).toContain("Filter Group B...");
  });

  it("parses highlight IDs from URL and handles storage fallback", () => {
    const hl = parseHighlightIdsFromUrl("#/case/C-01/graph?select=P1&hl=P1,PHONE:123");
    expect(hl).toEqual(["P1", "PHONE:123"]);

    saveHighlightIds(["P1", "PHONE:456"]);
    expect(getSavedHighlightIds()).toEqual(["P1", "PHONE:456"]);

    saveHighlightIds(null);
    expect(getSavedHighlightIds()).toEqual([]);
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
    expect(html).toContain("First Seen Identifiers");
    expect(html).toContain("First seen means the first time it appears in the uploaded records, not when it first existed.");
    expect(html).toContain("Phones (");
    expect(html).toContain("Accounts (");
    expect(html).toContain("IMEIs (");
  });

  it("renders TimelineView with accounts and imeis tabs and links", () => {
    const sampleData = {
      calls: [],
      transfers: [],
      first_seen: [{ phone: "9876543210", t: "2026-01-01T07:00:00" }],
      first_seen_accounts: [{ account: "ACC_998877", id: "ACC_998877", t: "2026-01-01T08:00:00" }],
      first_seen_imeis: [{ imei: "351756051523999", id: "351756051523999", t: "2026-01-01T09:00:00" }],
    };

    // Render with activeTab="accounts" and caseId
    const accountsHtml = renderToString(
      <TimelineView
        caseId="C-TEST"
        bucket="day"
        data={sampleData}
        activeTab="accounts"
      />
    );
    expect(accountsHtml).toContain("Accounts (1)");
    expect(accountsHtml).toContain("ACC_998877");
    expect(accountsHtml).toContain("#/case/C-TEST/graph?select=ACCOUNT%3AACC_998877&amp;firstfir=1");

    // Render with activeTab="imeis" and caseId
    const imeisHtml = renderToString(
      <TimelineView
        caseId="C-TEST"
        bucket="day"
        data={sampleData}
        activeTab="imeis"
      />
    );
    expect(imeisHtml).toContain("IMEIs (1)");
    expect(imeisHtml).toContain("351756051523999");
    expect(imeisHtml).toContain("#/case/C-TEST/graph?select=IMEI%3A351756051523999&amp;firstfir=1");

    // Render with activeTab="phones" and caseId
    const phonesHtml = renderToString(
      <TimelineView
        caseId="C-TEST"
        bucket="day"
        data={sampleData}
        activeTab="phones"
      />
    );
    expect(phonesHtml).toContain("Phones (1)");
    expect(phonesHtml).toContain("9876543210");
    expect(phonesHtml).toContain("#/case/C-TEST/graph?select=PHONE%3A9876543210&amp;firstfir=1");

    // Render without caseId shows plain text
    const noCaseHtml = renderToString(
      <TimelineView
        bucket="day"
        data={sampleData}
        activeTab="accounts"
      />
    );
    expect(noCaseHtml).toContain("ACC_998877");
    expect(noCaseHtml).not.toContain("graph?select=");
  });

  it("renders TimelineView with example markers and key when categories exist", () => {
    const sampleData = {
      calls: [],
      transfers: [],
      first_seen: [
        {
          phone: "9876543210",
          t: "2026-01-01T07:00:00",
          first_fir: { first_fir_id: "FIR_01", related_count: 3 },
          first_record: { timestamp: "2026-01-01T07:00:00", counterparts: ["9876543211"] },
        },
        {
          phone: "9876543211",
          t: "2026-01-01T07:00:00",
          first_fir: null,
          first_record: { timestamp: "2026-01-01T07:00:00", counterparts: ["9876543210"] },
        },
      ],
      first_seen_accounts: [],
      first_seen_imeis: [],
    };

    const html = renderToString(
      <TimelineView
        caseId="C-TEST"
        bucket="day"
        data={sampleData}
        activeTab="phones"
      />
    );

    expect(html).toContain("Example tags:");
    expect(html).toContain("FIR + records");
    expect(html).toContain("Records only");
    expect(html).toContain("#/case/C-TEST/graph?select=PHONE%3A9876543210&amp;firstfir=1");
    expect(html).toContain("#/case/C-TEST/graph?select=PHONE%3A9876543211&amp;firstfir=1");
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

