/**
 * Example lifecycle: delayed gallery import must not beat newer user intent,
 * and public demo entry points load one captured gallery report.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { expect, test, type Page, type Route } from "@playwright/test";

const ROOT = path.resolve(process.cwd());
const WEB = path.join(ROOT, "apps", "web");
const AMOUNT_REPORT = path.join(ROOT, "apps/web/public/examples/amount/report.json");
const DUPLICATES_REPORT = path.join(ROOT, "apps/web/public/examples/duplicates/report.json");
const CONTROL_PDF = path.join(ROOT, "apps/web/public/examples/amount/mapping-control.pdf");
const AMOUNT_SHA = "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80";
const DUPLICATES_SHA = "036db55ee2f8c320252c7c9fb220daa38699387800e8a3bbf8c6bb73463feb1f";

let baseUrl: string;
let viteServer: { close: () => Promise<void> } | null = null;

test.beforeAll(async () => {
  const viteModulePath = path.resolve(WEB, "node_modules/vite/dist/node/index.js");
  const { createServer } = (await import(pathToFileURL(viteModulePath).href)) as {
    createServer: (o: object) => Promise<{
      listen: () => Promise<void>;
      resolvedUrls: { local: string[] };
      close: () => Promise<void>;
    }>;
  };
  viteServer = await createServer({
    root: WEB,
    server: { port: 0, strictPort: false, host: "127.0.0.1", fs: { allow: [ROOT] } },
    logLevel: "silent",
  });
  await viteServer.listen();
  baseUrl = viteServer.resolvedUrls.local[0].replace(/\/$/, "");
});

test.afterAll(async () => {
  await viteServer?.close();
});

type InspectSnap = {
  sha: string | null;
  generation: number | null;
  reportSource: string | null;
  hasSourceBytes: boolean;
  fileState: string | null;
  error: string | null;
};

async function inspect(page: Page): Promise<InspectSnap> {
  return page.evaluate(() => {
    const snap = (
      globalThis as {
        __inspect?: {
          getState(): {
            report?: { document?: { sha256?: string } } | null;
            generation?: number;
            reportSource?: string | null;
            hasSourceBytes?: boolean;
            fileState?: string;
            error?: { message?: string } | null;
          };
        };
      }
    ).__inspect?.getState();
    return {
      sha: snap?.report?.document?.sha256 ?? null,
      generation: snap?.generation ?? null,
      reportSource: snap?.reportSource ?? null,
      hasSourceBytes: snap?.hasSourceBytes === true,
      fileState: snap?.fileState ?? null,
      error: snap?.error?.message ?? null,
    };
  });
}

async function waitForSha(page: Page, sha: string, timeout = 15_000): Promise<void> {
  await page.waitForFunction(
    (expected) =>
      (
        globalThis as {
          __inspect?: { getState(): { report?: { document?: { sha256?: string } } | null } };
        }
      ).__inspect?.getState().report?.document?.sha256 === expected,
    sha,
    { timeout },
  );
}

async function holdAmountReport(
  page: Page,
  body: string,
  status = 200,
): Promise<{ release: () => void; requested: Promise<void> }> {
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let fetched!: () => void;
  const requested = new Promise<void>((resolve) => {
    fetched = resolve;
  });
  await page.route("**/examples/amount/report.json", async (route: Route) => {
    fetched();
    await held;
    await route.fulfill({
      status,
      contentType: "application/json",
      body: status === 200 ? body : "unavailable",
    });
  });
  return { release: () => release(), requested };
}

test("delayed named example does not overwrite a newer imported report", async ({ page }) => {
  const amountJson = readFileSync(AMOUNT_REPORT, "utf8");
  const held = await holdAmountReport(page, amountJson);
  await page.goto(`${baseUrl}/#/workspace?example=amount`);
  await held.requested;
  await page.locator("#input-import-report").setInputFiles(DUPLICATES_REPORT);
  await waitForSha(page, DUPLICATES_SHA);
  const before = await inspect(page);
  expect(before.sha).toBe(DUPLICATES_SHA);

  held.release();
  await page.waitForTimeout(800);
  const after = await inspect(page);
  expect(after.sha, "user import must keep ownership after the delayed example resolves").toBe(
    DUPLICATES_SHA,
  );
  expect(after.sha).not.toBe(AMOUNT_SHA);
  expect(after.hasSourceBytes).toBe(false);
  await expect(page.getByTestId("example-error")).toHaveCount(0);
});

