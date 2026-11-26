import { describe, it, expect, vi } from "vitest";
import {
  validateBreakGroups,
  buildBreakViewModel,
  generateCandidateBreakPairs,
  formatExampleLabel,
  findBreakExamples,
} from "./breakHelpers.js";

describe("validateBreakGroups", () => {
  it("rejects empty group A", () => {
    const res = validateBreakGroups([], ["P2"]);
    expect(res.valid).toBe(false);
    expect(res.error).toContain("Group A");
  });

  it("rejects empty group B", () => {
    const res = validateBreakGroups(["P1"], []);
    expect(res.valid).toBe(false);
    expect(res.error).toContain("Group B");
  });

  it("rejects groups with more than 200 members", () => {
    const over200 = Array.from({ length: 201 }, (_, i) => `P${i}`);
    expect(validateBreakGroups(over200, ["P202"]).valid).toBe(false);
    expect(validateBreakGroups(["P1"], over200).valid).toBe(false);
  });

  it("rejects overlapping members between groups A and B", () => {
    const res = validateBreakGroups(["P1", "P2"], ["P2", "P3"]);
    expect(res.valid).toBe(false);
    expect(res.error).toContain("Groups cannot overlap");
    expect(res.error).toContain("P2");
  });

  it("accepts valid non-overlapping groups within 200 members", () => {
    const res = validateBreakGroups(["P1", "P2"], ["P3", "P4"]);
    expect(res.valid).toBe(true);
    expect(res.error).toBe(null);
  });
});

describe("buildBreakViewModel", () => {
  it("handles non-finite or empty cuts with required warning message", () => {
    const nonFiniteData = {
      finite: false,
      size: 0,
      cut: [],
      direct_link: false,
      bridging_unowned_phones: [],
      note: "Only observed calls used.",
      disclaimer: "Leads are decision support.",
    };
    const vm = buildBreakViewModel(nonFiniteData);
    expect(vm.finite).toBe(false);
    expect(vm.isEmptyCut).toBe(true);
    expect(vm.emptyCutMessage).toBe(
      "No observed link between the groups on the call layer. This does not mean the groups are unconnected."
    );
  });

  it("formats finite cut result with persons and bridging unowned phones", () => {
    const realData = {
      finite: true,
      size: 1,
      cut: [{ person_id: "PERSON:FIR_23:ent_05", name: "Farooq Ahmed" }],
      direct_link: false,
      bridging_unowned_phones: ["9876543210"],
      note: "Only observed calls used.",
      disclaimer: "Leads are decision support.",
    };
    const vm = buildBreakViewModel(realData);
    expect(vm.finite).toBe(true);
    expect(vm.size).toBe(1);
    expect(vm.cut.length).toBe(1);
    expect(vm.cut[0].name).toBe("Farooq Ahmed");
    expect(vm.bridgingPhones).toEqual(["9876543210"]);
    expect(vm.isEmptyCut).toBe(false);
    expect(vm.disclaimer).toBe("Leads are decision support.");
    expect(vm.note).toBe("Only observed calls used.");
  });

  it("includes cutDetails if present in data", () => {
    const dataWithDetails = {
      finite: true,
      size: 1,
      cut: [{ person_id: "P1", name: "Person 1" }],
      cut_details: {
        P1: {
          person_id: "P1",
          connects: [{ pair_text: "A <-> B" }],
          highlight_ids: ["P1", "PHONE:123"],
        },
      },
    };
    const vm = buildBreakViewModel(dataWithDetails);
    expect(vm.cutDetails).toBeDefined();
    expect(vm.cutDetails["P1"].connects[0].pair_text).toBe("A <-> B");
  });
});

