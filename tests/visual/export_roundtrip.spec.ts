/**
 * Export → reimport integrity: real production-app downloads, empty-workspace
 * imports, source opt-in, and identity mutations.
 *
 * Starts from AutoClaw's 5f21dc7 capture suite, then proves report-specific
 * identity from an empty workspace and refuses tampered payloads without
 * wiping a different valid session. Test instrumentation is labeled.
 */
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { test, expect, type Page } from "@playwright/test";
import { startProdServer, type ProdServerInstance } from "./prod_server.ts";

let prodServer: ProdServerInstance;
let baseUrl: string;

const ROOT = path.resolve(import.meta.dirname, "../..");
const CARD = "duplicates";
const SOURCE_PDF = readFileSync(
  path.join(ROOT, "apps/web/public/examples/duplicates/duplicates-four.pdf"),
);
const CONTROL_PDF = readFileSync(
  path.join(ROOT, "apps/web/public/examples/duplicates/duplicates-control.pdf"),
);

function cardManifest() {
  return JSON.parse(
    readFileSync(path.join(ROOT, "apps/web/public/examples", CARD, "manifest.json"), "utf8"),
  );
}

function sha256(buf: Buffer | Uint8Array): string {
  return createHash("sha256").update(buf).digest("hex");
}

async function downloadNamed(page: Page, button: string): Promise<{ name: string; body: Buffer }> {
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: button }).click();
  const download = await pending;
  const file = await download.path();
  expect(file, "the download must produce a real file").toBeTruthy();
  return { name: download.suggestedFilename(), body: readFileSync(file as string) };
}

async function downloadJson(page: Page, button = "Download portable JSON"): Promise<Record<string, any>> {
  const { body } = await downloadNamed(page, button);
  return JSON.parse(body.toString("utf8"));
}

async function waitForImportedReport(page: Page) {
  await expect(page.locator('[data-testid="viewer-stage"]')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: "Download portable JSON" })).toBeEnabled({
    timeout: 20_000,
  });
}

async function importReportBytes(page: Page, name: string, json: string | Buffer) {
  await page.locator("#input-import-report").setInputFiles({
    name,
    mimeType: "application/json",
    buffer: typeof json === "string" ? Buffer.from(json, "utf8") : json,
  });
}

async function gotoEmptyWorkspace(page: Page) {
  await page.goto(`${baseUrl}/#/workspace`);
  await page.waitForSelector("#btn-import-report, #btn-header-import-report", { timeout: 15_000 });
}

test.beforeAll(async () => {
  process.env.INKFLIP_TEST_HOOKS = "1";
  prodServer = await startProdServer();
  baseUrl = prodServer.baseUrl;
});

test.afterAll(async () => {
  await prodServer?.close();
});