test("pending example does not repopulate a closed workspace", async ({ page }) => {
  const amountJson = readFileSync(AMOUNT_REPORT, "utf8");
  const held = await holdAmountReport(page, amountJson);
  await page.goto(`${baseUrl}/#/workspace?example=amount`);
  await held.requested;
  await page.locator("#input-import-report").setInputFiles(DUPLICATES_REPORT);
  await waitForSha(page, DUPLICATES_SHA);
  await page.locator("#btn-close-doc").click();
  await expect(page.locator("#btn-load-demo")).toBeVisible();
  held.release();
  await page.waitForTimeout(800);
  const after = await inspect(page);
  expect(after.sha).toBeNull();
  await expect(page.getByTestId("example-error")).toHaveCount(0);
  await expect(page.locator("#btn-load-demo")).toBeVisible();
});

test("pending example does not overwrite a newer PDF", async ({ page }) => {
  const amountJson = readFileSync(AMOUNT_REPORT, "utf8");
  const held = await holdAmountReport(page, amountJson);
  await page.goto(`${baseUrl}/#/workspace?example=amount`);
  await held.requested;
  await page.locator("#input-open-pdf").setInputFiles(CONTROL_PDF);
  await page.waitForFunction(
    () =>
      (
        globalThis as { __inspect?: { getState(): { doc?: { label?: string } | null } } }
      ).__inspect?.getState().doc !== null,
    { timeout: 15_000 },
  );
  const before = await inspect(page);
  expect(before.sha).toBeNull();
  held.release();
  await page.waitForTimeout(800);
  const after = await inspect(page);
  expect(after.sha).toBeNull();
  expect(after.reportSource).toBeNull();
  const label = await page.evaluate(
    () =>
      (
        globalThis as { __inspect?: { getState(): { doc?: { label?: string | null } | null } } }
      ).__inspect?.getState().doc?.label ?? null,
  );
  expect(label).toContain("mapping-control.pdf");
});

test("pending example does not replace a newer named example", async ({ page }) => {
  const amountJson = readFileSync(AMOUNT_REPORT, "utf8");
  const held = await holdAmountReport(page, amountJson);
  await page.goto(`${baseUrl}/#/workspace?example=amount`);
  await held.requested;
  await page.goto(`${baseUrl}/#/workspace?example=duplicates`);
  await waitForSha(page, DUPLICATES_SHA);
  held.release();
  await page.waitForTimeout(800);
  expect((await inspect(page)).sha).toBe(DUPLICATES_SHA);
});

test("pending example does not publish a stale error after a newer import", async ({ page }) => {
  const held = await holdAmountReport(page, "", 500);
  await page.goto(`${baseUrl}/#/workspace?example=amount`);
  await held.requested;
  await page.locator("#input-import-report").setInputFiles(DUPLICATES_REPORT);
  await waitForSha(page, DUPLICATES_SHA);
  held.release();
  await page.waitForTimeout(800);
  expect((await inspect(page)).sha).toBe(DUPLICATES_SHA);
  await expect(page.getByTestId("example-error")).toHaveCount(0);
});

test("rejected local import keeps the live captured example", async ({ page }) => {
  await page.goto(`${baseUrl}/#/workspace?example=amount`);
  await waitForSha(page, AMOUNT_SHA);
  await page.locator("#input-import-report").setInputFiles({
    name: "malformed.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify({ kind: "nope" })),
  });
  await page.getByRole("button", { name: "Clear and open file" }).click();
  await expect(page.locator("#import-error")).toBeVisible();
  expect((await inspect(page)).sha).toBe(AMOUNT_SHA);
  await expect(page.getByRole("heading", { name: "Save report" })).toBeVisible();
});

test("replace confirmation cancel keeps the live example", async ({ page }) => {
  await page.goto(`${baseUrl}/#/workspace?example=amount`);
  await waitForSha(page, AMOUNT_SHA);
  await page.locator("#input-import-report").setInputFiles(DUPLICATES_REPORT);
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await page.getByRole("button", { name: "Keep this file" }).click();
  await expect(dialog).toHaveCount(0);
  expect((await inspect(page)).sha).toBe(AMOUNT_SHA);
});

