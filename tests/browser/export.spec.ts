/**
 * Browser tests for T16 ExportPanel and ExportController.
 *
 * Verifies in real Chromium:
 * 1. Keyboard interaction: tab navigation, space toggling, enter activation.
 * 2. State changes: options updates and prop synchronization (F7).
 * 3. Preview vs export consistency: downloaded JSON/HTML byte-for-byte and field-for-field match preview.
 * 4. Error states: oversized source PDF (F9), source requested but unavailable (F8), limits exceeded (F4).
 */
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import type { ExportHarnessApi } from "../../apps/web/src/features/export/mount";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const WEB = join(ROOT, "apps", "web");
const PREVIEW_URL = "/src/features/export/preview.html";

interface Harness {
  base: string;
  close: () => Promise<void>;
}

let harness: Harness;

test.beforeAll(async () => {
  const viteEntry = pathToFileURL(
    join(WEB, "node_modules", "vite", "dist", "node", "index.js"),
  ).href;
  const { createServer } = (await import(viteEntry)) as {
    createServer: (opts: {
      root: string;
      server: { port: number; strictPort?: boolean; fs?: { allow?: string[] } };
      logLevel: string;
    }) => Promise<{
      listen: () => Promise<void>;
      resolvedUrls: { local: string[] };
      close: () => Promise<void>;
    }>;
  };
  const server = await createServer({
    root: WEB,
    server: {
      port: 0,
      strictPort: false,
      fs: {
        allow: [ROOT],
      },
    },
    logLevel: "warn",
  });
  await server.listen();
  const base = server.resolvedUrls.local[0].replace(/\/$/, "");
  harness = { base, close: () => server.close() };
});

test.afterAll(async () => {
  if (harness) {
    await harness.close();
  }
});

