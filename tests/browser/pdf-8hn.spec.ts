/**
 * pdf-8hn — Focused regression spec for T08 review follow-ups:
 * 1. Stale handle and document nulled on failed replace (F1).
 * 2. Unenforced OCR/raster caps enforced in reader and plan (F2).
 * 3. Region label edit propagates to ContractRegion record (F3).
 * 4. Busy refusal emits 'rejected' event and sets error (F5).
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { expect, test, type Page } from '@playwright/test';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const WEB = join(ROOT, 'apps', 'web');
const FIXTURE_PUBLIC = join(ROOT, 'fixtures', 'public');
const PREVIEW = '/src/features/open/preview.html';

function buildPdf(options: {
  pages: number;
  box?: [number, number, number, number];
  rotate?: number;
  text?: string;
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
  const stream = `BT /F1 24 Tf 72 700 Td (${options.text ?? 'page'}) Tj ET`;
  push('%PDF-1.4\n');
  obj(1, '<< /Type /Catalog /Pages 2 0 R >>');
  const kids = Array.from(
    { length: nPages },
    (_, i) => `${firstPage + i} 0 R`,
  ).join(' ');
  obj(2, `<< /Type /Pages /Kids [${kids}] /Count ${nPages} >>`);
  obj(fontObj, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
  obj(
    contentObj,
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  );
  for (let i = 0; i < nPages; i++) {
    const rot = options.rotate ? ` /Rotate ${options.rotate}` : '';
    obj(
      firstPage + i,
      `<< /Type /Page /Parent 2 0 R /MediaBox [${box.join(
        ' ',
      )}]${rot} /Resources << /Font << /F1 ${fontObj} 0 R >> >> /Contents ${contentObj} 0 R >>`,
    );
  }
  const xrefPos = len;
  const count = firstPage + nPages;
  let xref = `xref\n0 ${count}\n0000000000 65535 f \n`;
  for (let i = 1; i < count; i++) {
    const off = offsets[i];
    xref +=
      off !== undefined
        ? `${String(off).padStart(10, '0')} 00000 n \n`
        : '0000000000 65535 f \n';
  }
  push(xref);
  push(`trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`);
  const out = new Uint8Array(len);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

interface Harness {
  base: string;
  close: () => Promise<void>;
}

let harness: Harness;

test.beforeAll(async () => {
  const viteEntry = pathToFileURL(
    join(WEB, 'node_modules', 'vite', 'dist', 'node', 'index.js'),
  ).href;
  const { createServer } = (await import(viteEntry)) as {
    createServer: (opts: {
      root: string;
      server: { port: number };
      logLevel: string;
    }) => Promise<{
      listen: () => Promise<void>;
      resolvedUrls: { local: string[] };
      close: () => Promise<void>;
    }>;
  };
  const server = await createServer({
    root: WEB,
    server: { port: 0 },
    logLevel: 'warn',
  });
  await server.listen();
  const base = server.resolvedUrls.local[0].replace(/\/$/, '');
  harness = { base, close: () => server.close() };
});

test.afterAll(async () => {
  await harness.close();
});

test.setTimeout(60_000);

async function openPreview(page: Page, query = ''): Promise<void> {
  await page.goto(`${harness.base}${PREVIEW}${query}`);
  await page.waitForFunction(
    () => (globalThis as { __t08?: unknown }).__t08 !== undefined,
    undefined,
    { timeout: 30_000 },
  );
  await expect(page.locator('[data-testid=file-drop]')).toBeVisible();
}

async function offerFile(
  page: Page,
  name: string,
  bytes: Uint8Array,
  mimeType = 'application/pdf',
): Promise<void> {
  await page.locator('[data-testid=file-input]').setInputFiles({
    name,
    mimeType,
    buffer: Buffer.from(bytes),
  });
}

async function waitForDocument(page: Page, pageCount?: number): Promise<void> {
  await expect(page.locator('[data-testid=doc-label]')).toBeVisible({
    timeout: 30_000,
  });
  if (pageCount !== undefined) {
    await expect(page.locator('[data-testid=doc-meta]')).toContainText(
      `${pageCount} page`,
    );
  }
}

// ---------------------------------------------------------------------------
// Fix 1: Stale handle on failed replace (Review F1)
// ---------------------------------------------------------------------------
test('F1: failed replace nulls currentHandle and currentDocument', async ({
  page,
}) => {
  await openPreview(page);
  await offerFile(page, 'first.pdf', buildPdf({ pages: 2, text: 'First Doc' }));
  await waitForDocument(page, 2);

  const initialHandle = await page.evaluate(
    () => (globalThis as any).__t08.controller.currentHandle !== null,
  );
  const initialDoc = await page.evaluate(
    () => (globalThis as any).__t08.controller.currentDocument?.label,
  );
  expect(initialHandle).toBe(true);
  expect(initialDoc).toBe('first.pdf');

  // Attempt replace with an invalid file (non-PDF image) directly via controller.offer
  const outcome = await page.evaluate(async () => {
    const { controller } = (globalThis as any).__t08;
    const badCandidate = {
      name: 'corrupt.png',
      type: 'image/png',
      size: 100,
      arrayBuffer: async () => new Uint8Array(100).buffer,
      slice: () => ({ arrayBuffer: async () => new Uint8Array(100).buffer }),
    };
    const res = await controller.offer(badCandidate);
    return {
      ok: res.ok,
      kind: res.ok ? null : res.error.kind,
      handleAfter: controller.currentHandle,
      docAfter: controller.currentDocument,
    };
  });

  expect(outcome.ok).toBe(false);
  expect(outcome.kind).toBe('not_pdf');
  expect(outcome.handleAfter).toBeNull();
  expect(outcome.docAfter).toBeNull();

  // Also assert that host fileState returned to idle
  const fileState = await page.evaluate(
    () => (globalThis as any).__t08.controller.host.fileState,
  );
  expect(fileState).toBe('idle');
});

// ---------------------------------------------------------------------------
// Fix 2: Unenforced OCR/raster caps (Review F2)
// ---------------------------------------------------------------------------
test('F2: reader limits receive profile.maxRasterPixels and startRun enforces maxOcrPagesPerRun', async ({
  page,
}) => {
  // Test desktop profile limits
  await openPreview(page);
  const desktopRasterCap = await page.evaluate(
    () => (globalThis as any).__t08.adapter.config.limits.maxRasterPixels,
  );
  const desktopExpected = await page.evaluate(
    () => (globalThis as any).__t08.profile.maxRasterPixels,
  );
  expect(desktopRasterCap).toBe(desktopExpected);
  expect(desktopRasterCap).toBe(4_000_000);

  // Test mobile profile limits
  await openPreview(page, '?profile=mobile');
  const mobileRasterCap = await page.evaluate(
    () => (globalThis as any).__t08.adapter.config.limits.maxRasterPixels,
  );
  const mobileExpected = await page.evaluate(
    () => (globalThis as any).__t08.profile.maxRasterPixels,
  );
  expect(mobileRasterCap).toBe(mobileExpected);
  expect(mobileRasterCap).toBe(2_000_000);

  // Test OCR page count capping in startRun:
  // Open an 8-page document on desktop (desktop maxOcrPagesPerRun = 5)
  await openPreview(page);
  await offerFile(page, 'eight.pdf', buildPdf({ pages: 8 }));
  await waitForDocument(page, 8);

  // Select all 8 pages
  await page.locator('[data-testid=select-all]').click();
  await expect(page.locator('[data-testid=pages-summary]')).toHaveText(
    '8 of 8 pages selected',
  );

  // Start run
  await page.locator('[data-testid=start-run]').click();
  const checks = await page
    .locator('[data-testid=plan-checks] li')
    .evaluateAll((els) =>
      els.map((el) => ({
        id: el.getAttribute('data-check-id'),
        page: Number(el.getAttribute('data-page')),
        capability: el.getAttribute('data-capability'),
      })),
    );

  const nativeChecks = checks.filter((c) => c.capability === 'native_text');
  const renderChecks = checks.filter((c) => c.capability === 'render');
  const ocrChecks = checks.filter((c) => c.capability === 'ocr');

  // All 8 pages get native_text and render
  expect(nativeChecks.length).toBe(8);
  expect(renderChecks.length).toBe(8);

  // Exactly 5 pages get OCR (capped by maxOcrPagesPerRun = 5)
  expect(ocrChecks.length).toBe(5);
  const ocrPages = ocrChecks.map((c) => c.page);
  expect(ocrPages).toEqual([0, 1, 2, 3, 4]);
});

// ---------------------------------------------------------------------------
// Fix 3: Region label edit propagation (Review F3)
// ---------------------------------------------------------------------------
test('F3: edited region label propagates to contract region in check plan', async ({
  page,
}) => {
  await openPreview(page);
  const bytes = readFileSync(join(FIXTURE_PUBLIC, 'mapping-amount.pdf'));
  await offerFile(page, 'mapping-amount.pdf', bytes);
  await waitForDocument(page, 1);

  const surface = page.locator('[data-testid=region-surface]');
  const canvas = page.locator('[data-testid=region-canvas]');
  await expect
    .poll(async () => canvas.getAttribute('width'), { timeout: 30_000 })
    .not.toBe('0');

  await surface.scrollIntoViewIfNeeded();
  const box = await surface.boundingBox();
  expect(box).not.toBeNull();
  // Drag a region
  await page.mouse.move(box!.x + 50, box!.y + 50);
  await page.mouse.down();
  await page.mouse.move(box!.x + 250, box!.y + 150, { steps: 5 });
  await page.mouse.up();

  await expect(page.locator('[data-testid=region-committed]')).toBeVisible();

  // Edit the region label in the UI
  const labelInput = page.locator('[data-testid=region-label]');
  await expect(labelInput).toBeVisible();
  await labelInput.fill('Grand Total Header Box');

  // Start run
  await page.locator('[data-testid=start-run]').click();
  await expect(page.locator('[data-testid=plan]')).toBeVisible();

  // Verify that the run plan's OCR check uses the region bindings and the label in the region record was updated
  const checks = await page
    .locator('[data-testid=plan-checks] li')
    .evaluateAll((els) =>
      els.map((el) => ({
        id: el.getAttribute('data-check-id'),
        page: Number(el.getAttribute('data-page')),
        capability: el.getAttribute('data-capability'),
        region: el.getAttribute('data-region'),
      })),
    );

  const ocrCheck = checks.find((c) => c.capability === 'ocr');
  expect(ocrCheck).toBeDefined();
  expect(ocrCheck!.region).toBeTruthy();

  // Assert contract region label passed to startRun carries the user-edited text
  const regionLabel = await page.evaluate(() => {
    const map = (globalThis as any).__t08.getLastStartRunRegions();
    return map?.get(0)?.label;
  });
  expect(regionLabel).toBe('Grand Total Header Box');
});

// ---------------------------------------------------------------------------
// Fix 4: Busy refusal event (Review F5)
// ---------------------------------------------------------------------------
test('F5: busy refusal emits rejected event and surfaces error', async ({
  page,
}) => {
  await openPreview(page);

  // Directly exercise controller with two concurrent offers
  const result = await page.evaluate(async () => {
    const { controller } = (globalThis as any).__t08;
    const events: any[] = [];
    const unsub = controller.subscribe((e: any) => events.push(e));

    // Create a slow candidate that holds busy = true
    let resolveArrayBuffer!: (v: ArrayBuffer) => void;
    const slowCandidate = {
      name: 'slow.pdf',
      type: 'application/pdf',
      size: 500,
      arrayBuffer: () => new Promise<ArrayBuffer>((res) => { resolveArrayBuffer = res; }),
      slice: () => ({ arrayBuffer: () => new Promise<ArrayBuffer>((res) => { resolveArrayBuffer = res; }) }),
    };

    const fastCandidate = {
      name: 'fast.pdf',
      type: 'application/pdf',
      size: 200,
      arrayBuffer: async () => new Uint8Array(200).buffer,
      slice: () => ({ arrayBuffer: async () => new Uint8Array(200).buffer }),
    };

    const p1 = controller.offer(slowCandidate);
    // While p1 is validating, offer fastCandidate
    const outcome2 = await controller.offer(fastCandidate);

    // Now resolve p1
    resolveArrayBuffer(new Uint8Array(500).buffer);
    await p1.catch(() => {});
    unsub();

    return {
      outcome2Ok: outcome2.ok,
      outcome2Error: outcome2.ok ? null : outcome2.error,
      rejectedEvent: events.find((e) => e.type === 'rejected' && e.error?.detail === 'open:busy'),
    };
  });

  expect(result.outcome2Ok).toBe(false);
  expect(result.outcome2Error?.detail).toBe('open:busy');
  expect(result.rejectedEvent).toBeDefined();
  expect(result.rejectedEvent.kind).toBe('open_failed');
  expect(result.rejectedEvent.error.detail).toBe('open:busy');
});