test("Help return preserves the captured example and finding selection", async ({ page }) => {
  await page.goto(`${baseUrl}/#/workspace?example=amount`);
  await waitForSha(page, AMOUNT_SHA);
  const finding = page.locator("[id^=finding-item-]").first();
  await finding.click();
  await expect(finding).toHaveAttribute("aria-current", "true");
  await page.locator("#btn-header-help").click();
  await expect(page.getByTestId("help-page")).toBeVisible();
  await page.locator("#btn-help-back-workspace").click();
  await waitForSha(page, AMOUNT_SHA);
  await expect(finding).toHaveAttribute("aria-current", "true");
});

test("example=true maps to the amount captured report with coverage, export, and privacy defaults", async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.goto(`${baseUrl}/#/workspace?example=true`);
  await waitForSha(page, AMOUNT_SHA);
  await expect(page.locator("#workspace-doc-title")).toContainText("mapping-amount.pdf");
  await expect(page.getByRole("heading", { name: "What was checked" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Save report" })).toBeVisible();
  await expect(page.getByTestId("run-progress")).toHaveCount(0);
  const live = await inspect(page);
  expect(live.reportSource).toBe("import");
  expect(live.hasSourceBytes).toBe(true);
  await expect(page.locator("#btn-attach-source")).toHaveCount(0);
  await expect(page.getByTestId("replay-status")).toContainText(
    "The original PDF is available with this report",
  );

  const finding = page.locator("[id^=finding-item-]").first();
  await finding.click();
  await expect(finding).toHaveAttribute("aria-current", "true");

  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save JSON (reopens in Inkflip)" }).click();
  const download = await pending;
  const file = await download.path();
  expect(file).toBeTruthy();
  const payload = JSON.parse(readFileSync(file as string, "utf8"));
  expect(payload.document.sha256).toBe(AMOUNT_SHA);
  expect(payload.document.source_asset_id ?? null).toBeNull();
  const sourceAssets = (payload.assets ?? []).filter((a: { purpose?: string }) => a.purpose === "source_pdf");
  expect(sourceAssets).toHaveLength(0);
  expect(JSON.stringify(payload.export.omissions)).toContain("Original PDF excluded");

  await page.locator("#btn-close-doc").click();
  await page.locator("#input-import-report").setInputFiles({
    name: "roundtrip.inkflip.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(payload)),
  });
  await waitForSha(page, AMOUNT_SHA);
  const reimported = await inspect(page);
  expect(reimported.sha).toBe(AMOUNT_SHA);
  expect(reimported.hasSourceBytes).toBe(false);
});

test("Home Check a PDF keeps you on Home until a file is chosen", async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.goto(`${baseUrl}/#/`);
  await expect(page.locator("#hero-headline")).toBeVisible();

  const firstChooser = page.waitForEvent("filechooser");
  await page.locator("#btn-open-locally").click();
  await firstChooser;
  expect(page.url()).not.toMatch(/workspace/);
  await page.keyboard.press("Escape");
  await expect(page.locator("#hero-headline")).toBeVisible();
  expect(page.url()).not.toMatch(/workspace/);

  const secondChooser = page.waitForEvent("filechooser");
  await page.locator("#btn-open-locally").click();
  const chooser = await secondChooser;
  await chooser.setFiles(CONTROL_PDF);
  await expect(page).toHaveURL(/#\/workspace/);
  await expect(page.getByTestId("doc-label")).toHaveText("mapping-control.pdf", {
    timeout: 30_000,
  });
});

test("Home Try the example and empty-workspace Load Example reach the captured amount report", async ({
  page,
}) => {
  await page.goto(`${baseUrl}/#/`);
  await expect(page.getByTestId("examples-gallery")).toBeVisible();
  await expect(page.getByTestId("examples-gallery").getByRole("heading", { name: "Try an example" })).toBeVisible();
  await page.getByTestId("example-card-amount").click();
  await expect(page.getByTestId("example-detail-amount")).toBeVisible();
  await page.locator("#btn-try-example").click();
  await waitForSha(page, AMOUNT_SHA);
  expect(page.url()).toContain("example=true");
  await expect(page.getByRole("heading", { name: "Save report" })).toBeVisible();

  await page.locator("#btn-close-doc").click();
  await page.locator("#btn-load-demo").click();
  await waitForSha(page, AMOUNT_SHA);
  await expect(page.getByRole("heading", { name: "What was checked" })).toBeVisible();
});
