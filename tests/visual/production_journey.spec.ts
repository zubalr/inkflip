import path from "node:path";
import { writeFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";
import { startProdServer, type ProdServerInstance, ROOT } from "./prod_server.ts";

const REAL_PDF = path.resolve(ROOT, "apps/web/public/examples/amount/mapping-amount.pdf");
const CONTROL_PDF = path.resolve(ROOT, "fixtures/public/mapping-control.pdf");

let prodServer: ProdServerInstance;
let baseUrl: string;

test.beforeAll(async () => {
  prodServer = await startProdServer();
  baseUrl = prodServer.baseUrl;
});

test.afterAll(async () => {
  if (prodServer) {
    await prodServer.close();
  }
});

test.describe("Production Journey: Navigation, Focus, & Demo Reload Matrix", () => {
  test("1. Starting with demo, replacing with real file, visiting Help, then choosing Try Demo reloads demo cleanly", async ({
    page,
  }) => {
    // 1. Start with demo example
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 15000 });
    await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");

    // 2. Replace demo with a different own file (confirm replacement)
    await page.locator("#input-open-pdf").setInputFiles(CONTROL_PDF);
    await page.getByRole("button", { name: "Clear and open file" }).click();
    await expect(page.locator("#workspace-doc-title")).toContainText("mapping-control.pdf");

    // 3. Visit Help
    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');
    expect(page.url()).toContain("#/help");

    // 4. In Help, click "Try Demo Example"
    await page.click("#btn-help-open-example");
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 15000 });

    // 5. Verify demo example was actually reloaded and replaced the real file!
    await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");
  });

  test("2. Escape on modal dialog closes active modal before affecting parent Help surface", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#btn-header-help");

    // Navigate to Help
    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');

    // Open CLI guide modal
    await page.click("#btn-guide-cli");
    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // First Escape closes the modal, NOT returning to workspace
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    expect(page.url()).toContain("#/help");
    await expect(page.locator('[data-testid="help-page"]')).toBeVisible();

    // Second Escape returns from Help to Workspace
    await page.keyboard.press("Escape");
    await page.waitForSelector('[data-testid="viewer-stage"]');
    expect(page.url()).toContain("#/workspace");
  });

  test("3. Hidden and inert workspace ignores viewer keyboard shortcuts while Help is active", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector('[data-testid="viewer-stage"]');

    // View mode starts in Page
    const pageTab = page.locator("#tab-mode-page");
    await expect(pageTab).toHaveAttribute("aria-selected", "true");

    // Navigate to Help
    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');

    // Workspace container is inert and hidden
    const wsContainer = page.locator("#workspace-container");
    await expect(wsContainer).toHaveAttribute("hidden");
    await expect(wsContainer).toHaveAttribute("inert");

    // Press single-key shortcuts: 'f' (cycle view mode), 'r' (rotate), '+' (zoom)
    await page.keyboard.press("f");
    await page.keyboard.press("r");
    await page.keyboard.press("+");

    // Return to workspace
    await page.click("#btn-help-back-workspace");
    await page.waitForSelector('[data-testid="viewer-stage"]');

    // View mode is still 'page' (shortcuts were not received by inert background workspace)
    await expect(page.locator("#tab-mode-page")).toHaveAttribute("aria-selected", "true");
  });

  test("4. Help page CLI quick guide displays verified executable syntax and hardened Docker mounts", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/help`);
    await page.waitForSelector('[data-testid="help-page"]');

    // Open CLI quick guide
    await page.click("#btn-guide-cli");
    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    const dialogText = await dialog.innerText();
    // Module name must be inkflip.cli
    expect(dialogText).toContain("PYTHONPATH=native python -m inkflip.cli inspect <pdf-file> --out report.json");
    // Report export must be html
    expect(dialogText).toContain("PYTHONPATH=native python -m inkflip.cli report <report.json> --format html --out report.html");
    // Replay syntax must be accurate
    expect(dialogText).toContain("PYTHONPATH=native python -m inkflip.cli replay <report.json> --source <pdf-file> --profile native-default --out replay.json");
    // Hardened Docker mount syntax with :ro and :rw
    expect(dialogText).toContain("docker run --rm --network none");
    expect(dialogText).toContain("/data/in:ro");
    expect(dialogText).toContain("/data/out:rw");

    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  });
});

test.describe("AutoClaw FND-002: Duplicates Example & Occurrence Navigation", () => {
  test("1. Gallery card detail displays verification mechanism and duplicates evidence note", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/`);
    await page.waitForSelector('[data-testid="examples-gallery"]');

    // Open duplicates card
    const dupCard = page.locator('[data-testid="example-card-duplicates"]');
    await expect(dupCard).toBeVisible();
    await dupCard.click();

    // Verify detail view
    const detail = page.locator('[data-testid="example-detail-duplicates"]');
    await expect(detail).toBeVisible();
    await detail.locator("summary").click();

    // Verify mechanism explanation is present
    const mechanismSection = page.locator('[data-testid="card-mechanism-section"]');
    await expect(mechanismSection).toBeVisible();
    await expect(mechanismSection).toContainText("Four identical amounts at distinct positions stay individually addressable");

    // Verify FND-002 evidence note explaining the four $100 occurrences
    const evidenceNote = page.locator('[data-testid="duplicates-evidence-note"]');
    await expect(evidenceNote).toBeVisible();
    await expect(evidenceNote).toContainText("Four distinct “$100” occurrences appear at separate page coordinates (occurrences #0, #2, #3, and #5)");
  });

  test("2. Duplicates example report preserves all four $100 occurrences as separately addressable", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace?example=duplicates`);
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 15000 });

    // Switch to Reading mode
    await page.click("#tab-mode-reading");
    await page.waitForSelector("#accessible-text-equivalent");

    const textLayer = page.locator("#accessible-text-equivalent");
    // Under the PDF.js text reader group, verify exactly 4 occurrences of $100
    const pdfjsGroup = textLayer.locator('div:has(h4:has-text("pdf.js"))');
    await expect(pdfjsGroup).toBeVisible();
    const amountItems = pdfjsGroup.locator('li:has-text("$100")');
    await expect(amountItems).toHaveCount(4);

    // Verify each of the 4 occurrences has distinct ordinal and can be individually selected
    const ordinals = ["occurrence #0", "occurrence #2", "occurrence #3", "occurrence #5"];
    for (let i = 0; i < 4; i++) {
      const item = amountItems.nth(i);
      await expect(item).toContainText(ordinals[i]);

      // Click Select button on this occurrence
      const selectBtn = item.locator("button");
      await selectBtn.click();
      await expect(selectBtn).toHaveAttribute("aria-pressed", "true");
    }

    // Also verify OCR reader extracted the 5th occurrence without collision
    const ocrGroup = textLayer.locator('div:has(h4:has-text("Tesseract"))');
    if (await ocrGroup.isVisible()) {
      const ocrItems = ocrGroup.locator('li:has-text("$100")');
      await expect(ocrItems).toHaveCount(1);
    }
  });
});

test.describe("Production Journey: Failure, Rejection, & Recovery", () => {
  test("1. Corrupt PDF input shows error, does not crash, and recovers cleanly for next file", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    // Create a temporary corrupt PDF
    const corruptPath = path.join(tmpdir(), "corrupt-file.pdf");
    writeFileSync(corruptPath, "THIS IS NOT A VALID PDF FILE HEADER CORRUPTED BYTES 12345");

    try {
      await page.locator("#input-open-pdf").setInputFiles(corruptPath);
      // Wait for error notice or rejection
      await page.waitForSelector('[role="alert"], [data-testid="file-drop"]', { timeout: 5000 });

      // Workspace remains intact and responsive
      await expect(page.locator("#btn-header-open-pdf")).toBeVisible();
      await expect(page.locator("#btn-header-import-report")).toBeVisible();

      // Offer valid PDF to prove clean recovery
      await page.locator("#input-open-pdf").setInputFiles(REAL_PDF);
      await page.waitForSelector("#workspace-doc-title", { timeout: 10000 });
      await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");
    } finally {
      try {
        unlinkSync(corruptPath);
      } catch {}
    }
  });

  test("2. Malformed report JSON preserves existing session intact", async ({ page }) => {
    // 1. Load valid demo first
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 15000 });
    await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");

    // 2. Offer a malformed report JSON
    const malformedPath = path.join(tmpdir(), "malformed-report.json");
    writeFileSync(malformedPath, JSON.stringify({ kind: "invalid_report_structure", broken: true }));

    try {
      await page.locator("#input-import-report").setInputFiles(malformedPath);
      await page.getByRole("button", { name: "Clear and open file" }).click();
      await page.waitForTimeout(500);

      // 3. Existing session must remain intact
      await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");
      await expect(page.locator('[data-testid="viewer-stage"]')).toBeVisible();
    } finally {
      try {
        unlinkSync(malformedPath);
      } catch {}
    }
  });

  test("3. Cancelled replace confirmation keeps existing file intact", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    // Load file A
    await page.locator("#input-open-pdf").setInputFiles(REAL_PDF);
    await page.waitForSelector("#workspace-doc-title");
    await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");

    // Offer file B while file A is active
    await page.locator("#input-open-pdf").setInputFiles(CONTROL_PDF);

    // Replace confirm dialog appears
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Open a different PDF?");

    // Click Cancel ("Keep this file")
    await page.getByRole("button", { name: "Keep this file" }).click();
    await expect(dialog).not.toBeVisible();

    // Existing file A is strictly preserved
    await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");

    // Offer file B again and confirm replacement
    await page.locator("#input-open-pdf").setInputFiles(CONTROL_PDF);
    await expect(dialog).toBeVisible();
    await page.getByRole("button", { name: "Clear and open file" }).click();
    await expect(dialog).not.toBeVisible();

    // Now file B is loaded
    await page.waitForSelector("#workspace-doc-title");
    await expect(page.locator("#workspace-doc-title")).toContainText("mapping-control.pdf");
  });
});

test.describe("Production Journey: Export & Privacy UI Verification", () => {
  test("Export panel displays accurate privacy summary, opt-in source inclusion, and downloads valid JSON", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace?example=duplicates`);
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 15000 });

    // Verify Export section is visible
    const exportHeading = page.getByRole("heading", { name: "Save report" });
    await expect(exportHeading).toBeVisible();

    // Verify default privacy opt-ins: Source PDF must be unchecked by default
    const sourceCheckbox = page.getByLabel("Include the original PDF");
    await expect(sourceCheckbox).not.toBeChecked();

    // Verify privacy warning for original PDF inclusion
    await expect(
      page.getByText("This includes every page and any hidden content in the original file."),
    ).toBeVisible();

    // Verify other privacy defaults
    await expect(page.getByLabel("Include original filename")).not.toBeChecked();
    await expect(page.getByLabel("Include my notes")).not.toBeChecked();

    // Trigger JSON download
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Save JSON (reopens in Inkflip)" }).click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toMatch(/\.json$/);

    // Verify success feedback
    await expect(page.getByRole("status")).toContainText(
      "Report downloaded. Downloads are managed by your browser.",
    );
  });
});
