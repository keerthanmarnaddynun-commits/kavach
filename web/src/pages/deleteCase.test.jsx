import { describe, it, expect, beforeEach } from "vitest";
import React from "react";
import { renderToString } from "react-dom/server";
import { canDeleteCase } from "../lib/roles.js";
import {
  clearCaseCaches,
  breakExamplesCache,
  breakStateCache,
  setCachedBreakExamples,
  setCachedBreakState,
  getCachedBreakExamples,
  getCachedBreakState,
} from "./breakHelpers.js";
import {
  insightViewCache,
  setCachedInsightView,
  getCachedInsightView,
} from "./timelineHelpers.js";
import { DeleteCaseModal } from "../components/DeleteCaseModal.jsx";
import { CaseListView } from "../App.jsx";
import { CaseRail } from "../components/CaseRail.jsx";
import { Break } from "./Break.jsx";

describe("Case Deletion Frontend", () => {
  beforeEach(() => {
    breakExamplesCache.clear();
    breakStateCache.clear();
    insightViewCache.clear();
  });

  describe("canDeleteCase role check", () => {
    it("permits admin and forbids analyst and viewer", () => {
      expect(canDeleteCase("admin")).toBe(true);
      expect(canDeleteCase("analyst")).toBe(false);
      expect(canDeleteCase("viewer")).toBe(false);
      expect(canDeleteCase(null)).toBe(false);
      expect(canDeleteCase(undefined)).toBe(false);
    });
  });

  describe("clearCaseCaches", () => {
    it("clears break examples, break state, and insight view for the target case while keeping others", () => {
      const c1 = "C-1111111111";
      const c2 = "C-2222222222";

      // Seed caches
      setCachedBreakExamples(c1, [{ id: "ex1" }]);
      setCachedBreakExamples(c2, [{ id: "ex2" }]);
      setCachedBreakState(c1, { groupA: ["P1"], groupB: ["P2"] });
      setCachedBreakState(c2, { groupA: ["P3"], groupB: ["P4"] });
      setCachedInsightView(c1, "Calls only");
      setCachedInsightView(c2, "Transfers only");

      expect(getCachedBreakExamples(c1)).toHaveLength(1);
      expect(getCachedBreakExamples(c2)).toHaveLength(1);
      expect(getCachedBreakState(c1)?.groupA).toEqual(["P1"]);
      expect(getCachedBreakState(c2)?.groupA).toEqual(["P3"]);
      expect(getCachedInsightView(c1)).toBe("Calls only");
      expect(getCachedInsightView(c2)).toBe("Transfers only");

      // Clear caches for c1
      clearCaseCaches(c1);

      expect(getCachedBreakExamples(c1)).toBeNull();
      expect(getCachedBreakState(c1)).toBeNull();
      expect(getCachedInsightView(c1)).toBe("Both");

      // c2 is unaffected
      expect(getCachedBreakExamples(c2)).toHaveLength(1);
      expect(getCachedBreakState(c2)?.groupA).toEqual(["P3"]);
      expect(getCachedInsightView(c2)).toBe("Transfers only");
    });
  });

  describe("DeleteCaseModal component", () => {
    it("does not render HTML when isOpen is false", () => {
      const html = renderToString(
        <DeleteCaseModal
          isOpen={false}
          caseId="C-1234567890"
          caseName="Demo Case"
          onClose={() => {}}
          onDeleted={() => {}}
        />
      );
      expect(html).toBe("");
    });

    it("renders modal dialog with confirmation instructions, input, and disabled delete button", () => {
      const html = renderToString(
        <DeleteCaseModal
          isOpen={true}
          caseId="C-1234567890"
          caseName="Operation Hawk"
          onClose={() => {}}
          onDeleted={() => {}}
        />
      );

      expect(html).toContain("Delete Case");
      expect(html).toContain("Operation Hawk");
      expect(html).toContain("C-1234567890");
      expect(html).toContain("data-testid=\"delete-case-input\"");
      expect(html).toContain("data-testid=\"delete-case-confirm-button\"");
      expect(html).toContain("disabled=\"\"");
      expect(html).toContain("Cancel");
    });
  });

  describe("CaseListView delete button visibility", () => {
    const dummyCases = [
      {
        case_id: "C-1111111111",
        name: "Case Alpha",
        created_at: "2026-01-01T00:00:00",
        counts: { documents: 2, cdr_rows: 10, bank_rows: 5 },
        analyzed: true,
      },
    ];

    it("shows Delete case button for admin user", () => {
      const html = renderToString(
        <CaseListView
          cases={dummyCases}
          user={{ username: "admin1", role: "admin" }}
          onSelectCase={() => {}}
          onDeleteCase={() => {}}
        />
      );
      expect(html).toContain("delete-case-list-btn");
      expect(html).toContain("Delete case");
    });

    it("hides Delete case button for analyst and viewer users", () => {
      const analystHtml = renderToString(
        <CaseListView
          cases={dummyCases}
          user={{ username: "analyst1", role: "analyst" }}
          onSelectCase={() => {}}
          onDeleteCase={() => {}}
        />
      );
      expect(analystHtml).not.toContain("delete-case-list-btn");

      const viewerHtml = renderToString(
        <CaseListView
          cases={dummyCases}
          user={{ username: "viewer1", role: "viewer" }}
          onSelectCase={() => {}}
          onDeleteCase={() => {}}
        />
      );
      expect(viewerHtml).not.toContain("delete-case-list-btn");
    });
  });

  describe("CaseRail navigation and button visibility", () => {
    const dummyCases = [
      {
        case_id: "C-1111111111",
        name: "Case Alpha",
        counts: { documents: 2, cdr_rows: 10, bank_rows: 5 },
      },
    ];

    it("renders All cases link in the rail", () => {
      const html = renderToString(
        <CaseRail
          cases={dummyCases}
          activeCaseId="C-1111111111"
          user={{ username: "admin1", role: "admin" }}
          defaultCollapsed={false}
        />
      );
      expect(html).toContain("all-cases-link");
      expect(html).toContain("All cases");
      expect(html).toContain("href=\"#/cases\"");
    });

    it("hides Delete button in rail for all roles including admin", () => {
      const adminHtml = renderToString(
        <CaseRail
          cases={dummyCases}
          activeCaseId="C-1111111111"
          user={{ username: "admin1", role: "admin" }}
          defaultCollapsed={false}
        />
      );
      expect(adminHtml).not.toContain("delete-case-rail-btn");

      const analystHtml = renderToString(
        <CaseRail
          cases={dummyCases}
          activeCaseId="C-1111111111"
          user={{ username: "analyst1", role: "analyst" }}
          defaultCollapsed={false}
        />
      );
      expect(analystHtml).not.toContain("delete-case-rail-btn");

      const viewerHtml = renderToString(
        <CaseRail
          cases={dummyCases}
          activeCaseId="C-1111111111"
          user={{ username: "viewer1", role: "viewer" }}
          defaultCollapsed={false}
        />
      );
      expect(viewerHtml).not.toContain("delete-case-rail-btn");
    });
  });

  describe("Break permission gating", () => {
    it("renders Break page controls for viewer role", () => {
      const html = renderToString(
        <Break
          caseId="C-1111111111"
          user={{ username: "viewer1", role: "viewer" }}
        />
      );
      expect(html).not.toContain("Requires the analyst role");
      expect(html).not.toContain("Requires the viewer role");
      expect(html).toContain("Courier Break Analysis");
      expect(html).toContain("Loading case individuals...");
    });

    it("renders role requirement message when user has no role", () => {
      const html = renderToString(
        <Break
          caseId="C-1111111111"
          user={null}
        />
      );
      expect(html).toContain("Requires the viewer role");
    });
  });
});
