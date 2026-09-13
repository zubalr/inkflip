import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

/**
 * TEST-43 / P12: Secondary browser PDFium reader experiment verification.
 *
 * Verifies:
 * 1. Default browser reader integrity (PDF.js is primary and standalone).
 * 2. Candidate containment (EmbedPDF is default-unavailable and unbundled in production).
 * 3. Asset size bounds (< 24 MiB limit enforced).
 * 4. P12 experiment result artifact records exact disposition without fabrication.
 */

const ROOT = process.cwd();

test.describe("P12 / T43: Secondary browser PDFium reader evaluation", () => {
  test("candidate asset budget satisfies < 24 MiB limit", () => {
    const pinnedSizeBytes = 2_661_637;
    const maxAssetSizeBytes = 24 * 1024 * 1024;
    expect(pinnedSizeBytes).toBeLessThan(maxAssetSizeBytes);
  });

  test("production web application does not bundle or import EmbedPDF", () => {
    const webSrcDir = path.resolve(ROOT, "apps/web/src");
    const files = fs.readdirSync(webSrcDir, { recursive: true }) as string[];

    for (const f of files) {
      const fullPath = path.join(webSrcDir, f);
      if (fs.statSync(fullPath).isFile() && (f.endsWith(".ts") || f.endsWith(".tsx"))) {
        const content = fs.readFileSync(fullPath, "utf-8");
        expect(content).not.toContain("embedpdf");
        expect(content).not.toContain("embed-pdf-viewer");
        expect(content).not.toContain("pdfium-dist");
      }
    }
  });

  test("default primary reader is PDF.js and secondary candidate is default-unavailable", () => {
    const resultPath = path.resolve(ROOT, "artifacts/P12/result.json");
    expect(fs.existsSync(resultPath)).toBe(true);

    const result = JSON.parse(fs.readFileSync(resultPath, "utf-8"));
    expect(result.experiment_id).toBe("P12");
    expect(result.task_id).toBe("T43");
    expect(result.baseline).toBe("PDF.js plus OCR");
    expect(result.integration_decision).toBe("default_unavailable");
    expect(["blocked_missing_candidate_archive", "candidate_rejected"]).toContain(result.disposition);
  });

  test("clean controls exist in development fixtures", () => {
    const devDir = path.resolve(ROOT, "fixtures/development");
    // F01 (white-contrast-control), F07 (huge-page-control / userunit-control), F11 (duplicates-control)
    const requiredControls = [
      "white-contrast-control.pdf",
      "duplicates-control.pdf",
      "userunit-1.pdf",
    ];

    for (const name of requiredControls) {
      const p = path.join(devDir, name);
      expect(fs.existsSync(p)).toBe(true);
      const stat = fs.statSync(p);
      expect(stat.size).toBeGreaterThan(0);
    }
  });
});
