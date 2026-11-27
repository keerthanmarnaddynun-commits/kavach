import { describe, it, expect } from "vitest";
import React from "react";
import { renderToString } from "react-dom/server";
import snapshot from "../data/pipeline_walkthrough.json";
import {
  getSampleList,
  getSampleData,
  getStepData,
  getCodeMap,
  getTypeStyle,
  splitTextIntoHighlightedSegments,
} from "./howItWorksHelpers.js";
import { HowItWorks } from "./HowItWorks.jsx";

describe("How It Works Helpers", () => {
  describe("getSampleList & getSampleData", () => {
    it("returns official sample FIRs with metadata", () => {
      const list = getSampleList(snapshot);
      expect(list.length).toBe(4);
      expect(list.map((s) => s.sampleId)).toEqual(["FIR_01", "FIR_52", "FIR_94", "FIR_A"]);
      expect(list[0].language).toBe("Hinglish");
      expect(list[1].language).toBe("English");
      expect(list[2].language).toBe("Hindi");
      expect(list[3].language).toContain("Live Demo");

      for (const s of list) {
        expect(s.charCount).toBeGreaterThan(500);
        expect(s.sha256.length).toBe(64);
      }
    });

    it("retrieves sample data by id or falls back to first sample", () => {
      const s1 = getSampleData(snapshot, "FIR_52");
      expect(s1.sample_id).toBe("FIR_52");
      expect(s1.steps.length).toBe(8);

      const fallback = getSampleData(snapshot, "NON_EXISTENT");
      expect(fallback.sample_id).toBe("FIR_01");
    });
  });

  describe("getStepData", () => {
    it("retrieves steps by index and clamps bounds", () => {
      const sample = getSampleData(snapshot, "FIR_01");
      const step0 = getStepData(sample, 0);
      expect(step0.stage_id).toBe("raw");
      expect(step0.step_name).toBe("Raw FIR");

      const step7 = getStepData(sample, 7);
      expect(step7.stage_id).toBe("graph");
      expect(step7.step_name).toBe("Into the Case Graph");

      const clampedLow = getStepData(sample, -5);
      expect(clampedLow.stage_id).toBe("raw");

      const clampedHigh = getStepData(sample, 99);
      expect(clampedHigh.stage_id).toBe("graph");
    });
  });

  describe("getCodeMap", () => {
    it("returns all 7 stage code references without code snippets", () => {
      const map = getCodeMap(snapshot);
      expect(map.length).toBe(7);

      const stageIds = map.map((m) => m.stage_id);
      expect(stageIds).toContain("model");
      expect(stageIds).toContain("postprocess");
      expect(stageIds).toContain("names_identifiers");
      expect(stageIds).toContain("assemble");
      expect(stageIds).toContain("relations");
      expect(stageIds).toContain("validate");
      expect(stageIds).toContain("graph");

      for (const st of map) {
        expect(st.entries.length).toBeGreaterThan(0);
        for (const entry of st.entries) {
          expect(entry.file).toMatch(/\.(py|js)$/);
          expect(entry.function).toBeTruthy();
          expect(entry.role).toBeTruthy();
          expect(entry.role.length).toBeGreaterThan(15);
        }
      }
    });
  });

  describe("getTypeStyle", () => {
    it("returns appropriate palette variables for entity types and detection source", () => {
      const modelPerson = getTypeStyle("PERSON", "model");
      expect(modelPerson.backgroundColor).toBe("var(--accent-weak)");
      expect(modelPerson.color).toBe("var(--accent)");
      expect(modelPerson.border).toContain("dashed");

      const rulePhone = getTypeStyle("PHONE", "rule");
      expect(rulePhone.backgroundColor).toBe("var(--tag-fir-bg)");
      expect(rulePhone.border).toContain("solid");

      const ruleAccount = getTypeStyle("ACCOUNT", "rule");
      expect(ruleAccount.backgroundColor).toBe("var(--tag-records-bg)");
      expect(ruleAccount.border).toContain("solid");

      const ruleImei = getTypeStyle("IMEI", "rule");
      expect(ruleImei.backgroundColor).toBe("var(--highlight)");
      expect(ruleImei.border).toContain("solid");
    });
  });

  describe("splitTextIntoHighlightedSegments", () => {
    it("splits text into styled segments without overlapping tags", () => {
      const text = "Accused Ramesh (9823011223) was detained.";
      const spans = [
        { start: 8, end: 14, type: "PERSON", source: "model", surface: "Ramesh" },
        { start: 16, end: 26, type: "PHONE", source: "rule", surface: "9823011223" },
      ];

      const segments = splitTextIntoHighlightedSegments(text, spans, null);
      expect(segments.length).toBeGreaterThan(2);

      const personSeg = segments.find((s) => s.isSpan && s.span.type === "PERSON");
      expect(personSeg).toBeDefined();
      expect(personSeg.text).toBe("Ramesh");
      expect(personSeg.span.source).toBe("model");

      const phoneSeg = segments.find((s) => s.isSpan && s.span.type === "PHONE");
      expect(phoneSeg).toBeDefined();
      expect(phoneSeg.text).toBe("9823011223");
    });

    it("marks segments inside active relation evidence sentence", () => {
      const text = "Sentence one. Accused Ramesh operated 9823011223 yesterday. Sentence three.";
      const spans = [
        { start: 22, end: 28, type: "PERSON", source: "model" },
        { start: 38, end: 48, type: "PHONE", source: "rule" },
      ];
      const evidenceSpan = [14, 59]; // Second sentence

      const segments = splitTextIntoHighlightedSegments(text, spans, evidenceSpan);
      const inEvSegments = segments.filter((s) => s.inEvidence);
      expect(inEvSegments.length).toBeGreaterThan(0);

      const fullInEvText = inEvSegments.map((s) => s.text).join("");
      expect(fullInEvText).toBe("Accused Ramesh operated 9823011223 yesterday.");
    });
  });
});

