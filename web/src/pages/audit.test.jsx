import { describe, it, expect } from "vitest";
import React from "react";
import { renderToString } from "react-dom/server";
import {
  sanitizeAuditDetail,
  formatAuditDetail,
  formatAuditTime,
  formatShortHash,
  filterAuditEntries,
  calculatePagination,
} from "./auditHelpers.js";
import { AuditLogView } from "./AuditLog.jsx";

describe("Audit Log Helpers", () => {
  describe("sanitizeAuditDetail and formatAuditDetail", () => {
    it("strips password, token, secret, and pbkdf2 hash values", () => {
      const sensitiveDetail = {
        username: "investigator1",
        password: "supersecretpassword",
        secret_key: "abc12345",
        token: "jwt.token.here",
        pwd_hash: "pbkdf2_sha256$1000$salt$hash",
        assigned_role: "analyst",
      };

      const clean = sanitizeAuditDetail(sensitiveDetail);
      expect(clean.username).toBe("investigator1");
      expect(clean.assigned_role).toBe("analyst");
      expect(clean.password).toBeUndefined();
      expect(clean.secret_key).toBeUndefined();
      expect(clean.token).toBeUndefined();
      expect(clean.pwd_hash).toBeUndefined();
    });

    it("formats clean detail into readable comma-separated string", () => {
      const detail = { case_name: "Operation Hawk", documents: 4 };
      const formatted = formatAuditDetail(detail);
      expect(formatted).toContain("case_name: Operation Hawk");
      expect(formatted).toContain("documents: 4");
    });

    it("returns dash for empty or null detail", () => {
      expect(formatAuditDetail(null)).toBe("-");
      expect(formatAuditDetail({})).toBe("-");
    });
  });

  describe("formatAuditTime and formatShortHash", () => {
    it("formats ISO timestamps into date and time strings", () => {
      expect(formatAuditTime("2026-11-27T10:48:30.123456+00:00")).toBe("2026-11-27 10:48:30");
      expect(formatAuditTime(null)).toBe("-");
    });

    it("shortens 64-char hashes to 8 characters", () => {
      const hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
      expect(formatShortHash(hash, 8)).toBe("e3b0c442");
      expect(formatShortHash(null)).toBe("-");
    });
  });

  describe("filterAuditEntries", () => {
    const sampleEntries = [
      { seq: 1, actor: "alice_admin", action: "case_created", case_id: "C-1111111111" },
      { seq: 2, actor: "bob_analyst", action: "document_uploaded", case_id: "C-1111111111" },
      { seq: 3, actor: "charlie_viewer", action: "break_run", case_id: "C-2222222222" },
    ];

    it("returns all entries when filter text is empty", () => {
      expect(filterAuditEntries(sampleEntries, "")).toHaveLength(3);
    });

    it("filters entries by user name", () => {
      const res = filterAuditEntries(sampleEntries, "alice");
      expect(res).toHaveLength(1);
      expect(res[0].actor).toBe("alice_admin");
    });

    it("filters entries by action", () => {
      const res = filterAuditEntries(sampleEntries, "break_run");
      expect(res).toHaveLength(1);
      expect(res[0].action).toBe("break_run");
    });

    it("filters entries by case id", () => {
      const res = filterAuditEntries(sampleEntries, "C-2222");
      expect(res).toHaveLength(1);
      expect(res[0].case_id).toBe("C-2222222222");
    });
  });

  describe("calculatePagination", () => {
    it("calculates page numbers, offsets and ranges correctly", () => {
      // First page of 50 with 50 items
      const p1 = calculatePagination(0, 50, 50, 120);
      expect(p1.currentPage).toBe(1);
      expect(p1.hasPrev).toBe(false);
      expect(p1.hasNext).toBe(true);
      expect(p1.nextOffset).toBe(50);
      expect(p1.rangeStart).toBe(1);
      expect(p1.rangeEnd).toBe(50);

      // Second page of 50 with 50 items
      const p2 = calculatePagination(50, 50, 50, 120);
      expect(p2.currentPage).toBe(2);
      expect(p2.hasPrev).toBe(true);
      expect(p2.hasNext).toBe(true);
      expect(p2.prevOffset).toBe(0);
      expect(p2.nextOffset).toBe(100);

      // Last page with 20 items
      const p3 = calculatePagination(100, 50, 20, 120);
      expect(p3.currentPage).toBe(3);
      expect(p3.hasPrev).toBe(true);
      expect(p3.hasNext).toBe(false);
      expect(p3.rangeStart).toBe(101);
      expect(p3.rangeEnd).toBe(120);
    });
  });
});

