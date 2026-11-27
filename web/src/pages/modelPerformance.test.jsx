import { describe, it, expect } from "vitest";
import React from "react";
import { renderToString } from "react-dom/server";
import snapshot from "../data/model_performance.json";
import {
  formatPercent,
  formatScore,
  formatMs,
  getHeadlineData,
  getPerTypeItems,
  getErrorClasses,
  getGeneralisationGapData,
  getBaselineModels,
  getSpeedData,
} from "./modelPerformanceHelpers.js";
import { ModelPerformance } from "./ModelPerformance.jsx";

describe("Model Performance Helpers", () => {
  describe("Formatting helpers", () => {
    it("formats percentages, scores, and milliseconds safely", () => {
      expect(formatPercent(0.7891)).toBe("78.9%");
      expect(formatPercent(null)).toBe("-");
      expect(formatScore(0.78906)).toBe("0.7891");
      expect(formatScore(null)).toBe("-");
      expect(formatMs(684.947)).toBe("684.9 ms");
      expect(formatMs(null)).toBe("-");
    });
  });

  describe("Headline helper", () => {
    it("extracts headline numbers directly from snapshot", () => {
      const data = getHeadlineData(snapshot);
      expect(data.heldOut.mentionsF1).toBe("0.7891");
      expect(data.heldOut.relationsF1).toBe("0.3182");
      expect(data.syntheticTest.mentionsF1).toBe("0.9992");
      expect(data.syntheticTest.relationsF1).toBe("0.9672");
      expect(data.caption).toBe("Synthetic test: 50 FIRs; independent held-out: 25 FIRs");
      expect(data.provenance).toContain("step7_llm_heldout_r2");
    });

    it("handles null or empty snapshot safely", () => {
      const data = getHeadlineData(null);
      expect(data.heldOut.mentionsF1).toBe("-");
      expect(data.syntheticTest.mentionsF1).toBe("-");
    });
  });

  describe("Per-type items helper (Block B and C)", () => {
    it("switches correctly between strict and lenient metrics", () => {
      const heldOutEntities = snapshot.entities_by_type.held_out;
      const strictItems = getPerTypeItems(heldOutEntities, "strict", "name", "asc");
      const lenientItems = getPerTypeItems(heldOutEntities, "lenient", "name", "asc");

      const personStrict = strictItems.find((i) => i.name === "PERSON");
      const personLenient = lenientItems.find((i) => i.name === "PERSON");

      expect(personStrict.f1).toBe(0.6502);
      expect(personLenient.f1).toBe(0.749);
      expect(personStrict.gold).toBe(92);
      expect(personLenient.gold).toBe(92);
    });

    it("switches correctly between held-out and synthetic test datasets", () => {
      const heldOut = getPerTypeItems(snapshot.entities_by_type.held_out, "strict");
      const synthetic = getPerTypeItems(snapshot.entities_by_type.synthetic_test, "strict");

      expect(heldOut.length).toBe(12);
      expect(synthetic.length).toBe(7);

      const personHeldOut = heldOut.find((i) => i.name === "PERSON");
      const personSynthetic = synthetic.find((i) => i.name === "PERSON");

      expect(personHeldOut.gold).toBe(92);
      expect(personSynthetic.gold).toBe(383);
    });

    it("sorts items by score and name in both directions", () => {
      const items = getPerTypeItems(snapshot.entities_by_type.held_out, "strict", "f1", "desc");
      expect(items[0].f1).toBeGreaterThanOrEqual(items[items.length - 1].f1);

      const ascItems = getPerTypeItems(snapshot.entities_by_type.held_out, "strict", "f1", "asc");
      expect(ascItems[0].f1).toBeLessThanOrEqual(ascItems[ascItems.length - 1].f1);

      const nameItems = getPerTypeItems(snapshot.entities_by_type.held_out, "strict", "name", "asc");
      expect(nameItems[0].name.localeCompare(nameItems[nameItems.length - 1].name)).toBeLessThanOrEqual(0);
    });

    it("handles empty items array gracefully", () => {
      expect(getPerTypeItems(null)).toEqual([]);
      expect(getPerTypeItems([])).toEqual([]);
    });
  });

  describe("Error breakdown helper (Block D)", () => {
    it("extracts mention and relation error classes and verifies percentage sums", () => {
      const mentionFp = getErrorClasses(snapshot.error_breakdown, "mentions", "fp");
      const mentionFn = getErrorClasses(snapshot.error_breakdown, "mentions", "fn");
      const relationFp = getErrorClasses(snapshot.error_breakdown, "relations", "fp");
      const relationFn = getErrorClasses(snapshot.error_breakdown, "relations", "fn");

      expect(mentionFp.length).toBeGreaterThan(0);
      expect(mentionFn.length).toBeGreaterThan(0);
      expect(relationFp.length).toBeGreaterThan(0);
      expect(relationFn.length).toBeGreaterThan(0);

      // Check sum of percentages roughly equals 100% (allowing small rounding difference)
      const sumFpPct = mentionFp.reduce((acc, c) => acc + c.pct, 0);
      expect(sumFpPct).toBeGreaterThanOrEqual(99.0);
      expect(sumFpPct).toBeLessThanOrEqual(101.0);

      // Check real examples presence
      const repeatShort = mentionFp.find((c) => c.className === "REPEAT_SHORT_FORM");
      expect(repeatShort).toBeDefined();
      expect(repeatShort.examples.length).toBeGreaterThan(0);
      expect(repeatShort.examples[0].surface).toBeDefined();
    });

    it("handles null or missing error data gracefully", () => {
      expect(getErrorClasses(null, "mentions", "fp")).toEqual([]);
      expect(getErrorClasses({}, "mentions", "fp")).toEqual([]);
    });
  });

  describe("Generalisation gap helper (Block E)", () => {
    it("returns gap comparison metrics directly from snapshot", () => {
      const data = getGeneralisationGapData(snapshot);
      expect(data.comparison.length).toBe(2);
      expect(data.comparison[0].synthetic_test).toBe(0.9992);
      expect(data.comparison[0].held_out).toBe(0.7891);
      expect(data.comparison[0].gap).toBe(0.2101);
      expect(data.provenance).toContain("step7_llm_heldout_r2");
    });
  });

  describe("Baselines helper (Block F)", () => {
    it("returns baseline models with their respective metrics", () => {
      const data = getBaselineModels(snapshot.baselines, "f1");
      expect(data.models.length).toBe(4);
      expect(data.caption).toContain("Synthetic test, 50 FIRs");

      const regex = data.models.find((m) => m.modelId === "regex");
      const pipeline = data.models.find((m) => m.modelId === "pipeline");

      expect(regex.precision).toBe(1.0);
      expect(regex.f1).toBe(0.6271);
      expect(pipeline.f1).toBe(0.9992);
    });
  });

  describe("Speed latency helper (Block G)", () => {
    it("returns latency stages and totals from snapshot", () => {
      const data = getSpeedData(snapshot.speed);
      expect(data.stages.length).toBe(6);
      expect(data.total.mean_ms).toBe(684.95);
      expect(data.total.p95_ms).toBe(965.17);
      expect(data.modelLoadMs).toBe(11854.83);
    });
  });

  describe("Single source of truth verification", () => {
    it("ensures every metric displayed on the helper layer originates from the snapshot JSON", () => {
      const h = getHeadlineData(snapshot);
      expect(h.heldOut.mentionsF1).toBe(snapshot.headline.held_out.mention_strict_f1.toFixed(4));
      expect(h.heldOut.relationsF1).toBe(snapshot.headline.held_out.relation_micro_f1.toFixed(4));
      expect(h.syntheticTest.mentionsF1).toBe(snapshot.headline.synthetic_test.mention_strict_f1.toFixed(4));
      expect(h.syntheticTest.relationsF1).toBe(snapshot.headline.synthetic_test.relation_micro_f1.toFixed(4));

      const b = getBaselineModels(snapshot.baselines, "f1");
      b.models.forEach((m) => {
        const sourceModel = snapshot.baselines.models.find((sm) => sm.model_id === m.modelId);
        expect(m.f1).toBe(sourceModel.f1);
        expect(m.precision).toBe(sourceModel.precision);
        expect(m.recall).toBe(sourceModel.recall);
      });

      const s = getSpeedData(snapshot.speed);
      expect(s.total.mean_ms).toBe(snapshot.speed.total.mean_ms);
      expect(s.total.p95_ms).toBe(snapshot.speed.total.p95_ms);
    });
  });
});