test.describe("Export payload, source opt-in, and reimport", () => {
  test("default selected export omits the source and discloses it", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace?example=${CARD}`);
    await waitForImportedReport(page);

    const manifest = cardManifest();
    const payload = await downloadJson(page);

    expect(payload.kind).toBe("report");
    expect(payload.export.scope).toBe("selection");
    expect(Array.isArray(payload.export.included)).toBe(true);
    expect(Array.isArray(payload.export.omissions)).toBe(true);
    expect(payload.document.sha256).toBe(manifest.files.source.sha256);
    expect(payload.document.byte_length).toBe(manifest.files.source.byte_length);
    expect(payload.document.source_asset_id ?? null).toBeNull();
    const sourceAssets = (payload.assets ?? []).filter((a: { purpose?: string }) => a.purpose === "source_pdf");
    expect(sourceAssets).toHaveLength(0);
    expect(JSON.stringify(payload.export.omissions)).toContain("Original PDF excluded");
  });

  test("gallery source opt-in embeds bytes that match the document digest", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace?example=${CARD}`);
    await waitForImportedReport(page);
    await expect(page.getByText("This includes every page and any hidden content in the original file.")).toBeVisible();

    await page.waitForFunction(
      () =>
        (
          globalThis as { __inspect?: { getState(): { hasSourceBytes: boolean } } }
        ).__inspect?.getState().hasSourceBytes === true,
      { timeout: 15_000 },
    );

    await page.getByLabel("Include the original PDF").check();
    await expect(page.getByText("Requested original bytes unavailable — evidence only.")).toHaveCount(0);

    const manifest = cardManifest();
    const payload = await downloadJson(page);
    const sourceAssets = (payload.assets ?? []).filter((a: { purpose?: string }) => a.purpose === "source_pdf");
    expect(sourceAssets).toHaveLength(1);
    const asset = sourceAssets[0];
    expect(asset.sha256).toBe(payload.document.sha256);
    expect(asset.byte_length).toBe(manifest.files.source.byte_length);
    const decoded = Buffer.from(asset.data_base64, "base64");
    expect(decoded.length).toBe(manifest.files.source.byte_length);
    expect(sha256(decoded)).toBe(manifest.files.source.sha256);
    expect(decoded.subarray(0, 5).toString("latin1")).toBe("%PDF-");
    expect(payload.export.included).toContain("source_pdf");
    expect(payload.document.source_asset_id).toBe(asset.id);
  });

  test("unavailable source stays evidence-only and discloses before download", async ({ page }) => {
    await gotoEmptyWorkspace(page);
    const exported = JSON.parse(
      readFileSync(path.join(ROOT, "apps/web/public/examples", CARD, "report.json"), "utf8"),
    );
    await importReportBytes(page, "evidence-only.json", JSON.stringify(exported));
    await waitForImportedReport(page);

    await page.getByLabel("Include the original PDF").check();
    await expect(
      page.getByText("Original bytes unavailable — this export is evidence-only."),
    ).toBeVisible();
    const payload = await downloadJson(page);
    expect(payload.assets ?? []).toHaveLength(0);
    expect(payload.document.source_asset_id ?? null).toBeNull();
    expect(JSON.stringify(payload.export.omissions)).toContain(
      "Requested original bytes unavailable — evidence only.",
    );
  });

  test("reimport from an empty workspace restores report-specific identity", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace?example=${CARD}`);
    await waitForImportedReport(page);
    const payload = await downloadJson(page);
    expect((payload.findings ?? []).length).toBeGreaterThan(0);
    const reportId = payload.report_id;
    const findingTitle = payload.findings[0].title;

    await gotoEmptyWorkspace(page);
    await expect(page.getByText(findingTitle)).toHaveCount(0);

    await importReportBytes(page, "roundtrip.json", JSON.stringify(payload));
    await waitForImportedReport(page);
    await expect(page.getByText(findingTitle).first()).toBeVisible({ timeout: 15_000 });
    const live = await page.evaluate(() => {
      const inspect = (globalThis as { __inspect?: { getState(): { report: Record<string, any> | null } } })
        .__inspect;
      const report = inspect?.getState().report;
      return {
        reportId: report?.report_id ?? null,
        documentSha: report?.document?.sha256 ?? null,
        findingIds: (report?.findings ?? []).map((f: { id: string }) => f.id),
      };
    });
    expect(live.reportId, "imported session must keep the payload's report identity").toBe(reportId);
    expect(live.documentSha).toBe(payload.document.sha256);
    expect(live.findingIds).toEqual(payload.findings.map((f: { id: string }) => f.id));

    const reimported = await downloadJson(page);
    // A new selected export reseals with a fresh report_id; origin stays bound.
    expect(reimported.export.origin_report_id).toBe(reportId);
    expect(reimported.document.sha256).toBe(payload.document.sha256);
    expect(reimported.findings.map((f: { id: string }) => f.id)).toEqual(
      payload.findings.map((f: { id: string }) => f.id),
    );
  });

  test("HTML download is script-free and carries CSP", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace?example=${CARD}`);
    await waitForImportedReport(page);
    const { body } = await downloadNamed(page, "Download readable HTML");
    const html = body.toString("utf8");
    expect(html.toLowerCase()).toContain("<!doctype html>");
    expect(html).toContain("Content-Security-Policy");
    const decodedHtml = html.replace(/&#x27;/g, "'").replace(/&#39;/g, "'");
    expect(decodedHtml).toMatch(/script-src 'none'/);
    expect(html.toLowerCase()).not.toContain("<script");
    expect(html).not.toContain("data:application/pdf");
    expect(html).not.toContain("%PDF-");
  });

  test("notes and finding selection round-trip; hostile text stays inert", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace?example=${CARD}`);
    await waitForImportedReport(page);

    const noteInput = page.locator('[data-testid="note-input"]').first();
    if (await noteInput.count()) {
      await noteInput.fill('<img src="https://evil.invalid/x.png" onerror="window.__pwned=1">');
      await page.locator('[data-testid="note-add"]').first().click();
      await page.getByLabel("Include my notes").check();
    }

    const findingBoxes = page.locator('[data-testid="export-findings"] input[type="checkbox"]');
    const findingCount = await findingBoxes.count();
    if (findingCount > 1) {
      await findingBoxes.nth(1).uncheck();
    }

    const payload = await downloadJson(page);
    if (findingCount > 1) {
      expect(payload.findings.length).toBeLessThan(findingCount);
    }
    if (await noteInput.count()) {
      expect(payload.export.included).toContain("annotations");
      const noteText = JSON.stringify(payload.annotations ?? []);
      expect(noteText).toContain("evil.invalid");
    }

    const { body: htmlBody } = await downloadNamed(page, "Download readable HTML");
    const html = htmlBody.toString("utf8");
    expect(html.toLowerCase()).not.toContain("<script");
    expect(html).not.toContain('src="https://evil.invalid');
    const pwned = await page.evaluate(() => (globalThis as { __pwned?: unknown }).__pwned);
    expect(pwned).toBeUndefined();
  });
});

test.describe("Tampered import refusal preserves a valid session", () => {
  async function loadValidExport(page: Page): Promise<Record<string, any>> {
    await page.goto(`${baseUrl}/#/workspace?example=${CARD}`);
    await waitForImportedReport(page);
    // Opt in to source inclusion so the payload carries the verified
    // source_pdf asset — without it `assets` is empty and an asset-identity
    // mutation degenerates into re-importing the untouched valid payload.
    await page.waitForFunction(
      () =>
        (
          globalThis as { __inspect?: { getState(): { hasSourceBytes: boolean } } }
        ).__inspect?.getState().hasSourceBytes === true,
      { timeout: 15_000 },
    );
    await page.getByLabel("Include the original PDF").check();
    return downloadJson(page);
  }

  test("a tampered export is refused on an empty workspace", async ({ page }) => {
    const payload = await loadValidExport(page);
    payload.report_id = "0".repeat(64);
    await gotoEmptyWorkspace(page);
    await importReportBytes(page, "tampered.json", JSON.stringify(payload));
    await expect(page.locator("#import-error")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(payload.findings[0].title)).toHaveCount(0);
  });

  test("mutating identities one at a time is refused and keeps the valid session", async ({
    page,
  }) => {
    const valid = await loadValidExport(page);
    const title = valid.findings[0].title;
    // The asset-identity mutation must be real: without a carried asset the
    // body is byte-identical to the valid export and asserts a stale error.
    expect(valid.assets?.length ?? 0).toBeGreaterThan(0);
    const mutations: Array<[string, (body: Record<string, any>) => void]> = [
      ["report_id", (b) => {
        b.report_id = "0".repeat(64);
      }],
      ["document.sha256", (b) => {
        b.document.sha256 = "a".repeat(64);
      }],
      ["execution.run_key", (b) => {
        if (b.execution) b.execution.run_key = "b".repeat(64);
      }],
      ["asset sha256", (b) => {
        if (Array.isArray(b.assets) && b.assets[0]) b.assets[0].sha256 = "c".repeat(64);
      }],
    ];

    for (const [label, mutate] of mutations) {
      const body = structuredClone(valid);
      mutate(body);
      await importReportBytes(page, `${label}.json`, JSON.stringify(body));
      const dialog = page.locator("[role=dialog]");
      if (await dialog.isVisible().catch(() => false)) {
        const confirm = dialog.getByRole("button", { name: /clear and open/i });
        if (await confirm.count()) await confirm.click();
      }
      await expect(page.locator("#import-error"), label).toBeVisible({ timeout: 10_000 });
      await expect(page.getByText(title).first(), `session survived ${label}`).toBeVisible();
    }
  });

  test("rejected attachment does not retain bytes; same-digest attach works; delayed replace cannot attach stale bytes", async ({
    page,
  }) => {
    // Evidence-only import: no gallery-retained bytes, so a rejected attach
    // cannot be confused with a previously verified matching source.
    await gotoEmptyWorkspace(page);
    const exported = JSON.parse(
      readFileSync(path.join(ROOT, "apps/web/public/examples", CARD, "report.json"), "utf8"),
    );
    await importReportBytes(page, "evidence-only.json", JSON.stringify(exported));
    await waitForImportedReport(page);

    await page.locator("#input-attach-source").setInputFiles({
      name: "wrong.pdf",
      mimeType: "application/pdf",
      buffer: CONTROL_PDF,
    });
    await expect(page.locator("#import-error")).toBeVisible();
    const afterReject = await page.evaluate(() => {
      const inspect = (globalThis as { __inspect?: { getState(): { hasSourceBytes: boolean } } })
        .__inspect;
      return inspect?.getState().hasSourceBytes ?? null;
    });
    expect(afterReject).not.toBe(true);

    await page.locator("#input-attach-source").setInputFiles({
      name: "duplicates-four.pdf",
      mimeType: "application/pdf",
      buffer: SOURCE_PDF,
    });
    await page.waitForFunction(
      () =>
        (
          globalThis as { __inspect?: { getState(): { hasSourceBytes: boolean; sourceAttached: boolean } } }
        ).__inspect?.getState().sourceAttached === true ||
        (
          globalThis as { __inspect?: { getState(): { hasSourceBytes: boolean } } }
        ).__inspect?.getState().hasSourceBytes === true,
      { timeout: 10_000 },
    );

    const amountReport = readFileSync(
      path.join(ROOT, "apps/web/public/examples/amount/report.json"),
      "utf8",
    );
    const race = await page.evaluate(
      async ({ pdf, reportB }) => {
        const inspect = (
          globalThis as {
            __inspect?: {
              attachSource(c: {
                name: string;
                size: number;
                arrayBuffer(): Promise<ArrayBuffer>;
              }): Promise<void>;
              offerFile(c: {
                name: string;
                type: string;
                size: number;
                slice: (a: number, b: number) => { arrayBuffer(): Promise<ArrayBuffer> };
                arrayBuffer(): Promise<ArrayBuffer>;
              }): Promise<void>;
              getState(): {
                generation: number;
                report: { report_id?: string; document?: { sha256?: string } } | null;
                hasSourceBytes: boolean;
              };
            };
          }
        ).__inspect;
        if (!inspect) return { error: "no-inspect" };
        const pdfBytes = Uint8Array.from(pdf);
        const reportBytes = new TextEncoder().encode(reportB);
        let release!: () => void;
        const gate = new Promise<void>((resolve) => {
          release = resolve;
        });
        const pending = inspect.attachSource({
          name: "slow.pdf",
          size: pdfBytes.byteLength,
          arrayBuffer: () => gate.then(() => pdfBytes.slice().buffer as ArrayBuffer),
        });
        await inspect.offerFile({
          name: "amount.json",
          type: "application/json",
          size: reportBytes.byteLength,
          slice: (a, b) => ({
            arrayBuffer: async () => reportBytes.slice(a, b).buffer as ArrayBuffer,
          }),
          arrayBuffer: async () => reportBytes.buffer as ArrayBuffer,
        });
        release();
        await pending;
        const snap = inspect.getState();
        return {
          reportId: snap.report?.report_id ?? null,
          documentSha: snap.report?.document?.sha256 ?? null,
          hasSourceBytes: snap.hasSourceBytes,
          amountId: (JSON.parse(reportB) as { report_id: string }).report_id,
        };
      },
      { pdf: Array.from(SOURCE_PDF), reportB: amountReport },
    );
    expect(race.error ?? null).toBeNull();
    expect(race.reportId).toBe(race.amountId);
    expect(race.hasSourceBytes).toBe(false);
  });
});