describe("AuditLogView Component", () => {
  const sampleEntries = [
    {
      seq: 1,
      ts: "2026-11-27T10:00:00+00:00",
      actor: "admin_user",
      role: "admin",
      action: "case_created",
      case_id: "C-1111111111",
      detail: { name: "Operation Delta" },
      prev_hash: "0000000000000000000000000000000000000000000000000000000000000000",
      hash: "1111111122222222333333334444444455555555666666667777777788888888",
    },
    {
      seq: 2,
      ts: "2026-11-27T10:05:00+00:00",
      actor: "analyst_user",
      role: "analyst",
      action: "break_run",
      case_id: "C-1111111111",
      detail: { group_a: ["P1"], group_b: ["P2"] },
      prev_hash: "1111111122222222333333334444444455555555666666667777777788888888",
      hash: "99999999aaaaaaaaabbbbbbbbccccccccddddddddeeeeeeeeffffffff00000000",
    },
  ];

  describe("Route guard for non-admin roles", () => {
    it("renders Admin access required message for viewer role", () => {
      const html = renderToString(
        <AuditLogView
          user={{ username: "viewer1", role: "viewer" }}
          entries={sampleEntries}
        />
      );
      expect(html).toContain("Admin access required");
      expect(html).not.toContain("Operation Delta");
      expect(html).not.toContain("Verify chain");
    });

    it("renders Admin access required message for analyst role", () => {
      const html = renderToString(
        <AuditLogView
          user={{ username: "analyst1", role: "analyst" }}
          entries={sampleEntries}
        />
      );
      expect(html).toContain("Admin access required");
      expect(html).not.toContain("Operation Delta");
    });

    it("renders Admin access required message for unauthenticated user", () => {
      const html = renderToString(
        <AuditLogView
          user={null}
          entries={sampleEntries}
        />
      );
      expect(html).toContain("Admin access required");
    });
  });

  describe("Admin view rendering", () => {
    it("renders Audit Log page with disclaimer, table, and shortened hashes for admin", () => {
      const html = renderToString(
        <AuditLogView
          user={{ username: "admin1", role: "admin" }}
          entries={sampleEntries}
        />
      );

      expect(html).not.toContain("Admin access required");
      expect(html).toContain("Audit Log");
      // Required plain-wording note
      expect(html).toContain(
        "The chain is unkeyed: someone with file access could rewrite the whole log, and removal of the last entries would not be detected."
      );
      expect(html).toContain("Verify chain");
      expect(html).toContain("admin_user");
      expect(html).toContain("case_created");
      expect(html).toContain("Operation Delta");
      expect(html).toContain("C-1111111111");

      // Shortened hashes (first 8 chars)
      expect(html).toContain("00000000");
      expect(html).toContain("11111111");
      expect(html).toContain("99999999");
      // Full hash in tooltip / title attribute
      expect(html).toContain("title=\"1111111122222222333333334444444455555555666666667777777788888888\"");
    });

    it("renders empty state message when no entries are present", () => {
      const html = renderToString(
        <AuditLogView
          user={{ username: "admin1", role: "admin" }}
          entries={[]}
        />
      );
      expect(html).toContain("No audit log entries found.");
    });
  });

  describe("Verify chain result rendering", () => {
    it("renders intact verification result line", () => {
      const html = renderToString(
        <AuditLogView
          user={{ username: "admin1", role: "admin" }}
          entries={sampleEntries}
          verifyResult={{ ok: true, entries: 42, first_bad_index: null }}
          verifyTime="10:30:00 AM"
        />
      );

      expect(html).toContain("Chain intact: 42 entries verified");
      expect(html).toContain("10:30:00 AM");
    });

    it("renders broken chain result line with failure index", () => {
      const html = renderToString(
        <AuditLogView
          user={{ username: "admin1", role: "admin" }}
          entries={sampleEntries}
          verifyResult={{ ok: false, entries: 5, first_bad_index: 6 }}
          verifyTime="10:35:00 AM"
        />
      );

      expect(html).toContain("Chain broken at entry 6");
      expect(html).toContain("10:35:00 AM");
    });
  });
});