describe("generateCandidateBreakPairs", () => {
  it("returns empty array when fewer than 4 person IDs are provided", () => {
    expect(generateCandidateBreakPairs([])).toEqual([]);
    expect(generateCandidateBreakPairs(["P1", "P2", "P3"])).toEqual([]);
    expect(generateCandidateBreakPairs(null)).toEqual([]);
  });

  it("generates disjoint candidate pairs with small group sizes (2-5 people per side)", () => {
    const pids = Array.from({ length: 12 }, (_, i) => `PERSON:P_${i}`);
    const pairs = generateCandidateBreakPairs(pids);
    expect(pairs.length).toBeGreaterThan(0);

    for (const pair of pairs) {
      expect(pair.groupA.length).toBeGreaterThanOrEqual(2);
      expect(pair.groupA.length).toBeLessThanOrEqual(5);
      expect(pair.groupB.length).toBeGreaterThanOrEqual(2);
      expect(pair.groupB.length).toBeLessThanOrEqual(5);

      const setA = new Set(pair.groupA);
      const overlap = pair.groupB.some((id) => setA.has(id));
      expect(overlap).toBe(false);
    }
  });
});

describe("formatExampleLabel", () => {
  it("formats singular bridge correctly", () => {
    const label = formatExampleLabel(1, ["P1", "P2"], ["P3", "P4"], { cut: [{ person_id: "P5" }] });
    expect(label).toBe("Example 1: 2 + 2 people, 1 bridge");
  });

  it("formats plural bridges correctly", () => {
    const label = formatExampleLabel(2, ["P1", "P2"], ["P3", "P4", "P5"], {
      size: 2,
      cut: [{ person_id: "P6" }, { person_id: "P7" }],
    });
    expect(label).toBe("Example 2: 2 + 3 people, 2 bridges");
  });

  it("formats no link correctly", () => {
    const label = formatExampleLabel(4, ["P1", "P2"], ["P3", "P4"], { finite: false, cut: [] });
    expect(label).toBe("Example 4: 2 + 2 people, no link");
  });

  it("formats direct link correctly", () => {
    const label = formatExampleLabel(4, ["P1", "P2"], ["P3", "P4"], { direct_link: true, cut: [] });
    expect(label).toBe("Example 4: 2 + 2 people, direct link");
  });
});

describe("findBreakExamples", () => {
  it("returns empty array if input people list is empty or under 4", async () => {
    const mockRequest = vi.fn();
    const result = await findBreakExamples("case-1", [], mockRequest);
    expect(result).toEqual([]);
    expect(mockRequest).not.toHaveBeenCalled();
  });

  it("queries break endpoint, stops when 3 distinct sizes are found, and caps API calls", async () => {
    const mockPeople = Array.from({ length: 10 }, (_, i) => ({
      id: `PERSON:FIR_01:ent_${i}`,
      owned_phones: i % 2 === 0 ? [`900000000${i}`] : [],
    }));

    let callCount = 0;
    const mockRequest = vi.fn().mockImplementation(async (path, opts) => {
      callCount++;
      const body = JSON.parse(opts.body);
      // Simulate distinct cut sizes depending on first element of groupB
      const cutSize = (callCount % 3) + 1;
      return {
        finite: true,
        size: cutSize,
        cut: Array.from({ length: cutSize }, (_, k) => ({ person_id: `BRIDGE_${k}` })),
      };
    });

    const examples = await findBreakExamples("case-1", mockPeople, mockRequest);
    expect(examples.length).toBe(3);
    expect(mockRequest).toHaveBeenCalled();
    expect(mockRequest.mock.calls.length).toBeLessThanOrEqual(30);

    // Each example has label, groupA, groupB, result
    expect(examples[0].label).toContain("Example 1:");
    expect(examples[1].label).toContain("Example 2:");
    expect(examples[2].label).toContain("Example 3:");
  });

  it("stops immediately when cancelled", async () => {
    const mockPeople = Array.from({ length: 10 }, (_, i) => ({
      id: `PERSON:FIR_01:ent_${i}`,
      owned_phones: [`900000000${i}`],
    }));

    let cancelled = false;
    const mockRequest = vi.fn().mockImplementation(async () => {
      cancelled = true; // cancel after first call
      return { finite: false, cut: [] };
    });

    const examples = await findBreakExamples("case-1", mockPeople, mockRequest, () => cancelled);
    expect(mockRequest.mock.calls.length).toBe(1);
    expect(examples).toEqual([]);
  });
});
