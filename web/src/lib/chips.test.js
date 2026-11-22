import { describe, it, expect } from "vitest";
import { chipLabel, chipTooltip } from "./chips.js";

describe("chipLabel", () => {
  it("extracts chip property from chip objects", () => {
    expect(chipLabel({ chip: "Mule", reason: "Pass-through account" })).toBe("Mule");
  });

  it("extracts name or role when chip property is omitted in object", () => {
    expect(chipLabel({ name: "Operator" })).toBe("Operator");
    expect(chipLabel({ role: "Leader" })).toBe("Leader");
  });

  it("handles plain strings", () => {
    expect(chipLabel("SUSPECT")).toBe("SUSPECT");
    expect(chipLabel("Direct")).toBe("Direct");
  });

  it("handles null or undefined missing values", () => {
    expect(chipLabel(null)).toBe("");
    expect(chipLabel(undefined)).toBe("");
  });

  it("handles empty object or numeric values", () => {
    expect(chipLabel({})).toBe("");
    expect(chipLabel(42)).toBe("42");
  });
});

describe("chipTooltip", () => {
  it("extracts reason from chip objects", () => {
    expect(chipTooltip({ chip: "Mule", reason: "High velocity" })).toBe("High velocity");
    expect(chipTooltip({ chip: "Direct" })).toBeUndefined();
    expect(chipTooltip("SUSPECT")).toBeUndefined();
  });
});
