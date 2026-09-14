/**
 * Real error, rejection and recovery cases the existing journey suite does not cover.
 *
 * The existing journey suite covers a corrupt PDF, malformed report JSON and a cancelled replace.
 * This file adds the two the goal names that were untested: an encrypted input
 * (rejected, prior session preserved, next valid file still works) and the
 * wrong-source disclosure on an imported report.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { startProdServer, type ProdServerInstance, ROOT } from "./prod_server.ts";

let prodServer: ProdServerInstance;
let baseUrl: string;

const FIXTURES = path.join(ROOT, "fixtures");
const ENCRYPTED = path.join(FIXTURES, "development", "bad-pdf-encrypted.pdf");
const VALID = path.join(FIXTURES, "public", "mapping-amount.pdf");
const EXAMPLE_REPORT = path.join(ROOT, "apps/web/public/examples/duplicates/report.json");
const OTHER = path.join(FIXTURES, "public", "covered-amount.pdf");
const NOTE_FOR_TRIPS = "note-survives-repeated-help-trips";

test.beforeAll(async () => {
  prodServer = await startProdServer();
  baseUrl = prodServer.baseUrl;
});

test.afterAll(async () => {
  await prodServer?.close();
});

test.describe("Workspace: encrypted input and recovery", () => {
  test("an encrypted PDF is refused and the next valid file still loads", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    await page.locator("#input-open-pdf").setInputFiles(ENCRYPTED);

    // The refusal must be surfaced, not silently ignored and not a crash.
    await expect(
      page.getByText(/encrypted|password|not supported|could not be (opened|read)/i).first(),
    ).toBeVisible({ timeout: 15000 });

    // Recovery: a valid file after the refusal must produce a usable session.
    // Loading and inspecting are two steps — the file lands in the intake as
    // "not yet inspected" and the explicit start control begins the run.
    await page.locator("#input-open-pdf").setInputFiles(VALID);
    await expect(page.getByText("not yet inspected").first()).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="start-run"]').click();
    await expect(page.locator('[data-testid="viewer-stage"]')).toBeVisible({ timeout: 40000 });

    // The recovery claim is "the next valid job succeeds and the controls are usable",
    // not "the amount renders as one contiguous string": the native reader is
    // character-granular for this fixture (see test_fixture_facts_through_cli.py), so
    // asserting "$100" would over-claim about reader granularity rather than recovery.
    await expect(page.locator("#input-open-pdf")).toBeEnabled();
    await expect(page.locator("#btn-rerun")).toBeVisible({ timeout: 20000 });
  });

  test("a refused encrypted input does not replace an existing usable session", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace?example=duplicates`);
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 15000 });
    const before = await page.locator('[data-testid="viewer-stage"]').innerText();

    await page.locator("#input-open-pdf").setInputFiles(ENCRYPTED);
    await page.waitForTimeout(1500);

    // The prior session must still be the one on screen.
    await expect(page.locator('[data-testid="viewer-stage"]')).toBeVisible();
    expect(await page.locator('[data-testid="viewer-stage"]').innerText()).toBe(before);
  });
});

test.describe("Workspace: imported report source disclosure", () => {
  test("an imported report without its source is disclosed, not presented as complete", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    await page.locator("#btn-header-import-report").click();
    await page.locator("#input-import-report").setInputFiles(EXAMPLE_REPORT);

    // The session renders the imported evidence.
    await expect(page.locator('[data-testid="viewer-stage"]')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("No matching reading found here").first()).toBeVisible({ timeout: 15000 });

    // The export surface must disclose that the original is absent rather than
    // implying the report is fully self-contained.
    await expect(
      page.getByText(/Original PDF not included|replay requires the matching original/i).first(),
    ).toBeVisible({ timeout: 15000 });

    // And it must not assert a correctness or safety verdict.
    const body = await page.locator("body").innerText();
    expect(body.toLowerCase()).not.toContain("all checked");
    expect(body.toLowerCase()).not.toContain("document is safe");
  });
});

test.describe("Workspace: oversized input, cancellation, and replacement disclosure", () => {
  function oversizedFixture(): string {
    const target = path.join(tmpdir(), "oversized-input.pdf");
    // One byte over the documented 20 MiB local browser limit.
    writeFileSync(target, Buffer.concat([Buffer.from("%PDF-1.4\n"), Buffer.alloc(21 * 1024 * 1024, 0x41)]));
    return target;
  }

  test("an oversized file is refused with the limit and the actual size", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    await page.locator("#input-open-pdf").setInputFiles(oversizedFixture());

    const refusal = page.getByText(/exceeds the 20 MiB local browser limit/i).first();
    await expect(refusal).toBeVisible({ timeout: 15000 });
    const text = await refusal.textContent();
    expect(text, "the refusal must state the measured size, not just the limit").toMatch(/\d{7,}\s*>\s*20971520/);

    // Recovery: the intake still works for an acceptable file.
    await page.locator("#input-open-pdf").setInputFiles(VALID);
    await expect(page.getByText("not yet inspected").first()).toBeVisible({ timeout: 15000 });
  });

  test("a run can be cancelled and reports a terminal cancelled state", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');
    await page.locator("#input-open-pdf").setInputFiles(VALID);
    await expect(page.getByText("not yet inspected").first()).toBeVisible({ timeout: 15000 });

    await expect(page.locator("#btn-cancel-run")).toHaveCount(0, { timeout: 5000 });
    await page.locator('[data-testid="start-run"]').click();
    await expect(page.locator("#btn-cancel-run")).toHaveCount(1, { timeout: 15000 });

    await page.locator("#btn-cancel-run").click();
    await expect(page.getByText(/inspection run was cancelled/i).first()).toBeVisible({ timeout: 15000 });
  });

  test("selecting a different file discloses the unsaved report before replacing", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');
    await page.locator("#input-open-pdf").setInputFiles(VALID);
    await expect(page.getByText("not yet inspected").first()).toBeVisible({ timeout: 15000 });

    await page.locator("#input-open-pdf").setInputFiles(OTHER);

    await expect(page.getByText(/open a different pdf/i).first()).toBeVisible({ timeout: 15000 });
    await expect(
      page.getByText(/clears the current file and its unsaved report/i).first(),
    ).toBeVisible({ timeout: 15000 });
  });
});

test.describe("Workspace: notes stay with their document", () => {
  const NOTE = "note-bound-to-this-document";

  async function addNote(page: import("@playwright/test").Page) {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector("#btn-header-import-report");
    await page.locator("#input-import-report").setInputFiles(EXAMPLE_REPORT);
    // Finding ids are content-derived (f_<hash>), so wait for the first card
    // rather than hardcoding an id that belongs to one particular fixture.
    const finding = page.locator('[id^="finding-item-"]').first();
    await finding.waitFor({ state: "visible", timeout: 20000 });
    await finding.click();
    await page.getByTestId("note-input").fill(NOTE);
    await page.getByTestId("note-add").click();
    await expect(page.getByTestId("finding-notes")).toContainText(NOTE);
  }

  test("typing a viewer shortcut inside the note field does not change the viewer mode", async ({ page }) => {
    await addNote(page);
    const before = await page.locator("#tab-mode-page").getAttribute("aria-selected");
    await page.getByTestId("note-input").press("3");
    await page.waitForTimeout(300);
    expect(await page.locator("#tab-mode-page").getAttribute("aria-selected")).toBe(before);
  });

  test("a note does not migrate to a different document", async ({ page }) => {
    await addNote(page);

    await page.locator("#input-open-pdf").setInputFiles(OTHER);
    await expect(page.getByText(/open a different pdf/i).first()).toBeVisible({ timeout: 15000 });
    const replace = page.getByRole("button", { name: /clear|replace|continue/i }).first();
    await replace.click();
    await expect(page.getByText("not yet inspected").first()).toBeVisible({ timeout: 15000 });

    const body = await page.locator("body").innerText();
    expect(body, "the previous document's note must not appear in the new session").not.toContain(NOTE);
    await expect(page.getByTestId("finding-notes")).toHaveCount(0);
  });
});

test.describe("Workspace: repeated navigation and modal nesting", () => {
  test("a finding selection and its note survive repeated Help trips", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector("#btn-header-import-report");
    await page.locator("#input-import-report").setInputFiles(EXAMPLE_REPORT);
    const finding = page.locator('[id^="finding-item-"]').first();
    await finding.waitFor({ state: "visible", timeout: 20000 });
    await finding.click();
    await page.getByTestId("note-input").fill(NOTE_FOR_TRIPS);
    await page.getByTestId("note-add").click();
    await expect(page.getByTestId("finding-notes")).toContainText(NOTE_FOR_TRIPS);

    for (let trip = 1; trip <= 3; trip += 1) {
      await page.click("#btn-header-help");
      await expect(page.locator('[data-testid="help-page"]')).toBeVisible({ timeout: 15000 });
      await page.click("#btn-help-back-workspace");
      await expect(page.getByTestId("finding-notes")).toContainText(NOTE_FOR_TRIPS, { timeout: 15000 });
      await expect(finding).toHaveAttribute("aria-current", "true");
    }
  });

  test("each guide dialog traps focus and Escape closes only the open one", async ({ page }) => {
    await page.goto(`${baseUrl}/#/help`);
    await page.waitForSelector('[data-testid="help-page"]');

    const dialog = page.locator('[role="dialog"]');
    for (const trigger of ["#btn-guide-cli", "#btn-guide-keyboard"]) {
      const control = page.locator(trigger);
      if ((await control.count()) === 0) continue;
      await control.focus();
      await page.keyboard.press("Enter");
      await expect(dialog).toHaveCount(1, { timeout: 15000 });

      // Focus must be inside the dialog while it is open.
      // Poll rather than sample once: the dialog is present in the DOM a tick
      // before focus lands inside it, and sampling once made this assertion racy.
      // Every dialog element is checked, not just the first - the app may keep
      // more than one, and only the open one is expected to hold focus.
      await expect
        .poll(
          () =>
            page.evaluate(() => {
              const active = document.activeElement as HTMLElement | null;
              return Array.from(document.querySelectorAll('[role="dialog"]')).some((dialog) =>
                dialog.contains(active),
              );
            }),
          { message: "focus must move into the dialog when it opens", timeout: 10000 },
        )
        .toBe(true);

      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0, { timeout: 15000 });
      const restored = await page.evaluate(() => (document.activeElement as HTMLElement | null)?.id ?? "");
      expect(restored, "focus must return to the control that opened the dialog").toBe(trigger.slice(1));
    }
  });
});