describe("ModelPerformance Component Rendering", () => {
  describe("Route guard for non-admin roles", () => {
    it("renders Admin access required message for viewer role", () => {
      const html = renderToString(<ModelPerformance user={{ username: "viewer1", role: "viewer" }} />);
      expect(html).toContain("Admin access required");
      expect(html).not.toContain("Entity extraction by type");
      expect(html).not.toContain("Speed (latency per stage)");
    });

    it("renders Admin access required message for analyst role", () => {
      const html = renderToString(<ModelPerformance user={{ username: "analyst1", role: "analyst" }} />);
      expect(html).toContain("Admin access required");
      expect(html).not.toContain("Entity extraction by type");
    });

    it("renders Admin access required message when user is null", () => {
      const html = renderToString(<ModelPerformance user={null} />);
      expect(html).toContain("Admin access required");
    });
  });

  describe("Admin view rendering all blocks", () => {
    const adminUser = { username: "admin_tester", role: "admin" };

    it("renders Block A: Headline strip with strict mention F1, relation micro F1 and dataset counts", () => {
      const html = renderToString(<ModelPerformance user={adminUser} />);
      expect(html).toContain("Model performance");
      expect(html).toContain("0.7891");
      expect(html).toContain("0.3182");
      expect(html).toContain("0.9992");
      expect(html).toContain("0.9672");
      expect(html).toContain("Synthetic test: 50 FIRs; independent held-out: 25 FIRs");
      expect(html).toContain("step7_llm_heldout_r2 &amp; step6_extraction_r3");
    });

    it("renders Block B: Entity extraction by type with toggles and table", () => {
      const html = renderToString(<ModelPerformance user={adminUser} />);
      expect(html).toContain("Entity extraction by type");
      expect(html).toContain("Held-out");
      expect(html).toContain("Synthetic test");
      expect(html).toContain("Strict");
      expect(html).toContain("Lenient");
      expect(html).toContain("PERSON");
      expect(html).toContain("ALIAS");
      expect(html).toContain("PHONE");
      expect(html).toContain("ACCOUNT");
    });

    it("renders Block C: Relation extraction by type with table and support", () => {
      const html = renderToString(<ModelPerformance user={adminUser} />);
      expect(html).toContain("Relation extraction by type");
      expect(html).toContain("OWNS_DEVICE");
      expect(html).toContain("ASSOCIATED_IMEI");
      expect(html).toContain("COMMUNICATED_WITH");
      expect(html).toContain("CONTROLS_ACCOUNT");
      expect(html).toContain("TRANSFERRED_FUNDS");
    });

    it("renders Block D: How it fails with error classes and example errors", () => {
      const html = renderToString(<ModelPerformance user={adminUser} />);
      expect(html).toContain("How it fails (held-out error breakdown)");
      expect(html).toContain("REPEAT_SHORT_FORM");
      expect(html).toContain("INSIDE_GOLD_RIGHT");
      expect(html).toContain("Showing up to 5 real examples from errors.json");
    });

    it("renders Block E: Generalisation gap comparison", () => {
      const html = renderToString(<ModelPerformance user={adminUser} />);
      expect(html).toContain("Generalisation gap");
      expect(html).toContain("Mentions F1 (strict)");
      expect(html).toContain("Relations F1 (micro)");
      expect(html).toContain("Gap: -0.2101");
      expect(html).toContain("Gap: -0.6490");
    });

    it("renders Block F: Against baselines with caption", () => {
      const html = renderToString(<ModelPerformance user={adminUser} />);
      expect(html).toContain("Against baselines");
      expect(html).toContain("Regex baseline");
      expect(html).toContain("spaCy (Davlan/XLM-R)");
      expect(html).toContain("Flair (IndicNER)");
      expect(html).toContain("Our pipeline");
      expect(html).toContain("Synthetic test, 50 FIRs. Only mentions evaluated (baselines do not extract relations).");
    });

    it("renders Block G: Speed latency stages and total", () => {
      const html = renderToString(<ModelPerformance user={adminUser} />);
      expect(html).toContain("Speed (latency per stage)");
      expect(html).toContain("Total: 685.0 ms");
      expect(html).toContain("p95: 965.2 ms");
      expect(html).toContain("Model load: 11854.8 ms");
      expect(html).toContain("Neural model inference");
      expect(html).toContain("Contract validation");
    });
  });
});
