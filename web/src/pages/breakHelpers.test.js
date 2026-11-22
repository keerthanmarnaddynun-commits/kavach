import { describe, it, expect } from "vitest";
import { validateBreakGroups, buildBreakViewModel } from "./breakHelpers.js";

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
});
