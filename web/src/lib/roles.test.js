import { describe, it, expect } from "vitest";
import { hasRole, canUpload, canAnalyze, canBreak, canDeleteCase } from "./roles.js";

describe("roles permissions", () => {
  it("evaluates role hierarchy correctly", () => {
    expect(hasRole("admin", "viewer")).toBe(true);
    expect(hasRole("admin", "analyst")).toBe(true);
    expect(hasRole("admin", "admin")).toBe(true);

    expect(hasRole("analyst", "viewer")).toBe(true);
    expect(hasRole("analyst", "analyst")).toBe(true);
    expect(hasRole("analyst", "admin")).toBe(false);

    expect(hasRole("viewer", "viewer")).toBe(true);
    expect(hasRole("viewer", "analyst")).toBe(false);
    expect(hasRole("viewer", "admin")).toBe(false);
  });

  it("restricts upload and analyze to analyst and admin", () => {
    expect(canUpload("viewer")).toBe(false);
    expect(canUpload("analyst")).toBe(true);
    expect(canUpload("admin")).toBe(true);

    expect(canAnalyze("viewer")).toBe(false);
    expect(canAnalyze("analyst")).toBe(true);
    expect(canAnalyze("admin")).toBe(true);
  });

  it("permits viewer, analyst, and admin to run break", () => {
    expect(canBreak("viewer")).toBe(true);
    expect(canBreak("analyst")).toBe(true);
    expect(canBreak("admin")).toBe(true);
    expect(canBreak(null)).toBe(false);
  });

  it("restricts delete case to admin only", () => {
    expect(canDeleteCase("viewer")).toBe(false);
    expect(canDeleteCase("analyst")).toBe(false);
    expect(canDeleteCase("admin")).toBe(true);
    expect(canDeleteCase(null)).toBe(false);
  });
});
