import { describe, it, expect } from "vitest";
import { shortenHash, formatCaseFingerprint, formatNumber, formatDate } from "./format.js";

describe("format utilities", () => {
  it("shortens hashes accurately to specified length", () => {
    const hash = "9d6b9c0ff4e2098b5093b5654fd622";
    expect(shortenHash(hash, 12)).toBe("9d6b9c0ff4e2");
    expect(shortenHash(hash, 8)).toBe("9d6b9c0f");
    expect(shortenHash("")).toBe("");
    expect(shortenHash(null)).toBe("");
  });

  it("formats case fingerprint with analyzed state", () => {
    const hash = "af0c0d67c9387ccba48c628b721e5373a94ce275114b6f72089eccc689393f8b";
    expect(formatCaseFingerprint(true, hash)).toBe("af0c0d67c938");
    expect(formatCaseFingerprint(false, hash)).toBe("not analyzed");
    expect(formatCaseFingerprint(true, "")).toBe("not analyzed");
    expect(formatCaseFingerprint(true, null)).toBe("not analyzed");
  });

  it("formats numbers cleanly", () => {
    expect(formatNumber(1000)).toBe("1,000");
    expect(formatNumber("7483")).toBe("7,483");
    expect(formatNumber(null)).toBe("0");
  });

  it("formats dates into readable ISO slice", () => {
    expect(formatDate("2026-11-20T17:00:00Z")).toContain("2026-11-20 17:00:00");
    expect(formatDate("")).toBe("");
  });
});
