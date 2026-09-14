import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * TEST-14: Findings, coverage and plain explanations browser verification (T14).
 *
 * Acceptance criteria:
 * 1. Normal invisible scan has no warning solely for invisibility (I11).
 * 2. timed-out, model-missing, and unsupported are strictly distinct categories (I05).
 * 3. Zero findings cannot display clean/safe; displays I06 disclaimer.
 * 4. Explanations come from deterministic templates and actual recorded evidence,
 *    not generated truth claims or probabilistic guessing.
 * 5. Review priority ordering: selected > material_token > ordinary > informational.
 * 6. Accessibility: No serious or critical WCAG violations.
 */

const PREVIEW_PATH = "/src/features/findings/preview.html";
const WEB_ROOT = path.resolve(process.cwd(), "apps/web");

let viteServer: any;
let baseUrl: string;

test.beforeAll(async () => {
  const viteModulePath = path.resolve(WEB_ROOT, "node_modules/vite/dist/node/index.js");
  const { createServer } = await import(pathToFileURL(viteModulePath).href);
  viteServer = await createServer({
    root: WEB_ROOT,
    server: {
      port: 0,
      strictPort: false,
      fs: {
        allow: [path.resolve(process.cwd())],
      },
    },
    logLevel: "silent",
  });
  await viteServer.listen();
  baseUrl = viteServer.resolvedUrls.local[0].replace(/\/$/, "");
});

test.afterAll(async () => {
  if (viteServer) {
    await viteServer.close();
  }
});

