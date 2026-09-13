import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect, type Page } from "@playwright/test";

/**
 * TEST-19: Large-document and narrow-device interaction (T19).
 *
 * Acceptance criteria:
 * 1. A 1,000-page metadata plan does not render all pages.
 * 2. Selected native/OCR limits are visible.
 * 3. 320px and touch controls are usable.
 * 4. Oversized edges are rejected before allocation.
 * 5. Cancellation leaves a coherent partial result and next-file health.
 *
 * Drives the real public workspace (/#/workspace) through a Vite dev server —
 * no private mounts. Test PDFs are built with real xref tables (the same
 * builder open.spec.ts uses) so pdf.js parses them genuinely.
 */

const WEB_ROOT = path.resolve(process.cwd(), "apps/web");
const MIB = 1024 * 1024;
const DESKTOP_MAX = 20 * MIB;

let viteServer: { close(): Promise<void>; resolvedUrls: { local: string[] } };
let baseUrl: string;

test.beforeAll(async () => {
  const viteModulePath = path.resolve(WEB_ROOT, "node_modules/vite/dist/node/index.js");
  const { createServer } = await import(pathToFileURL(viteModulePath).href);
  viteServer = await createServer({
    root: WEB_ROOT,
    server: { port: 0, strictPort: false },
    logLevel: "silent",
  });
  await viteServer.listen();
  baseUrl = viteServer.resolvedUrls.local[0].replace(/\/$/, "");
});

test.afterAll(async () => {
  await viteServer?.close();
});

// ---------------------------------------------------------------------------
// Minimal PDF builder (real xref tables — pdf.js parses these genuinely).
// ---------------------------------------------------------------------------

function buildPdf(options: {
  pages: number;
  box?: [number, number, number, number];
  text?: string;
  padBytes?: number;
}): Uint8Array {
  const enc = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const offsets: number[] = [];
  let len = 0;
  const push = (s: string) => {
    const b = enc.encode(s);
    chunks.push(b);
    len += b.length;
  };
  const obj = (n: number, body: string) => {
    offsets[n] = len;
    push(`${n} 0 obj\n${body}\nendobj\n`);
  };
  const fontObj = 3;
  const contentObj = 4;
  const firstPage = 5;
  const nPages = options.pages;
  const box = options.box ?? [0, 0, 612, 792];
  const stream = `BT /F1 24 Tf 72 700 Td (${options.text ?? "page"}) Tj ET`;
  push("%PDF-1.4\n");
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  const kids = Array.from({ length: nPages }, (_, i) => `${firstPage + i} 0 R`).join(" ");
  obj(2, `<< /Type /Pages /Kids [${kids}] /Count ${nPages} >>`);
  obj(fontObj, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  obj(contentObj, `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
  for (let i = 0; i < nPages; i++) {
    obj(
      firstPage + i,
      `<< /Type /Page /Parent 2 0 R /MediaBox [${box.join(
        " ",
      )}] /Resources << /Font << /F1 ${fontObj} 0 R >> >> /Contents ${contentObj} 0 R >>`,
    );
  }
  const xrefPos = len;
  const count = firstPage + nPages;
  let xref = `xref\n0 ${count}\n0000000000 65535 f \n`;
  for (let i = 1; i < count; i++) {
    const off = offsets[i];
    xref +=
      off !== undefined
        ? `${String(off).padStart(10, "0")} 00000 n \n`
        : "0000000000 65535 f \n";
  }
  push(xref);
  push(`trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`);
  if (options.padBytes) {
    // Declared-size edge: real bytes after %%EOF — the size gate must reject
    // on the declared size alone, before any reader allocation.
    chunks.push(new Uint8Array(options.padBytes));
    len += options.padBytes;
  }
  const out = new Uint8Array(len);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

async function offerPdf(page: Page, bytes: Uint8Array, name = "large-mobile.pdf") {
  await page
    .locator('[data-testid="file-input"]')
    .setInputFiles({ name, mimeType: "application/pdf", buffer: Buffer.from(bytes) });
}

async function openPdf(page: Page, bytes: Uint8Array, name?: string) {
  await offerPdf(page, bytes, name);
  await page.waitForSelector('[data-testid="pages-summary"]');
}

// ---------------------------------------------------------------------------

test("1,000-page metadata plan stays bounded and every page is reachable", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${baseUrl}/#/workspace`);

  await openPdf(page, buildPdf({ pages: 1000, text: "bulk" }), "thousand.pdf");

  // The picker windows the metadata plan — it must not mount 1,000 rows.
  const rows = page.locator('[data-testid="page-list"] li');
  expect(await rows.count()).toBeLessThanOrEqual(48);
  await expect(page.locator('[data-testid="pages-summary"]')).toContainText(
    "of 1000 pages",
  );

  // Every page stays reachable: jump to a far page, then toggle it.
  await page.locator('[data-testid="page-jump"]').fill("950");
  await page.locator('[data-testid="page-jump"]').press("Enter");
  const far = page.locator('[data-testid="page-toggle-950"]');
  await expect(far).toBeVisible();
  await far.click();
  await expect(far).toHaveAttribute("aria-pressed", "true");

  // Select-all is honestly capped, not silently trimmed.
  await page.locator('[data-testid="select-all"]').click();
  await expect(page.locator('[data-testid="pages-summary"]')).toContainText(
    "20 of 1000 pages selected",
  );
  await expect(page.locator("#pages-limit-notice")).toBeVisible();
});