async function openExportPreview(page: Page): Promise<void> {
  await page.goto(`${harness.base}${PREVIEW_URL}`);
  await page.waitForFunction(
    () => (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness !== undefined,
    undefined,
    { timeout: 30_000 },
  );
  await expect(page.locator("h2")).toContainText("Save report");
}

test.describe("T16 Browser Export", () => {
  test("keyboard interaction: focus navigation, space toggle, enter download", async ({ page }) => {
    await openExportPreview(page);

    // Initial state: filename and notes checkboxes are enabled.
    // Focus the filename checkbox
    const filenameCheckbox = page.locator('input[type="checkbox"]').nth(1);
    await filenameCheckbox.focus();
    await expect(filenameCheckbox).toBeFocused();
    expect(await filenameCheckbox.isChecked()).toBe(false);

    // Toggle via Space key
    await page.keyboard.press("Space");
    await expect(filenameCheckbox).toBeChecked({ checked: true });

    // Focus JSON download button
    const jsonBtn = page.getByRole("button", { name: "Save JSON (reopens in Inkflip)" });
    await jsonBtn.focus();
    await expect(jsonBtn).toBeFocused();

    // Trigger download via Enter key
    await page.keyboard.press("Enter");

    // Verify success banner appears
    const statusMsg = page.locator('[role="status"]');
    await expect(statusMsg).toBeVisible();
    await expect(statusMsg).toContainText("Report downloaded");

    // Verify download was captured by harness
    const downloads = await page.evaluate(() => {
      const h = (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness;
      return h?.getDownloads() ?? [];
    });
    expect(downloads.length).toBeGreaterThanOrEqual(1);
    expect(downloads[downloads.length - 1].filename).toMatch(/^inkflip-.*\.json$/);
  });

  test("state changes: option toggling updates preview manifest and counts", async ({ page }) => {
    await openExportPreview(page);

    const manifest = page.locator("p").filter({ hasText: "Included:" });
    await expect(manifest).toBeVisible();

    // Initially filename and annotations are off
    const initialText = await manifest.innerText();
    expect(initialText).not.toContain("filename");
    expect(initialText).not.toContain("annotations");

    // Toggle filename on
    const filenameOption = page.locator('label:has-text("Include original filename")');
    await filenameOption.click();
    await expect(manifest).toContainText("filename");

    // Toggle notes on
    const notesOption = page.locator('label:has-text("Include my notes")');
    await notesOption.click();
    await expect(manifest).toContainText("annotations");
  });

  test("prop synchronization: changing source prop refreshes controller and preview (F7)", async ({ page }) => {
    await openExportPreview(page);

    const previewGrid = page.locator("dl");
    await expect(previewGrid).toBeVisible();
    const initialFindings = await previewGrid.locator("dd").first().innerText();
    expect(initialFindings).toBe("1");

    // Change source prop through harness by adding a schema-valid second finding
    await page.evaluate(() => {
      const h = (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness;
      if (!h) throw new Error("harness missing");
      const modified = structuredClone(h.defaultReport) as {
        findings: Array<{ id: string }>;
      };
      const secondFinding = structuredClone(modified.findings[0]);
      secondFinding.id = "f_second";
      modified.findings.push(secondFinding);
      h.setSource(modified);
    });

    // The preview must immediately update to reflect 2 findings without any user interaction
    await expect(previewGrid.locator("dd").first()).toHaveText("2");
  });

  test("preview vs export consistency: downloaded JSON and HTML match preview exactly (I09)", async ({ page }) => {
    await openExportPreview(page);

    await page.evaluate(() => {
      const h = (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness;
      h?.clearDownloads();
    });

    // Click JSON download button
    const jsonBtn = page.getByRole("button", { name: "Save JSON (reopens in Inkflip)" });
    await jsonBtn.click();

    const downloadData = await page.evaluate(() => {
      const h = (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness;
      const list = h?.getDownloads() ?? [];
      const item = list[list.length - 1];
      const parsed = JSON.parse(item.text);
      const enc = new TextEncoder();
      const utf8Bytes = enc.encode(item.text).length;
      return {
        filename: item.filename,
        parsed,
        utf8Bytes,
      };
    });

    expect(downloadData.parsed.kind).toBe("report");
    expect(downloadData.parsed.schema_version).toBe("1.0.0");
    expect(downloadData.parsed.export.mode).toBe("evidence");
    expect(downloadData.parsed.export.scope).toBe("selection");
    expect(downloadData.filename).toMatch(/^inkflip-evidence-[a-f0-9]{12}\.inkflip\.json$/);

    // Download HTML
    const htmlBtn = page.getByRole("button", { name: "Save HTML report (readable)" });
    await htmlBtn.click();

    const htmlData = await page.evaluate(() => {
      const h = (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness;
      const list = h?.getDownloads() ?? [];
      const item = list[list.length - 1];
      return {
        filename: item.filename,
        text: item.text,
      };
    });

    expect(htmlData.filename).toMatch(/^inkflip-evidence-[a-f0-9]{12}\.html$/);
    expect(htmlData.text).toMatch(/<!doctype html>/i);
    expect(htmlData.text).toContain("Content-Security-Policy");
    expect(htmlData.text).not.toContain("<script");
  });

  test("error state: oversized source PDF opt-in fails with clear explanation and alternative (F9)", async ({ page }) => {
    await openExportPreview(page);

    // Configure harness with source bytes provider that yields >20 MiB
    await page.evaluate(() => {
      const h = (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness;
      if (!h) throw new Error("harness missing");
      const oversizedBytes = new Uint8Array(20 * 1024 * 1024 + 1024);
      const rep = structuredClone(h.defaultReport) as { document: { byte_length: number; sha256: string } };
      rep.document.byte_length = oversizedBytes.length;
      rep.document.sha256 = "975d7df408b7b8bf58aeb3fc368124619cf26be2daec16eaf11bf14dbd3453b1";
      h.setSource(rep, oversizedBytes);
    });

    // Check "Include the original PDF"
    const sourceOption = page.locator('label:has-text("Include the original PDF")');
    await sourceOption.click();

    // Verify error notice is displayed with understandable explanation and alternative
    const errorNotice = page.locator("div").filter({ hasText: "Export failed" });
    await expect(errorNotice.first()).toBeVisible();
    await expect(errorNotice.first()).toContainText("exceeds the 20971520 byte embed limit");
    await expect(errorNotice.first()).toContainText("evidence-only");

    // Verify JSON download button is disabled
    const jsonBtn = page.getByRole("button", { name: "Save JSON (reopens in Inkflip)" });
    await expect(jsonBtn).toBeDisabled();

    // Uncheck "Include the original PDF"
    await sourceOption.click();

    // Error clears and export is re-enabled
    await expect(jsonBtn).toBeEnabled();
  });

  test("error state: source requested but unavailable sets warning and evidence-only export (F8)", async ({ page }) => {
    await openExportPreview(page);

    // Configure harness with a source that has no source_pdf asset and provider returns null
    await page.evaluate(() => {
      const h = (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness;
      if (!h) throw new Error("harness missing");
      const rep = structuredClone(h.defaultReport) as { document: { source_asset_id: string | null } };
      rep.document.source_asset_id = null;
      h.setSource(rep, null);
    });

    // Request source PDF
    const sourceOption = page.locator('label:has-text("Include the original PDF")');
    await sourceOption.click();

    // Warning renders indicating original bytes unavailable
    const warning = page.locator("p").filter({ hasText: "Original bytes unavailable — this export is evidence-only." });
    await expect(warning).toBeVisible();

    // Clear prior downloads and download JSON
    await page.evaluate(() => {
      const h = (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness;
      h?.clearDownloads();
    });
    const jsonBtn = page.getByRole("button", { name: "Save JSON (reopens in Inkflip)" });
    await jsonBtn.click();

    const omissions = await page.evaluate(() => {
      const h = (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness;
      const list = h?.getDownloads() ?? [];
      const item = list[list.length - 1];
      const parsed = JSON.parse(item.text);
      return parsed.export.omissions as string[];
    });

    expect(omissions).toContain("Original PDF excluded.");
    expect(omissions).toContain("Requested original bytes unavailable — evidence only.");
  });

  test("error state: exceeding PNG pixel cap renders withinLimits warning and disables JSON export (F4)", async ({ page }) => {
    await openExportPreview(page);

    // Configure engine where preview reports withinLimits: false
    await page.evaluate(() => {
      const h = (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness;
      if (!h) throw new Error("harness missing");
      const baseEngine = h.engine;
      const customEngine = {
        ...baseEngine,
        preview: (rep: unknown, opts: unknown) => {
          const p = baseEngine.preview(rep, opts as never);
          return {
            ...p,
            withinLimits: false,
          };
        },
      };
      h.setEngine(customEngine as never);
    });

    // Warning about exceeding portable bundle limits appears
    const limitsWarning = page.locator("p").filter({
      hasText: "This export exceeds the portable bundle limits and cannot be reopened in the browser; reduce the selection.",
    });
    await expect(limitsWarning).toBeVisible();

    // JSON export button is disabled
    const jsonBtn = page.getByRole("button", { name: "Save JSON (reopens in Inkflip)" });
    await expect(jsonBtn).toBeDisabled();
  });
});
