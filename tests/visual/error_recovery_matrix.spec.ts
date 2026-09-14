/**
 * Section G — real error, rejection and recovery cases AGY's suite does not cover.
 *
 * AGY covers a corrupt PDF, malformed report JSON and a cancelled replace.
 * This file adds the two the goal names that were untested: an encrypted input
 * (rejected, prior session preserved, next valid file still works) and the
 * wrong-source disclosure on an imported report.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { startProdServer, type ProdServerInstance, ROOT } from "./prod_server.ts";

let prodServer: ProdServerInstance;
let baseUrl: string;

const FIXTURES = path.join(ROOT, "fixtures");
const ENCRYPTED = path.join(FIXTURES, "development", "bad-pdf-encrypted.pdf");
const VALID = path.join(FIXTURES, "public", "mapping-amount.pdf");
const EXAMPLE_REPORT = path.join(ROOT, "apps/web/public/examples/duplicates/report.json");

test.beforeAll(async () => {
  prodServer = await startProdServer();
  baseUrl = prodServer.baseUrl;
});

test.afterAll(async () => {
  await prodServer?.close();
});

test.describe("Section G: encrypted input and recovery", () => {
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

test.describe("Section G: imported report source disclosure", () => {
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
