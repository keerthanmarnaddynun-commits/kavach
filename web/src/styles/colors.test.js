import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const srcDir = path.resolve(__dirname, "..");

function getSourceFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "fixtures") continue;
      files.push(...getSourceFiles(fullPath));
    } else if (entry.isFile()) {
      if (
        entry.name.includes(".test.") ||
        entry.name === "tokens.css"
      ) {
        continue;
      }
      if (/\.(js|jsx|css|html)$/.test(entry.name)) {
        files.push(fullPath);
      }
    }
  }
  return files;
}

describe("Design Palette Rule (Repair 4)", () => {
  it("ensures no raw hex or rgb() or rgba() anywhere in web/src except tokens.css", () => {
    const files = getSourceFiles(srcDir);
    expect(files.length).toBeGreaterThan(0);

    const rawColorPattern = /(#[0-9a-fA-F]{3,8}|rgba?\s*\()/;
    const violations = [];

    for (const file of files) {
      const content = fs.readFileSync(file, "utf-8");
      const lines = content.split("\n");
      lines.forEach((line, idx) => {
        if (rawColorPattern.test(line)) {
          const relPath = path.relative(srcDir, file);
          violations.push(`${relPath}:${idx + 1}: ${line.trim()}`);
        }
      });
    }

    expect(violations).toEqual([]);
  });
});
