import path from "node:path";
import { test, expect } from "@playwright/test";

const ROOT = path.resolve(process.cwd());
const EXAMPLE_REPORT = path.resolve(
  ROOT,
  "planning/contracts/examples/valid/native-evidence.inkflip.json",
);
const REAL_PDF = path.resolve(
  ROOT,
  "apps/web/public/examples/amount/mapping-amount.pdf",
);

import { startProdServer, type ProdServerInstance } from "./prod_server.ts";

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

test.describe("T38: Help Journey & Workspace Preservation", () => {
  test("1. Own-file session preserves loaded PDF, doc title, and state across Help visits (UI button & browser back)", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector("#btn-header-open-pdf");

    // Load real PDF file
    await page.locator("#input-open-pdf").setInputFiles(REAL_PDF);
    await page.waitForSelector("#workspace-doc-title");
    await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");

    // Navigate to Help via header button
    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');
    expect(page.url()).toContain("#/help");

    // Return to workspace via "Return to Workspace" button
    const returnBtn = page.locator("#btn-help-back-workspace");
    await expect(returnBtn).toHaveText("Return to Workspace");
    await returnBtn.click();
    await page.waitForSelector("#workspace-doc-title");

    // Verify own file and docTitle are strictly preserved
    expect(page.url()).toContain("#/workspace");
    await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");

    // Now test browser Back / Forward preservation
    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');
    await page.goBack();
    await page.waitForTimeout(300);

    expect(page.url()).toContain("#/workspace");
    await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");
  });

  test("2. Imported report session preserves report findings, selection, and user notes across Help visits", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector("#btn-header-import-report");

    // Import report
    await page.locator("#input-import-report").setInputFiles(EXAMPLE_REPORT);
    await page.waitForSelector("#finding-item-f_amount", { timeout: 15000 });

    // Select finding and add note
    await page.locator("#finding-item-f_amount").click();
    await page.getByTestId("note-input").fill("Verification note for imported report roundtrip");
    await page.getByTestId("note-add").click();
    await expect(page.getByTestId("finding-notes")).toContainText(
      "Verification note for imported report roundtrip",
    );

    // Navigate to Help
    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');

    // Return via UI button
    await page.click("#btn-help-back-workspace");
    await page.waitForSelector("#finding-item-f_amount");

    // Verify finding selection and note are intact
    await expect(page.locator("#finding-item-f_amount")).toHaveAttribute("aria-current", "true");
    await expect(page.getByTestId("finding-notes")).toContainText(
      "Verification note for imported report roundtrip",
    );

    // Return via browser Back
    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');
    await page.goBack();
    await page.waitForTimeout(300);

    await expect(page.locator("#finding-item-f_amount")).toHaveAttribute("aria-current", "true");
    await expect(page.getByTestId("finding-notes")).toContainText(
      "Verification note for imported report roundtrip",
    );
  });

  test("3. Empty workspace intake state preserves intake surface across Help visits", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector("#btn-header-open-pdf");
    await page.waitForSelector('[data-testid="file-drop"]');

    // Navigate to Help
    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');

    // Return to workspace
    await page.click("#btn-help-back-workspace");
    await page.waitForSelector('[data-testid="file-drop"]');
    await expect(page.locator("#btn-header-open-pdf")).toBeVisible();
    await expect(page.locator("#btn-header-import-report")).toBeVisible();
  });

  test("4. Named gallery example (?example=scan) preserves scan report and finding selection across Help", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace?example=scan`);
    await page.waitForSelector('[id^="finding-item-"]', { timeout: 15000 });

    // Select first finding
    const firstFinding = page.locator('[id^="finding-item-"]').first();
    await firstFinding.click();
    await expect(firstFinding).toHaveAttribute("aria-current", "true");

    // Navigate to Help
    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');

    // Return via UI button
    await page.click("#btn-help-back-workspace");
    await page.waitForSelector('[id^="finding-item-"]');

    expect(page.url()).toContain("example=scan");
    await expect(firstFinding).toHaveAttribute("aria-current", "true");
  });

  test("5. Deep-linked Help (#/help) renders Open Workspace and separate Try Demo Example actions", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/help`);
    await page.waitForSelector('[data-testid="help-page"]');

    const wsBtn = page.locator("#btn-help-back-workspace");
    const exBtn = page.locator("#btn-help-open-example");

    // Since user deep-linked and has no active workspace, button says "Open Workspace"
    await expect(wsBtn).toHaveText("Open Workspace");
    await expect(exBtn).toHaveText("Try Demo Example");

    // Clicking "Try Demo Example" loads the demo example
    await exBtn.click();
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 10000 });
    expect(page.url()).toContain("example=true");
  });

  test("6. Keyboard focus enters Help cleanly and restores to triggering button upon return", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#btn-header-help");

    // Focus Help button and press Enter
    await page.locator("#btn-header-help").focus();
    await page.keyboard.press("Enter");
    await page.waitForSelector('[data-testid="help-page"]');

    // Focus is within HelpPage on the primary return button
    const focusedId = await page.evaluate(() => document.activeElement?.id);
    expect(focusedId).toBe("btn-help-back-workspace");

    // Press Enter to return to workspace
    await page.keyboard.press("Enter");
    await page.waitForSelector('[data-testid="viewer-stage"]');

    // Focus is restored to #btn-header-help
    await page.waitForFunction(
      () => document.activeElement?.id === "btn-header-help",
      { timeout: 3000 },
    );
    const restoredId = await page.evaluate(() => document.activeElement?.id);
    expect(restoredId).toBe("btn-header-help");
  });

  test("7. Workspace container is inert and hidden while Help is active, with zero focusable elements leaked", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#btn-header-help");

    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');

    // Inspect the preserved workspace container
    const container = page.locator("#workspace-container");
    await expect(container).toHaveAttribute("hidden");
    await expect(container).toHaveAttribute("inert");

    // Verify Tab cycles only through Help elements, never reaching inert workspace
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press("Tab");
      const activeElInWorkspace = await page.evaluate(() => {
        const ws = document.getElementById("workspace-container");
        return ws ? ws.contains(document.activeElement) : false;
      });
      expect(activeElInWorkspace).toBe(false);
    }
  });

  test("8. Guide cards provide accessible interactive modal dialogs with focus trap and Escape dismissal", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/help`);
    await page.waitForSelector('[data-testid="help-page"]');

    const guideButtons = [
      { id: "btn-guide-cli", title: "Command-Line Interface Guide" },
      { id: "btn-guide-a11y", title: "Accessibility & Assistive Flows Guide" },
      { id: "btn-guide-corpus", title: "Corpus & Test Invariants Guide" },
      { id: "btn-guide-readers", title: "Reader Integration Guide" },
      { id: "btn-guide-attribution", title: "Attribution & Licenses Guide" },
    ];

    for (const guide of guideButtons) {
      const btn = page.locator(`#${guide.id}`);
      await expect(btn).toBeVisible();

      // Click guide button
      await btn.click();
      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible();
      await expect(dialog).toHaveAttribute("aria-modal", "true");
      await expect(page.locator(`text=${guide.title}`).first()).toBeVisible();

      // Escape dismisses modal
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);

      // Focus restored to button
      await page.waitForFunction(
        (expectedId) => document.activeElement?.id === expectedId,
        guide.id,
        { timeout: 3000 },
      );
      const activeId = await page.evaluate(() => document.activeElement?.id);
      expect(activeId).toBe(guide.id);
    }
  });

  test("9. Help copy strictly avoids developer invariant IDs and unsupported exact percentage claims", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}/#/help`);
    await page.waitForSelector('[data-testid="help-page"]');

    const pageContent = await page.content();

    // Developer invariant IDs must NOT appear
    expect(pageContent).not.toContain("Invariant I06");
    expect(pageContent).not.toContain("Invariant I11");
    expect(pageContent).not.toContain("report.schema.json");

    // Unsupported exact percentage claims must NOT appear
    expect(pageContent).not.toContain("exact percentage of page text and geometry");

    // Honest product principles and platform scope must be present
    expect(pageContent).toContain("Non-Certification Principle");
    expect(pageContent).toContain("Explicit Omission Reporting");
    expect(pageContent).toContain("Provenance &amp; Audit Trail");
    expect(pageContent).toContain("Local-First Processing");
    expect(pageContent).toContain("Offline Readiness");
    expect(pageContent).toContain("Inspection Coverage &amp; Status");
    expect(pageContent).toContain("Platform Scope &amp; Availability");
    expect(pageContent).toContain("macOS native companion");
    expect(pageContent).toContain("Docker CLI workflow");
    expect(pageContent).toContain("Separate Windows and Linux desktop GUI applications remain deferred");
  });

  test("10. Escape key on Help page returns to active Workspace", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#btn-header-help");

    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]');
    expect(page.url()).toContain("#/help");

    // Press Escape
    await page.keyboard.press("Escape");
    await page.waitForSelector('[data-testid="viewer-stage"]');
    expect(page.url()).toContain("#/workspace");
  });
});
