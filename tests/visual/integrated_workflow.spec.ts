/**
 * The integrated browser workflow, start to finish, as one journey.
 *
 * Own file -> inspect -> select a finding -> add a note -> Help -> return ->
 * failure -> recovery. Each step asserts terminal, user-visible evidence rather
 * than an intermediate flag, so a step that silently does nothing fails here.
 */
import path from "node:path";
import { test, expect } from "@playwright/test";
import { startProdServer, type ProdServerInstance, ROOT } from "./prod_server.ts";

let prodServer: ProdServerInstance;
let baseUrl: string;

const FIXTURES = path.join(ROOT, "fixtures");
const OWN_FILE = path.join(FIXTURES, "public", "mapping-amount.pdf");
const ENCRYPTED = path.join(FIXTURES, "development", "bad-pdf-encrypted.pdf");
const NOTE = "note-added-during-the-integrated-journey";

test.beforeAll(async () => {
  prodServer = await startProdServer();
  baseUrl = prodServer.baseUrl;
});

test.afterAll(async () => {
  await prodServer?.close();
});

test("own file -> inspect -> note -> Help -> return -> failure -> recovery", async ({ page }) => {
  // 1. own file
  await page.goto(`${baseUrl}/#/workspace`);
  await page.waitForSelector('[data-testid="file-drop"]');
  await page.locator("#input-open-pdf").setInputFiles(OWN_FILE);
  await expect(page.getByText("not yet inspected").first()).toBeVisible({ timeout: 15000 });

  // 2. inspect
  await page.locator('[data-testid="start-run"]').click();
  await expect(page.locator('[data-testid="viewer-stage"]')).toBeVisible({ timeout: 40000 });

  // 3. select a finding and add a note
  const finding = page.locator('[id^="finding-item-"]').first();
  await finding.waitFor({ state: "visible", timeout: 20000 });
  await finding.click();
  await page.getByTestId("note-input").fill(NOTE);
  await page.getByTestId("note-add").click();
  await expect(page.getByTestId("finding-notes")).toContainText(NOTE);

  // 4. Help and back, via the UI control
  await page.click("#btn-header-help");
  await expect(page.locator('[data-testid="help-page"]')).toBeVisible({ timeout: 15000 });
  await page.click("#btn-help-back-workspace");
  await expect(page.locator('[data-testid="viewer-stage"]')).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId("finding-notes")).toContainText(NOTE);

  // 5. failure: replacing the open document asks first, and only then is the
  //    unusable input processed and refused. Both steps are part of the journey.
  await page.locator("#input-open-pdf").setInputFiles(ENCRYPTED);
  await expect(page.getByText(/open a different pdf/i).first()).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: /clear|replace|continue/i }).first().click();

  await expect(
    page.getByText(/encrypted|password|not supported|could not be (opened|read)/i).first(),
  ).toBeVisible({ timeout: 15000 });

  // 6. recovery: the workspace is still usable after the refusal
  await expect(page.locator("#input-open-pdf")).toBeEnabled();
  await page.locator("#input-open-pdf").setInputFiles(OWN_FILE);
  await expect(page.getByText("not yet inspected").first()).toBeVisible({ timeout: 15000 });
});
