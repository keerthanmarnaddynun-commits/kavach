import { describe, it, expect, vi } from "vitest";
import { buildDossier, formatEvidenceRefs } from "./dossier.js";

// Real fixtures
import caseDetailFixture from "../fixtures/case_detail.json";
import leadsFixture from "../fixtures/leads.json";
import graphFixture from "../fixtures/graph.json";
import peopleFixture from "../fixtures/people.json";

describe("buildDossier view model", () => {
  const dummyUser = { username: "officer_1", role: "analyst" };
  const dummyTime = "2026-11-23 10:00:00 UTC";

  it("limits priority leads to at most ten items and preserves fixture order", () => {
    const dossier = buildDossier({
      caseDetail: caseDetailFixture,
      leads: leadsFixture,
      graph: graphFixture,
      user: dummyUser,
      generatedAt: dummyTime,
    });

    expect(dossier.analyzed).toBe(true);
    expect(dossier.priorityLeads.length).toBeLessThanOrEqual(10);
    expect(dossier.priorityLeads.length).toBe(Math.min(10, leadsFixture.money_flow.length));

    // Verify order is unchanged
    for (let i = 0; i < dossier.priorityLeads.length; i++) {
      expect(dossier.priorityLeads[i].personId).toBe(leadsFixture.money_flow[i].person_id);
      expect(dossier.priorityLeads[i].rank).toBe(leadsFixture.money_flow[i].rank);
      expect(dossier.priorityLeads[i].name).toBe(leadsFixture.money_flow[i].name);
    }
  });

  it("computes counts per node type that sum to the total number of graph nodes", () => {
    const dossier = buildDossier({
      caseDetail: caseDetailFixture,
      leads: leadsFixture,
      graph: graphFixture,
      user: dummyUser,
      generatedAt: dummyTime,
    });

    const countsList = dossier.graphSummary.countsPerType;
    expect(Array.isArray(countsList)).toBe(true);
    expect(countsList.length).toBeGreaterThan(0);

    const sum = countsList.reduce((acc, item) => acc + item.count, 0);
    expect(sum).toBe(graphFixture.elements.nodes.length);
    expect(sum).toBe(dossier.graphSummary.totalNodes);

    // Verify alphabetical ordering of type names
    for (let i = 0; i < countsList.length - 1; i++) {
      expect(countsList[i].type.localeCompare(countsList[i + 1].type)).toBeLessThanOrEqual(0);
    }
  });

  it("includes every hash in the table matching the fixture and preserves 64-char fingerprint", () => {
    const dossier = buildDossier({
      caseDetail: caseDetailFixture,
      leads: leadsFixture,
      graph: graphFixture,
      user: dummyUser,
      generatedAt: dummyTime,
    });

    const ht = dossier.hashTable;

    // Document hashes match fixture
    expect(ht.documents.length).toBe(caseDetailFixture.documents.length);
    for (let i = 0; i < ht.documents.length; i++) {
      const doc = ht.documents[i];
      const fixDoc = caseDetailFixture.documents[i];
      expect(doc.docId).toBe(fixDoc.doc_id);
      expect(doc.sha256Raw).toBe(fixDoc.sha256_raw);
      expect(doc.sha256Text).toBe(fixDoc.sha256_text);
      expect(doc.sha256Raw.length).toBe(64);
      expect(doc.sha256Text.length).toBe(64);
    }

    // CDR and Bank file hashes match fixture
    expect(ht.cdr.sha256).toBe(caseDetailFixture.files.cdr.sha256);
    expect(ht.cdr.sha256.length).toBe(64);
    expect(ht.bank.sha256).toBe(caseDetailFixture.files.bank.sha256);
    expect(ht.bank.sha256.length).toBe(64);

    // Honest CSV file labels
    expect(ht.cdr.fileName).toBe("uploaded file name not recorded");
    expect(ht.bank.fileName).toBe("uploaded file name not recorded");
    expect(ht.cdr.fileName).not.toContain("cdr.csv");
    expect(ht.bank.fileName).not.toContain("bank.csv");

    // Full 64-character fingerprint with zero shortening
    expect(ht.fingerprint).toBe(leadsFixture.document_hash);
    expect(ht.fingerprint.length).toBe(64);
    expect(dossier.title.fingerprint).toBe(leadsFixture.document_hash);
    expect(dossier.title.fingerprint.length).toBe(64);
  });

  it("handles a not-analyzed case returning analyzed false with empty leads", () => {
    const unanalyzedCase = {
      case: {
        ...caseDetailFixture.case,
        analyzed: false,
      },
      documents: caseDetailFixture.documents,
      files: caseDetailFixture.files,
    };

    const dossier = buildDossier({
      caseDetail: unanalyzedCase,
      leads: null,
      graph: null,
      user: dummyUser,
      generatedAt: dummyTime,
    });

    expect(dossier.analyzed).toBe(false);
    expect(dossier.priorityLeads).toEqual([]);
    expect(dossier.detectorLeads.mules).toEqual([]);
    expect(dossier.detectorLeads.burners).toEqual([]);
    expect(dossier.detectorLeads.hasFlagged).toBe(false);
    expect(dossier.graphSummary.totalNodes).toBe(0);
    expect(dossier.title.notAnalyzedMessage).toBe("Case not analyzed: no leads or graph summary.");
  });

  it("formats evidence references for FIR items and CSV items", () => {
    // FIR evidence item
    const firItem = { doc_id: "FIR_05", char_span: [120, 185] };
    const firText = formatEvidenceRefs(firItem);
    expect(firText).toEqual(["FIR_05, 120-185"]);

    // CSV evidence item
    const csvItem = { file: "cdr.csv", rows: [10, 20, 30], row_count: 3 };
    const csvText = formatEvidenceRefs(csvItem);
    expect(csvText[0]).toContain("cdr.csv");
    expect(csvText[0]).toContain("10, 20, 30");
    expect(csvText[0]).toContain("3 total rows");

    // Array containing both
    const mixed = formatEvidenceRefs([firItem, csvItem]);
    expect(mixed.length).toBe(2);
    expect(mixed[0]).toBe("FIR_05, 120-185");
    expect(mixed[1]).toContain("cdr.csv");
  });

  it("formats certificate text containing Section 63(4)(c) and not the legacy section name", () => {
    const dossier = buildDossier({
      caseDetail: caseDetailFixture,
      leads: leadsFixture,
      graph: graphFixture,
      user: dummyUser,
      generatedAt: dummyTime,
    });

    expect(dossier.certificateText).toContain("SECTION 63(4)(c) OF THE BHARATIYA SAKSHYA ADHINIYAM, 2023");
    expect(dossier.certificateText).toContain("PART A (DRAFT TEMPLATE)");
    expect(dossier.certificateText).not.toContain("65B");
    expect(dossier.certificateText).toContain("________");
    expect(dossier.certificateText).toContain(dummyTime);
    expect(dossier.certificateText).toContain(leadsFixture.document_hash);
  });

  it("does not access the system clock and accepts timestamp solely as parameter", () => {
    const dateSpy = vi.spyOn(globalThis, "Date");

    const customTime = "2026-05-15 14:30:00 UTC";
    const dossier = buildDossier({
      caseDetail: caseDetailFixture,
      leads: leadsFixture,
      graph: graphFixture,
      user: dummyUser,
      generatedAt: customTime,
    });

    expect(dossier.title.generatedAt).toBe(customTime);
    expect(dossier.certificateText).toContain(customTime);

    // Assert that no clock calls were made by buildDossier
    expect(dateSpy).not.toHaveBeenCalled();
    dateSpy.mockRestore();
  });

  it("populates firDocuments for known persons in fixture order up to 10 and sets firDocumentTotal", () => {
    const dossier = buildDossier({
      caseDetail: caseDetailFixture,
      leads: leadsFixture,
      graph: graphFixture,
      people: peopleFixture,
      user: dummyUser,
      generatedAt: dummyTime,
    });

    expect(dossier.priorityLeads.length).toBeGreaterThan(0);
    for (const lead of dossier.priorityLeads) {
      const match = peopleFixture.find((p) => (p.person_id || p.id) === lead.personId);
      if (match) {
        const expectedRefs = match.document_references || [];
        expect(lead.firDocuments).toEqual(expectedRefs.slice(0, 10));
        expect(lead.firDocumentTotal).toBe(expectedRefs.length);
        expect(lead.firDocuments.length).toBeLessThanOrEqual(10);
      } else {
        expect(lead.firDocuments).toEqual([]);
        expect(lead.firDocumentTotal).toBe(0);
      }
    }
  });

  it("handles missing person or missing people list with empty firDocuments and total 0", () => {
    const dossierWithoutPeople = buildDossier({
      caseDetail: caseDetailFixture,
      leads: leadsFixture,
      graph: graphFixture,
      user: dummyUser,
      generatedAt: dummyTime,
    });
    for (const lead of dossierWithoutPeople.priorityLeads) {
      expect(lead.firDocuments).toEqual([]);
      expect(lead.firDocumentTotal).toBe(0);
    }

    const nonExistentPeople = [{ person_id: "PERSON:nonexistent", document_references: ["FIR_99"] }];
    const dossierWithOtherPeople = buildDossier({
      caseDetail: caseDetailFixture,
      leads: leadsFixture,
      graph: graphFixture,
      people: nonExistentPeople,
      user: dummyUser,
      generatedAt: dummyTime,
    });
    for (const lead of dossierWithOtherPeople.priorityLeads) {
      expect(lead.firDocuments).toEqual([]);
      expect(lead.firDocumentTotal).toBe(0);
    }
  });
});