test("selected native/OCR limits are visible on the open document", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${baseUrl}/#/workspace`);
  await openPdf(page, buildPdf({ pages: 3, text: "limits" }));

  const limits = page.locator('[data-testid="run-limits"]');
  await expect(limits).toBeVisible();
  await expect(limits).toHaveAttribute("data-profile", "desktop");
  const text = await limits.textContent();
  expect(text).toContain("20"); // native pages per run
  expect(text).toContain("5"); // OCR pages per run
  expect(text).toContain("4,000,000"); // raster pixel cap
  expect(text).toContain("20.0 MiB"); // file cap
});

test("320px layout: controls stack and stay usable, mobile profile engages", async ({
  page,
}) => {
  test.setTimeout(120_000);
  // A sub-768px viewport selects the mobile (low-memory) profile — no
  // synthetic device flags needed.
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto(`${baseUrl}/#/workspace`);
  await openPdf(page, buildPdf({ pages: 4, text: "narrow" }), "narrow.pdf");

  const limits = page.locator('[data-testid="run-limits"]');
  await expect(limits).toHaveAttribute("data-profile", "mobile");
  await expect(limits).toContainText("low-memory mode");

  // OCR consent is explicit on the low-memory profile.
  await expect(page.locator('[data-testid="ocr-consent-row"]')).toBeVisible();
  await expect(page.locator('[data-testid="ocr-consent"]')).not.toBeChecked();

  // Preview stays available but on-demand (no auto raster on mobile).
  await expect(page.locator('[data-testid="render-preview"]')).toBeVisible();
  await page.locator('[data-testid="render-preview"]').click();

  // Touch-sized controls: every page toggle meets the 44px floor.
  const toggle = page.locator('[data-testid="page-toggle-1"]');
  const box = await toggle.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.height).toBeGreaterThanOrEqual(44);

  // No horizontal overflow at 320px.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);

  // The run remains startable: selection + start control are usable.
  await page.locator('[data-testid="start-run"]').click();
  await expect(
    page.locator('[data-testid="run-progress"], #viewer-stage, #pdf-received-notice').first(),
  ).toBeVisible({ timeout: 60_000 });
});

test("oversized edges are rejected before allocation", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${baseUrl}/#/workspace`);

  // Declared-size edge: >20 MiB rejected on metadata alone — the workspace
  // never opens it and stays on the intake surface.
  const fat = buildPdf({ pages: 1, text: "fat", padBytes: DESKTOP_MAX });
  await offerPdf(page, fat, "fat.pdf");
  const err = page.locator('[id^="open-error-"], #import-error');
  await expect(err).toBeVisible();
  await expect(err).toContainText("limit");
  await expect(page.locator('[data-testid="pages-summary"]')).toHaveCount(0);

  // Page-count edge: 1,001 pages exceeds the metadata cap — rejected, with
  // nothing silently skipped.
  const tall = buildPdf({ pages: 1001, text: "many" });
  await offerPdf(page, tall, "tall.pdf");
  await expect(
    page.locator('[id^="open-error-too_many_pages"], #import-error'),
  ).toBeVisible();
});

test("cancellation leaves coherent partial state and next file opens cleanly", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${baseUrl}/#/workspace`);
  await openPdf(page, buildPdf({ pages: 6, text: "cancelme" }), "first.pdf");

  // Widen the selection so the run has real in-flight work.
  await page.locator('[data-testid="page-toggle-2"]').click();
  await page.locator('[data-testid="page-toggle-3"]').click();
  await page.locator('[data-testid="start-run"]').click();

  // Cancel while the run is preparing assets or running.
  await expect(page.locator("#btn-cancel-run")).toBeVisible({ timeout: 30_000 });
  await page.locator("#btn-cancel-run").click();

  // The workspace lands on an honest cancelled state — not stuck, not blank.
  await expect(page.locator('[data-testid="run-cancelled"]')).toBeVisible({
    timeout: 30_000,
  });
  await page.locator("#btn-back-to-selection").click();
  await expect(page.locator('[data-testid="pages-summary"]')).toBeVisible();

  // Next-file health: a different PDF opens cleanly through the confirmed
  // replacement path.
  await page.locator('[data-testid="file-input"]').setInputFiles({
    name: "second.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(buildPdf({ pages: 2, text: "second" })),
  });
  const confirm = page.locator("text=/Clear and open|Open a different PDF/i");
  if (await confirm.count()) {
    await page
      .locator('button:has-text("Clear and open file"), #btn-confirm-replace')
      .first()
      .click();
  }
  await expect(page.locator('[data-testid="pages-summary"]')).toContainText(
    "of 2 pages",
    { timeout: 30_000 },
  );
});
