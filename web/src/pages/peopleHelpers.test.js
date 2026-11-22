import { describe, it, expect } from "vitest";
import { filterPeople } from "./peopleHelpers.js";

describe("filterPeople", () => {
  const people = [
    {
      id: "P1",
      name: "Vikas Sharma",
      aliases: ["Kallu", "Viku"],
      owned_phones: ["9876543210"],
      controlled_accounts: ["ACC123"],
      documents: ["FIR_01"],
      suggested_same_person: [{ other_person_id: "P2", reasons: ["same_name"] }],
    },
    {
      id: "P2",
      name: "Rajendra Singh",
      aliases: ["Raju"],
      owned_phones: ["9123456789"],
      controlled_accounts: ["ACC456"],
      documents: ["FIR_05"],
      suggested_same_person: [],
    },
  ];

  it("returns all people when query is empty", () => {
    expect(filterPeople(people, "")).toHaveLength(2);
    expect(filterPeople(people, "   ")).toHaveLength(2);
  });

  it("filters by name case-insensitively", () => {
    const res = filterPeople(people, "vikas");
    expect(res).toHaveLength(1);
    expect(res[0].name).toBe("Vikas Sharma");
  });

  it("filters by alias", () => {
    const res = filterPeople(people, "raju");
    expect(res).toHaveLength(1);
    expect(res[0].name).toBe("Rajendra Singh");
  });

  it("filters by phone or account", () => {
    expect(filterPeople(people, "98765")).toHaveLength(1);
    expect(filterPeople(people, "ACC456")).toHaveLength(1);
  });

  it("filters by suggested same person id", () => {
    expect(filterPeople(people, "P2")).toHaveLength(2); // P2 is itself and P1 links to P2
  });

  it("handles null or empty array safely", () => {
    expect(filterPeople(null, "abc")).toEqual([]);
  });
});