test.describe("T14: Findings, Coverage and Plain Explanations", () => {
  test("criterion 1: normal invisible scan has no warning solely for invisibility (I11)", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}?scenario=normal-scan`);
    await page.waitForSelector("#coverage-normal-scan-notice");

    const scanNotice = page.locator("#coverage-normal-scan-notice");
    await expect(scanNotice).toBeVisible();

    // Must emit the informative notice copy
    const text = await scanNotice.textContent();
    expect(text).toContain(
      "Searchable scans can contain invisible OCR text. That alone is not a problem.",
    );

    // Must be informative (role note), NOT a warning, error, or alert
    const role = await scanNotice.getAttribute("role");
    expect(role).toBe("note");

    const className = (await scanNotice.getAttribute("class")) || "";
    expect(className.toLowerCase()).not.toContain("warning");
    expect(className.toLowerCase()).not.toContain("danger");
    expect(className.toLowerCase()).not.toContain("error");
    expect(className.toLowerCase()).not.toContain("alert");

    await page.screenshot({
      path: "artifacts/tasks/T14/screenshots/normal-scan.png",
      fullPage: true,
    });
  });

  test("criterion 2: timed-out, model-missing, and unsupported are strictly distinct (I05)", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}?scenario=incomplete-statuses`);
    await page.waitForSelector('[role="group"][aria-label="Check statistics"]');
    // stat cards live inside the collapsed "Check counts by result" details
    const countsDetails = page.locator("details", { has: page.locator("#stat-completed, .statCompleted") }).first();
    if (await countsDetails.count()) await countsDetails.locator("summary").click();

    // Check stats cards breakdown
    const timeoutCard = page.locator("#stat-timeout");
    const modelMissingCard = page.locator("#stat-model-missing");
    const unsupportedCard = page.locator("#stat-unsupported");

    await expect(timeoutCard).toBeVisible();
    await expect(modelMissingCard).toBeVisible();
    await expect(unsupportedCard).toBeVisible();

    expect(await timeoutCard.textContent()).toContain("Timed Out");
    expect(await modelMissingCard.textContent()).toContain("Model Missing");
    expect(await unsupportedCard.textContent()).toContain("Unsupported");

    // Check detail status list items
    const statusRows = page.locator('[role="listitem"]');
    const count = await statusRows.count();
    expect(count).toBe(3);

    const rowTexts = await statusRows.allTextContents();
    const joined = rowTexts.join(" | ");

    // Verify distinct descriptions from copy
    expect(joined).toContain("reached its local time limit");
    expect(joined).toContain(
      "OCR could not start. This is a reader error, not an unreadable-page result.",
    );
    expect(joined).toContain("Not supported by this reader");

    // Verify distinct badge labels
    expect(joined).toContain("Timed out");
    expect(joined).toContain("Model missing");
    expect(joined).toContain("Unsupported");

    // Verify check identity and recorded reason are rendered distinctly (P2-2)
    expect(joined).toContain("chk-2");
    expect(joined).toContain("chk-3");
    expect(joined).toContain("chk-4");
    expect(joined).toContain("Page 0 timed out after 10000ms");

    await page.screenshot({
      path: "artifacts/tasks/T14/screenshots/incomplete-statuses.png",
      fullPage: true,
    });
  });

  test("criterion 3: zero findings cannot display clean or safe (I06)", async ({ page }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}?scenario=zero-findings`);
    await page.waitForSelector("#findings-noalert");

    const noAlertNotice = page.locator("#findings-noalert");
    await expect(noAlertNotice).toBeVisible();

    const text = await noAlertNotice.textContent();
    expect(text).toContain(
      "No localized differences were found in completed comparisons. This is not a document safety or correctness check.",
    );

    // Invariant I06 check across findings container and full page
    const pageText = (await page.locator("main").innerText()).toLowerCase();
    expect(pageText).not.toMatch(/\bclean\b/);
    expect(pageText).not.toMatch(/\bsafe\b/);
    expect(pageText).not.toMatch(/\ball-clear\b/);

    await page.screenshot({
      path: "artifacts/tasks/T14/screenshots/zero-findings.png",
      fullPage: true,
    });
  });

  test("criterion 4: explanations come from deterministic templates and actual recorded evidence", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}?scenario=normal-scan`);
    await page.waitForSelector("#finding-f-amount-1");

    const amountCard = page.locator("#finding-f-amount-1");
    await expect(amountCard).toBeVisible();

    // Verbatim comparative readings with reader names and versions
    expect(await amountCard.textContent()).toContain("PDFium v149.0.7825.0 (occurrence #1)");
    expect(await amountCard.textContent()).toContain("pypdf v6.18.0 (occurrence #1)");
    expect(await amountCard.textContent()).toContain("$1,000.00");
    expect(await amountCard.textContent()).toContain("$10,000.00");

    // Material difference badge
    expect(await amountCard.textContent()).toContain("Material difference");

    // Invariant I06 finding disclaimer
    expect(await amountCard.textContent()).toContain(
      "A difference does not establish which reading is correct.",
    );

    // Interactive "How this was checked" disclosure
    const disclosureButton = amountCard.locator("button", { hasText: "How this was checked" });
    await expect(disclosureButton).toBeVisible();
    await disclosureButton.click();

    await expect(
      amountCard.locator("text=Exact coordinate alignment over overlapping tokens."),
    ).toBeVisible();
    await expect(
      amountCard.locator("text=OCR verification was not run on this page."),
    ).toBeVisible();

    await page.screenshot({
      path: "artifacts/tasks/T14/screenshots/findings-card.png",
      fullPage: true,
    });
  });

  test("criterion 5: priority ordering respects selected > material_token > ordinary > informational", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}?scenario=amount-diff`);
    await page.waitForSelector("#findings-list");

    // Card articles in order
    const cardTitles = await page.locator("#findings-list article h3").allTextContents();
    expect(cardTitles.length).toBe(3);

    // First card should be the material_token (amount), then ordinary text, then informational
    expect(cardTitles[0]).toBe("This amount reads differently");
    expect(cardTitles[1]).toBe("These readings differ here");
    expect(cardTitles[2]).toBe("A supported structural check found this property");

    await page.screenshot({
      path: "artifacts/tasks/T14/screenshots/amount-diff.png",
      fullPage: true,
    });
  });

  test("criterion 6: no serious or critical automated accessibility violations (WCAG 2.2 AA)", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}?scenario=normal-scan`);
    await page.waitForSelector("main");

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();

    const seriousOrCritical = accessibilityScanResults.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );

    expect(seriousOrCritical).toEqual([]);
  });

  test("criterion 7: failed, cancelled, and skipped checks have distinct stat cards and badges (P2-1, P2-2)", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}?scenario=all-terminal-statuses`);
    await page.waitForSelector('[role="group"][aria-label="Check statistics"]');
    // stat cards live inside the collapsed "Check counts by result" details
    const countsDetails = page.locator("details", { has: page.locator("#stat-completed, .statCompleted") }).first();
    if (await countsDetails.count()) await countsDetails.locator("summary").click();

    // All terminal categories have distinct stat cards
    await expect(page.locator("#stat-timeout")).toBeVisible();
    await expect(page.locator("#stat-model-missing")).toBeVisible();
    await expect(page.locator("#stat-unsupported")).toBeVisible();
    await expect(page.locator("#stat-failed")).toBeVisible();
    await expect(page.locator("#stat-cancelled")).toBeVisible();
    await expect(page.locator("#stat-skipped")).toBeVisible();

    // Check distinct badge styling in status list
    const failedRow = page.locator("#check-status-failed-chk-failed");
    await expect(failedRow).toBeVisible();
    expect(await failedRow.textContent()).toContain("Failed");
    expect(await failedRow.textContent()).toContain("chk-failed");
    expect(await failedRow.textContent()).toContain("Decoder crashed with syntax error");

    const cancelledRow = page.locator("#check-status-cancelled-chk-cancelled");
    await expect(cancelledRow).toBeVisible();
    expect(await cancelledRow.textContent()).toContain("Cancelled");
    expect(await cancelledRow.textContent()).toContain("chk-cancelled");

    const skippedRow = page.locator("#check-status-skipped-chk-skipped");
    await expect(skippedRow).toBeVisible();
    expect(await skippedRow.textContent()).toContain("Skipped");
    expect(await skippedRow.textContent()).toContain("chk-skipped");
    expect(await skippedRow.textContent()).toContain("Not run: Feature flag disabled");
  });

  test("criterion 8: local notes and annotations render distinctly with non-reader label (P2-3)", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}?scenario=normal-scan`);
    await page.waitForSelector("#note-note-1");

    const noteCard = page.locator("#note-note-1");
    await expect(noteCard).toBeVisible();
    expect(await noteCard.textContent()).toContain(
      "Verified manual ledger entry matches PDFium amount.",
    );
    expect(await noteCard.textContent()).toContain("Reviewer Audit");

    // Must carry the clear disclaimer that it's human interpretation, not reader result
    const notesSection = page.locator('[role="region"][aria-label="Local notes"]');
    expect(await notesSection.textContent()).toContain("Your interpretation (not a reader result)");
    expect(await notesSection.textContent()).toContain(
      "Notes remain local and are included in exports only when selected.",
    );

    // Add note affordance exists
    const addNoteBtn = page.locator("#btn-add-note-f-amount-1");
    await expect(addNoteBtn).toBeVisible();
  });
});