describe("HowItWorks Component Rendering", () => {
  const adminUser = { username: "admin1", role: "admin" };
  const analystUser = { username: "analyst1", role: "analyst" };
  const viewerUser = { username: "viewer1", role: "viewer" };

  describe("Route Guard", () => {
    it("blocks access for non-admin roles", () => {
      const analystHtml = renderToString(<HowItWorks user={analystUser} />);
      expect(analystHtml).toContain("Admin access required");
      expect(analystHtml).not.toContain("pipeline-stepper");

      const viewerHtml = renderToString(<HowItWorks user={viewerUser} />);
      expect(viewerHtml).toContain("Admin access required");

      const anonHtml = renderToString(<HowItWorks user={null} />);
      expect(anonHtml).toContain("Admin access required");
    });

    it("permits access for admin role", () => {
      const adminHtml = renderToString(<HowItWorks user={adminUser} />);
      expect(adminHtml).not.toContain("Admin access required");
      expect(adminHtml).toContain("How the NLP works");
      expect(adminHtml).toContain("Sample FIR:");
      expect(adminHtml).toContain("Where the code lives");
    });
  });

  describe("Step Render Smoke Tests", () => {
    it("renders Step 0: Raw FIR text and metadata", () => {
      const html = renderToString(<HowItWorks user={adminUser} />);
      expect(html).toContain("Step 0 of 7");
      expect(html).toContain("Raw FIR");
      expect(html).toContain("Receives raw police First Information Report text directly from intake.");
      expect(html).toContain("Document ID");
      expect(html).toContain("FIR_01");
      expect(html).toContain("SHA-256 Digest");
    });

    it("contains stepper controls with all 8 stage titles", () => {
      const html = renderToString(<HowItWorks user={adminUser} />);
      expect(html).toContain("Raw FIR");
      expect(html).toContain("Neural NER Model");
      expect(html).toContain("Postprocessing");
      expect(html).toContain("Names &amp; Identifiers");
      expect(html).toContain("Entity Assembly");
      expect(html).toContain("Relation Extraction");
      expect(html).toContain("Contract Validation");
      expect(html).toContain("Into the Case Graph");
      expect(html).toContain("Previous");
      expect(html).toContain("Next");
    });

    it("contains code map panel with real file paths", () => {
      const html = renderToString(<HowItWorks user={adminUser} />);
      expect(html).toContain("Where the code lives");
    });
  });

  describe("Step 2 Postprocessing Alignment and Caption", () => {
    it("merges B + icky into Bicky in one row and matches row count to cleaned plus dropped mentions", () => {
      const sample = getSampleData(snapshot, "FIR_01");
      const step2 = getStepData(sample, 2);
      expect(step2).toBeDefined();

      const items = step2.new_items;
      const bickyRow = items.find((row) => row.cleaned === "Bicky");
      expect(bickyRow).toBeDefined();
      expect(bickyRow.raw_text).toBe("B + icky");
      expect(bickyRow.raw_pieces).toEqual(["B", "icky"]);
      expect(bickyRow.changes).toContain("merged 2 pieces");
      expect(bickyRow.status).toBe("merged 2 pieces");
      expect(bickyRow.cleaned_span).toEqual([230, 235]);

      const cleanedCount = step2.spans.length;
      const droppedCount = items.filter((row) => row.status === "dropped").length;
      expect(items.length).toBe(cleanedCount + droppedCount);
      expect(items.length).toBe(12);
    });

    it("verifies Hindi sample (FIR_94) Step 2 alignment and mentions", () => {
      const sample = getSampleData(snapshot, "FIR_94");
      expect(sample).toBeDefined();
      expect(sample.sample_id).toBe("FIR_94");
      expect(sample.language).toBe("Hindi");

      const step2 = getStepData(sample, 2);
      expect(step2).toBeDefined();
      const items = step2.new_items;
      const mergedRow = items.find((row) => row.cleaned === "मुख्तार अंसारी");
      expect(mergedRow).toBeDefined();
      expect(mergedRow.changes).toContain("merged 3 pieces");

      const droppedRow = items.find((row) => row.status === "dropped");
      expect(droppedRow).toBeDefined();
    });

    it("renders postprocessing caption note in Step 2", () => {
      const html = renderToString(<HowItWorks user={adminUser} initialStepIndex={2} />);
      expect(html).toContain("Postprocessing is a light clean-up step; most mentions pass through unchanged");
    });
  });
});
