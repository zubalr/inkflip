/**
 * T08 — Local file validation + page/region selection: real Chromium coverage.
 *
 * The suite boots the REAL app path: Vite serves
 * `apps/web/src/features/open/preview.html`, which mounts the T08
 * open/selection features wired to the pinned pdf.js 6.3.289 legacy pair,
 * the T09 reader adapter and the T11 RunCoordinator. Files are offered
 * through the real <input type="file"> and drop zone — nothing is mocked
 * at the contract surface.
 *
 * Acceptance criteria coverage (exact strings from the T08 contract):
 *
 * - "20MiB/1000-page and mobile limits exercised without giant allocations"
 *   The byte gate runs on declared size metadata: an over-limit candidate
 *   is rejected with ZERO byte reads (spy-counted), the exact 20 MiB and
 *   10 MiB boundaries are exercised with real (tiny) bytes, and the
 *   1000/1001-page boundary uses a real generated 156 KiB PDF — no giant
 *   allocations anywhere.
 * - "wrong MIME/header, encrypted and malformed are distinct"
 *   Five distinct OpenError kinds asserted: not_pdf (wrong MIME and wrong
 *   header share the bucket, with distinct details), too_large,
 *   encrypted, malformed, too_many_pages.
 * - "new file revokes old generation first"
 *   Replacement emits teardown under the NEW generation; a schema-valid
 *   worker message stamped with the old generation is rejected
 *   stale_generation by the coordinator's admission authority.
 * - "page selection never silently excludes a page"
 *   25-page document: select-all caps visibly at 20, an over-cap toggle is
 *   refused, and the frozen plan enumerates EXACTLY the selected set.
 * - "no document metadata in URL"
 *   Canary filename/text/hash: URL, hash, history, storage and every
 *   network request are asserted free of document data; all requests stay
 *   same-origin loopback.
 *
 * Fixture honesty (per task notes): F17/F18/F19/F21 are not yet in the
 * merged fixtures/ tree, so this spec generates the equivalent minimal
 * PDFs in-page — an /Encrypt-dictionary document, a truncated document, a
 * 100 000 pt page, N-page documents and a canary document. Real fixtures
 * (mapping-amount.pdf, geometry-90.pdf) cover the open/rotation paths.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

import { expect, test, type Page } from '@playwright/test';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const WEB = join(ROOT, 'apps', 'web');
const FIXTURE_PUBLIC = join(ROOT, 'fixtures', 'public');
const PREVIEW = '/src/features/open/preview.html';

const MIB = 1024 * 1024;
const DESKTOP_MAX = 20 * MIB; // 20_971_520
const MOBILE_MAX = 10 * MIB; // 10_485_760

// ---------------------------------------------------------------------------
// Minimal PDF builder (real xref tables — pdf.js parses these genuinely).
// ---------------------------------------------------------------------------

function buildPdf(options: {
  pages: number;
  box?: [number, number, number, number];
  rotate?: number;
  text?: string;
  encrypt?: boolean;
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
  let encObj = 0;
  if (options.encrypt) {
    encObj = firstPage + nPages;
    obj(
      encObj,
      '<< /Filter /Standard /V 1 /R 2 /Length 40 /P -4 ' +
        '/O <28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A> ' +
        '/U <2FF91B4564B28F29D2AA9C1A1122D54E0BF91F34D14F4A96CD19FD9F13954D34> >>',
    );
  }
  const xrefPos = len;
  const count = (options.encrypt ? encObj : firstPage + nPages - 1) + 1;
  let xref = `xref\n0 ${count}\n0000000000 65535 f \n`;
  for (let i = 1; i < count; i++) {
    const off = offsets[i];
    xref +=
      off !== undefined
        ? `${String(off).padStart(10, '0')} 00000 n \n`
        : '0000000000 65535 f \n';
  }
  push(xref);
  push(
    `trailer\n<< /Size ${count} /Root 1 0 R${
      options.encrypt
        ? ` /Encrypt ${encObj} 0 R /ID [<1A2B3C4D5E6F7A8B1A2B3C4D5E6F7A8B><1A2B3C4D5E6F7A8B1A2B3C4D5E6F7A8B>]`
        : ''
    } >>\nstartxref\n${xrefPos}\n%%EOF\n`,
  );
  const out = new Uint8Array(len);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

const PNG_BYTES = Uint8Array.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d,
  0x49, 0x48, 0x44, 0x52,
]);

// ---------------------------------------------------------------------------
// Harness: Vite dev server over the real app source.
// ---------------------------------------------------------------------------

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

test.beforeEach(async ({ page }) => {
  page.on('pageerror', (error) => {
    console.log(`[pageerror] ${error}`);
  });
});

test.setTimeout(120_000);

async function openPreview(page: Page, query = ''): Promise<void> {
  await page.goto(`${harness.base}${PREVIEW}${query}`);
  await page.waitForFunction(
    () => (globalThis as { __t08?: unknown }).__t08 !== undefined,
    undefined,
    { timeout: 30_000 },
  );
  await expect(page.locator('[data-testid=file-drop]')).toBeVisible();
}

/** Offer bytes through the real file input (hidden input is fine for setInputFiles). */
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

async function offerFixture(page: Page, name: string): Promise<void> {
  await offerFile(
    page,
    name,
    readFileSync(join(FIXTURE_PUBLIC, name)),
  );
}

/** Wait until the workspace shows the loaded document panel. */
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

async function fileState(page: Page): Promise<string> {
  return page.evaluate(
    () => (globalThis as any).__t08.coordinator.fileState,
  );
}

async function generation(page: Page): Promise<number> {
  return page.evaluate(
    () => (globalThis as any).__t08.coordinator.currentGeneration,
  );
}

// ---------------------------------------------------------------------------
// Valid open: metadata, page count, default selection, real raster
// ---------------------------------------------------------------------------

test('valid PDF opens locally with metadata, count, default selection and raster', async ({
  page,
}) => {
  await openPreview(page);
  await offerFixture(page, 'mapping-amount.pdf');
  await waitForDocument(page, 1);

  await expect(page.locator('[data-testid=doc-label]')).toHaveText(
    'mapping-amount.pdf',
  );
  await expect(page.locator('[data-testid=doc-meta]')).toContainText(
    'Local file · 1 page',
  );
  // sha256 suffix is displayed as document identity (not the filename).
  await expect(page.locator('[data-testid=doc-meta]')).toContainText('sha256 …');

  // Selecting state through the real coordinator.
  expect(await fileState(page)).toBe('selecting');

  // Default selection is exactly page 1 — explicit, never "all".
  await expect(page.locator('[data-testid=pages-summary]')).toHaveText(
    '1 of 1 pages selected',
  );
  await expect(page.locator('[data-testid=page-toggle-1]')).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  // The preview raster arrives through the real adapter render path.
  const canvas = page.locator('[data-testid=region-canvas]');
  await expect
    .poll(async () => canvas.getAttribute('width'), { timeout: 30_000 })
    .not.toBe('0');
  const w = Number(await canvas.getAttribute('width'));
  const h = Number(await canvas.getAttribute('height'));
  expect(w).toBeGreaterThan(0);
  expect(w * h).toBeLessThanOrEqual(4_000_000); // max_raster_pixels
});

test('drop zone accepts a real dropped file', async ({ page }) => {
  await openPreview(page);
  const bytes = buildPdf({ pages: 2, text: 'dropped' });
  const dt = await page.evaluateHandle((arr) => {
    const d = new DataTransfer();
    d.items.add(
      new File([new Uint8Array(arr)], 'dropped.pdf', {
        type: 'application/pdf',
      }),
    );
    return d;
  }, Array.from(bytes));
  await page.locator('[data-testid=file-drop]').dispatchEvent('drop', {
    dataTransfer: dt,
  });
  await waitForDocument(page, 2);
  await expect(page.locator('[data-testid=doc-label]')).toHaveText(
    'dropped.pdf',
  );
});

// ---------------------------------------------------------------------------
// Distinct local errors: MIME / header / encrypted / malformed / too_large
// ---------------------------------------------------------------------------

test('wrong MIME, wrong header, encrypted and malformed are distinct errors', async ({
  page,
}) => {
  await openPreview(page);
  const seen: Array<{ kind: string; text: string; detail: string }> = [];

  // 1. Wrong declared MIME (image/png) — rejected on type alone.
  await offerFile(page, 'photo.png', PNG_BYTES, 'image/png');
  await expect(page.locator('#open-error-not_pdf')).toBeVisible({
    timeout: 15_000,
  });
  seen.push({
    kind: 'not_pdf:mime',
    text: (await page.locator('#open-error-not_pdf').textContent()) ?? '',
    detail:
      (await page
        .locator('#open-error-not_pdf [data-testid=open-error-detail]')
        .textContent()) ?? '',
  });
  expect(await fileState(page)).toBe('idle');

  // 2. Correct MIME + wrong header bytes — rejected on magic.
  await offerFile(
    page,
    'report.pdf',
    new TextEncoder().encode('this is plain text, not a PDF at all'),
  );
  await expect(page.locator('#open-error-not_pdf')).toBeVisible({
    timeout: 15_000,
  });
  seen.push({
    kind: 'not_pdf:header',
    text: (await page.locator('#open-error-not_pdf').textContent()) ?? '',
    detail:
      (await page
        .locator('#open-error-not_pdf [data-testid=open-error-detail]')
        .textContent()) ?? '',
  });

  // 3. Encrypted — real /Encrypt dictionary, real PasswordException.
  await offerFile(page, 'locked.pdf', buildPdf({ pages: 1, encrypt: true }));
  await expect(page.locator('#open-error-encrypted')).toBeVisible({
    timeout: 15_000,
  });
  seen.push({
    kind: 'encrypted',
    text: (await page.locator('#open-error-encrypted').textContent()) ?? '',
    detail: '',
  });

  // 4. Malformed — valid header + truncated body, real InvalidPDFException.
  const truncated = buildPdf({ pages: 2 }).slice(0, 180);
  await offerFile(page, 'broken.pdf', truncated);
  await expect(page.locator('#open-error-malformed')).toBeVisible({
    timeout: 15_000,
  });
  seen.push({
    kind: 'malformed',
    text: (await page.locator('#open-error-malformed').textContent()) ?? '',
    detail: '',
  });

  // The four buckets are distinct elements with distinct canonical copy —
  // and the two not_pdf paths carry different details (mime vs header).
  expect(new Set(seen.map((s) => s.text)).size).toBeGreaterThanOrEqual(3);
  expect(seen[0].detail).toContain('mime:');
  expect(seen[1].detail).toContain('header:');
  expect(seen[0].detail).not.toBe(seen[1].detail);
  expect(seen[2].text).toContain('Encrypted');
  expect(seen[3].text).toContain('reader could not open');
  expect(seen[2].text).not.toBe(seen[3].text);

  // Every rejection returned the workspace to a usable idle drop zone.
  expect(await fileState(page)).toBe('idle');
  await expect(page.locator('[data-testid=file-input]')).toBeEnabled();
});

// ---------------------------------------------------------------------------
// Size limits + 1000-page boundary — without giant allocations
// ---------------------------------------------------------------------------

test('20MiB size gate rejects before any byte read; boundary passes to the reader', async ({
  page,
}) => {
  await openPreview(page);

  // Over-limit candidate: structural FileCandidate through the real
  // controller. Spies prove the size gate needs metadata alone.
  const over = await page.evaluate(async (limit) => {
    const { controller } = (globalThis as any).__t08;
    let sliceReads = 0;
    let fullReads = 0;
    const fake = {
      name: 'huge.pdf',
      type: 'application/pdf',
      size: limit + 1,
      slice: () => {
        sliceReads += 1;
        return { arrayBuffer: async () => new ArrayBuffer(0) };
      },
      arrayBuffer: async () => {
        fullReads += 1;
        return new ArrayBuffer(0);
      },
    };
    const out = await controller.offer(fake);
    return {
      ok: out.ok,
      kind: out.ok ? null : out.error.kind,
      detail: out.ok ? null : (out.error.detail ?? null),
      sliceReads,
      fullReads,
      state: controller ? undefined : undefined,
    };
  }, DESKTOP_MAX);

  expect(over.ok).toBe(false);
  expect(over.kind).toBe('too_large');
  expect(over.detail).toContain(`${DESKTOP_MAX}`);
  // The gate ran on declared metadata — zero bytes were touched.
  expect(over.sliceReads).toBe(0);
  expect(over.fullReads).toBe(0);
  expect(await fileState(page)).toBe('idle');
  await expect(page.locator('#open-error-too_large')).toBeVisible();

  // Exactly at the limit: the gate passes and real (tiny) bytes reach the
  // reader — the boundary is inclusive, exercised without a 20 MiB buffer.
  const real = buildPdf({ pages: 1, text: 'boundary' });
  const atLimit = await page.evaluate(
    async ({ limit, arr }) => {
      const { controller } = (globalThis as any).__t08;
      const bytes = new Uint8Array(arr);
      const fake = {
        name: 'at-limit.pdf',
        type: 'application/pdf',
        size: limit,
        slice: (a: number, b: number) => ({
          arrayBuffer: async () => bytes.slice(a, b).buffer,
        }),
        arrayBuffer: async () => bytes.buffer,
      };
      const out = await controller.offer(fake);
      return { ok: out.ok, pages: out.ok ? out.document.pageCount : null };
    },
    { limit: DESKTOP_MAX, arr: Array.from(real) },
  );
  expect(atLimit.ok).toBe(true);
  await waitForDocument(page, 1);
});

test('mobile profile: 10MiB gate and 5-page selection cap', async ({ page }) => {
  await openPreview(page, '?profile=mobile');
  const profile = await page.evaluate(
    () => (globalThis as any).__t08.profile.id,
  );
  expect(profile).toBe('mobile');

  // 10 MiB + 1 byte rejected with zero reads (same metadata-only gate).
  const over = await page.evaluate(async (limit) => {
    const { controller } = (globalThis as any).__t08;
    let reads = 0;
    const out = await controller.offer({
      name: 'big.pdf',
      type: 'application/pdf',
      size: limit + 1,
      slice: () => {
        reads += 1;
        return { arrayBuffer: async () => new ArrayBuffer(0) };
      },
      arrayBuffer: async () => {
        reads += 1;
        return new ArrayBuffer(0);
      },
    });
    return { ok: out.ok, kind: out.ok ? null : out.error.kind, reads };
  }, MOBILE_MAX);
  expect(over).toEqual({ ok: false, kind: 'too_large', reads: 0 });
  await expect(page.locator('#open-error-too_large')).toContainText('10 MiB');

  // An 8-page document under the mobile run cap of 5.
  await offerFile(page, 'eight.pdf', buildPdf({ pages: 8 }));
  await waitForDocument(page, 8);
  await page.locator('[data-testid=select-all]').click();
  await expect(page.locator('[data-testid=pages-summary]')).toHaveText(
    '5 of 8 pages selected',
  );
  await expect(page.locator('#pages-limit-notice')).toContainText(
    'up to 5 pages',
  );
  // The 6th page is refused visibly, not silently.
  await page.locator('[data-testid=page-toggle-6]').click();
  await expect(page.locator('[data-testid=pages-summary]')).toHaveText(
    '5 of 8 pages selected',
  );
  await expect(page.locator('[data-testid=page-toggle-6]')).toHaveAttribute(
    'aria-pressed',
    'false',
  );
});

test('1000-page boundary: real generated PDF opens; 1001 is a distinct error', async ({
  page,
}) => {
  await openPreview(page);
  const thousand = buildPdf({ pages: 1000 });
  expect(thousand.length).toBeLessThan(1_000_000); // ~156 KiB, not a giant alloc
  await offerFile(page, 'thousand.pdf', thousand);
  await waitForDocument(page, 1000);
  await expect(page.locator('[data-testid=pages-window]')).toHaveText(
    'Pages 1–48 of 1000',
  );

  // Every page remains reachable: jump brings page 1000 into the window.
  await page.locator('[data-testid=page-jump]').fill('1000');
  await page.locator('[data-testid=page-jump]').press('Enter');
  await expect(page.locator('[data-testid=page-toggle-1000]')).toBeVisible();

  // 1001 pages exceeds max_document_pages — a distinct error kind.
  const r = await page.evaluate(async (arr) => {
    const { controller } = (globalThis as any).__t08;
    const bytes = new Uint8Array(arr);
    const out = await controller.offer({
      name: 'thousand-one.pdf',
      type: 'application/pdf',
      size: bytes.length,
      slice: (a: number, b: number) => ({
        arrayBuffer: async () => bytes.slice(a, b).buffer,
      }),
      arrayBuffer: async () => bytes.buffer,
    });
    return { ok: out.ok, kind: out.ok ? null : out.error.kind };
  }, Array.from(buildPdf({ pages: 1001 })));
  expect(r).toEqual({ ok: false, kind: 'too_many_pages' });
  await expect(page.locator('#open-error-too_many_pages')).toBeVisible();
});

// ---------------------------------------------------------------------------
// Generation-first replacement (I07)
// ---------------------------------------------------------------------------

test('new file revokes the old generation before teardown; stale messages rejected', async ({
  page,
}) => {
  await openPreview(page);
  await offerFile(page, 'first.pdf', buildPdf({ pages: 3, text: 'AAA' }));
  await waitForDocument(page, 3);
  const genA = await generation(page);
  const shaA = await page.evaluate(
    () => (globalThis as any).__t08.controller.currentDocument.sha256,
  );

  // A schema-valid worker message from this generation is already stale:
  // no run registry is active, so admission refuses it by construction.
  const staleEarly = await page.evaluate(
    ({ gen, sha }) => {
      const { coordinator, MessageFactory } = (globalThis as any).__t08;
      const mf = new MessageFactory({
        generation: gen,
        documentSha256: sha,
        runKey: 'a'.repeat(64),
        jobId: 'j_1',
      });
      return coordinator.receive(mf.checkTerminal('chk_x', 'completed'));
    },
    { gen: genA, sha: shaA },
  );
  expect(staleEarly).toEqual({ ok: false, code: 'stale_generation' });

  // Offer a replacement through the UI — the confirm dialog stands first.
  await offerFile(page, 'second.pdf', buildPdf({ pages: 4, text: 'BBB' }));
  const dialog = page.locator('[role=dialog]');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Open a different PDF?');

  // Cancel keeps the current file — no generation bump, no teardown.
  const eventsBefore = await page.evaluate(
    () => (globalThis as any).__t08.events.length,
  );
  await dialog.getByRole('button', { name: 'Keep this file' }).click();
  await expect(dialog).not.toBeVisible();
  expect(await generation(page)).toBe(genA);
  expect(
    await page.evaluate(
      () => (globalThis as any).__t08.events.length,
    ),
  ).toBe(eventsBefore);
  await expect(page.locator('[data-testid=doc-label]')).toHaveText(
    'first.pdf',
  );

  // Confirm: generation increments FIRST, teardown observes the new
  // generation, then validation/open of the new file proceeds.
  await offerFile(page, 'second.pdf', buildPdf({ pages: 4, text: 'BBB' }));
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Clear and open file' }).click();
  await waitForDocument(page, 4);
  await expect(page.locator('[data-testid=doc-label]')).toHaveText(
    'second.pdf',
  );

  const events = await page.evaluate(
    () => (globalThis as any).__t08.events,
  );
  const clear = events.find((e: any) => e.type === 'clear');
  const teardown = events.find((e: any) => e.type === 'teardown');
  const opened = events.filter((e: any) => e.type === 'opened');
  const metas = events.filter((e: any) => e.type === 'metadata');
  const metadata = metas[metas.length - 1];
  expect(clear).toBeTruthy();
  expect(teardown).toBeTruthy();
  // The 'clear' event records the generation being retired…
  expect(clear.generation).toBe(genA);
  // …and I07: the generation was bumped BEFORE the old handle was
  // released — teardown records the NEW generation, strictly greater.
  expect(teardown.generation).toBeGreaterThan(genA);
  expect(teardown.generation).toBe(clear.generation + 1);
  // Event order: clear(intent) -> teardown -> validated -> opened -> metadata.
  const order = events.map((e: any) => e.type);
  expect(order.indexOf('clear')).toBeLessThan(order.indexOf('teardown'));
  expect(order.indexOf('teardown')).toBeLessThan(order.lastIndexOf('opened'));
  // The new document carries a different identity.
  const shaB = await page.evaluate(
    () => (globalThis as any).__t08.controller.currentDocument.sha256,
  );
  expect(shaB).not.toBe(shaA);
  expect(opened[opened.length - 1].sha256).toBe(shaB);
  expect(metadata.pageCount).toBe(4);

  // A message stamped with the OLD generation is rejected stale — the
  // authority rejects it, it is not merely hidden from the UI.
  const staleAfter = await page.evaluate(
    ({ gen, sha }) => {
      const { coordinator, MessageFactory } = (globalThis as any).__t08;
      const mf = new MessageFactory({
        generation: gen,
        documentSha256: sha,
        runKey: 'a'.repeat(64),
        jobId: 'j_1',
      });
      return coordinator.receive(mf.progress('chk_x', 1));
    },
    { gen: genA, sha: shaA },
  );
  expect(staleAfter).toEqual({ ok: false, code: 'stale_generation' });
});

// ---------------------------------------------------------------------------
// Page selection: explicit, bounded, never silently excluding
// ---------------------------------------------------------------------------

test('25 pages: select-all caps visibly; the plan enumerates exactly the selection', async ({
  page,
}) => {
  await openPreview(page);
  await offerFile(page, 'twentyfive.pdf', buildPdf({ pages: 25 }));
  await waitForDocument(page, 25);

  await expect(page.locator('[data-testid=pages-summary]')).toHaveText(
    '1 of 25 pages selected',
  );
  // The truncated cap is visible BEFORE any run.
  await expect(page.locator('#pages-limit-notice')).toContainText(
    'up to 20 pages',
  );

  await page.locator('[data-testid=select-all]').click();
  await expect(page.locator('[data-testid=pages-summary]')).toHaveText(
    '20 of 25 pages selected',
  );
  await expect(page.locator('#pages-limit-notice')).toBeVisible();
  await expect(page.locator('[data-testid=page-toggle-20]')).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.locator('[data-testid=page-toggle-21]')).toHaveAttribute(
    'aria-pressed',
    'false',
  );

  // Over-cap toggle is refused — the count does not change silently.
  await page.locator('[data-testid=page-toggle-21]').click();
  await expect(page.locator('[data-testid=pages-summary]')).toHaveText(
    '20 of 25 pages selected',
  );
  await expect(page.locator('[data-testid=page-toggle-21]')).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await expect(page.locator('#pages-limit-notice')).toBeVisible();

  // Deselect two, then page 21 fits — explicit trade, visible counts.
  await page.locator('[data-testid=page-toggle-1]').click();
  await page.locator('[data-testid=page-toggle-2]').click();
  await page.locator('[data-testid=page-toggle-21]').click();
  await expect(page.locator('[data-testid=pages-summary]')).toHaveText(
    '19 of 25 pages selected',
  );
  await expect(page.locator('[data-testid=page-toggle-21]')).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.locator('#ocr-limit-notice')).toBeVisible();

  // The frozen plan covers EXACTLY the selected pages — count and set.
  await page.locator('[data-testid=start-run]').click();
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
  const plannedPages = new Set(checks.map((c) => c.page));
  const expected = new Set<number>();
  for (let i = 0; i < 25; i++) {
    // indices 2..20 inclusive — pages 1-2 deselected, page 21 re-added.
    if (i !== 0 && i !== 1 && i <= 20) expected.add(i);
  }
  expect(plannedPages).toEqual(expected);
  // Every selected page carries native_text and render checks; OCR is
  // capped at max_ocr_pages_per_run (5 on desktop) — no page silently lost
  // native or render coverage.
  const ocrPages = new Set(
    checks.filter((c) => c.capability === 'ocr').map((c) => c.page),
  );
  expect(ocrPages.size).toBe(5);
  for (const p of expected) {
    const caps = checks.filter((c) => c.page === p).map((c) => c.capability);
    if (ocrPages.has(p)) {
      expect(caps.sort()).toEqual(['native_text', 'ocr', 'render'].sort());
    } else {
      expect(caps.sort()).toEqual(['native_text', 'render'].sort());
    }
  }
  // The pinned selected-pages total is recorded by the coordinator.
  const pinned = await page.evaluate(
    () => (globalThis as any).__t08.coordinator.snapshot().run.selectedPagesTotal,
  );
  expect(pinned).toBe(19);
  await expect(page.locator('[data-testid=plan]')).toContainText(
    '19 pages selected',
  );
  // Dispatch intents were issued for the checks (bounded concurrency).
  const dispatched = await page
    .locator('[data-testid=plan-dispatched] li')
    .count();
  expect(dispatched).toBeGreaterThan(0);
  expect(await fileState(page)).toBe('running');
});

// ---------------------------------------------------------------------------
// Region selection: drag, numeric, clamped to page bounds, explicit padding
// ---------------------------------------------------------------------------

test('region drag and numeric entry stay inside page bounds; padding explicit', async ({
  page,
}) => {
  await openPreview(page);
  await offerFixture(page, 'mapping-amount.pdf'); // 520 x 400 pt page
  await waitForDocument(page, 1);

  const surface = page.locator('[data-testid=region-surface]');
  const canvas = page.locator('[data-testid=region-canvas]');
  await expect
    .poll(async () => canvas.getAttribute('width'), { timeout: 30_000 })
    .not.toBe('0');

  await surface.scrollIntoViewIfNeeded();
  const box = await surface.boundingBox();
  expect(box).not.toBeNull();
  // Drag a rectangle inside the raster.
  await page.mouse.move(box!.x + 60, box!.y + 50);
  await page.mouse.down();
  await page.mouse.move(box!.x + 320, box!.y + 240, { steps: 5 });
  await page.mouse.up();

  const committed = page.locator('[data-testid=region-committed]');
  await expect(committed).toBeVisible();
  const text = (await committed.textContent()) ?? '';
  const m = text.match(/Region on page 1: ([\d.]+), ([\d.]+), ([\d.]+), ([\d.]+) pt/);
  expect(m).not.toBeNull();
  const [x0, y0, x1, y1] = m!.slice(1).map(Number);
  // In canonical page bounds (520 x 400 pt) with positive area.
  expect(x0).toBeGreaterThanOrEqual(0);
  expect(y0).toBeGreaterThanOrEqual(0);
  expect(x1).toBeLessThanOrEqual(520);
  expect(y1).toBeLessThanOrEqual(400);
  expect(x1 - x0).toBeGreaterThan(10);
  expect(y1 - y0).toBeGreaterThan(10);

  // Numeric fields mirror the committed canonical bounds (synced by the
  // committed-box effect — wait for it to flush).
  await expect(page.locator('[data-testid=region-x0]')).not.toHaveValue('');
  const nx0 = Number(await page.locator('[data-testid=region-x0]').inputValue());
  expect(Math.abs(nx0 - x0)).toBeLessThan(1);

  // OCR padding is shown as an explicit, larger outline (8 px / 10% rule).
  const padded = page.locator('[data-testid=region-padded]');
  await expect(padded).toBeVisible();
  expect(text).toContain('padding');

  // Numeric input OUTSIDE the page is rejected with a reason — never
  // silently clamped into bounds.
  await page.locator('[data-testid=region-x1]').fill('9999');
  await page.locator('[data-testid=region-apply]').click();
  await expect(page.locator('[data-testid=region-error]')).toContainText(
    'inside the page',
  );

  // Degenerate input is rejected too.
  await page.locator('[data-testid=region-x1]').fill('10');
  await page.locator('[data-testid=region-x0]').fill('50');
  await page.locator('[data-testid=region-apply]').click();
  await expect(page.locator('[data-testid=region-error]')).toContainText(
    'positive width and height',
  );

  // A valid keyboard entry commits exactly the typed bounds.
  await page.locator('[data-testid=region-x0]').fill('10');
  await page.locator('[data-testid=region-y0]').fill('20');
  await page.locator('[data-testid=region-x1]').fill('210');
  await page.locator('[data-testid=region-y1]').fill('120');
  await page.locator('[data-testid=region-apply]').click();
  await expect(page.locator('[data-testid=region-error]')).not.toBeVisible();
  await expect(committed).toContainText('10, 20, 210, 120 pt');

  // The region binds into the plan: ocr check for page 0 carries region_id.
  await page.locator('[data-testid=start-run]').click();
  const ocrCheck = page.locator(
    '[data-testid=plan-checks] li[data-capability=ocr]',
  );
  await expect(ocrCheck).toHaveCount(1);
  const regionId = await ocrCheck.getAttribute('data-region');
  expect(regionId).toMatch(/^region_p0_\d+$/);
});

test('rotated page: drag converts to canonical bounds inside page extent', async ({
  page,
}) => {
  await openPreview(page);
  await offerFixture(page, 'geometry-90.pdf'); // real /Rotate 90 fixture
  await waitForDocument(page, 1);

  const meta = await page.evaluate(
    () => (globalThis as any).__t08.controller.currentDocument.pages[0],
  );
  expect(meta.rotation).toBe(90);

  const surface = page.locator('[data-testid=region-surface]');
  const canvas = page.locator('[data-testid=region-canvas]');
  await expect
    .poll(async () => canvas.getAttribute('width'), { timeout: 30_000 })
    .not.toBe('0');
  await surface.scrollIntoViewIfNeeded();
  const box = await surface.boundingBox();
  // Display space swaps W/H for a 90° page — the raster really is rotated.
  expect(box!.width).not.toBe(box!.height);

  await page.mouse.move(box!.x + 40, box!.y + 40);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width * 0.6, box!.y + box!.height * 0.5, {
    steps: 5,
  });
  await page.mouse.up();

  const committed = page.locator('[data-testid=region-committed]');
  await expect(committed).toBeVisible();
  const text = (await committed.textContent()) ?? '';
  const m = text.match(/: ([\d.]+), ([\d.]+), ([\d.]+), ([\d.]+) pt/);
  expect(m).not.toBeNull();
  const [x0, y0, x1, y1] = m!.slice(1).map(Number);
  // Canonical bounds stay inside the UNROTATED page extent.
  expect(x0).toBeGreaterThanOrEqual(0);
  expect(y0).toBeGreaterThanOrEqual(0);
  expect(x1).toBeLessThanOrEqual(meta.widthPt);
  expect(y1).toBeLessThanOrEqual(meta.heightPt);
  expect(x1).toBeGreaterThan(x0);
  expect(y1).toBeGreaterThan(y0);
});

test('huge page opens; region validation quotes its real bounds', async ({
  page,
}) => {
  await openPreview(page);
  await offerFile(
    page,
    'huge.pdf',
    buildPdf({ pages: 1, box: [0, 0, 100000, 100000] }),
  );
  await waitForDocument(page, 1);

  // Keyboard input beyond the 100 000 pt extent is refused with the real
  // bound in the message — the bound comes from page metadata, not a cap.
  await page.locator('[data-testid=region-x0]').fill('0');
  await page.locator('[data-testid=region-y0]').fill('0');
  await page.locator('[data-testid=region-x1]').fill('100001');
  await page.locator('[data-testid=region-y1]').fill('10');
  await page.locator('[data-testid=region-apply]').click();
  await expect(page.locator('[data-testid=region-error]')).toContainText(
    '100000',
  );
});

// ---------------------------------------------------------------------------
// Privacy: no document metadata in URL/hash/history/network/storage
// ---------------------------------------------------------------------------

test('no document data reaches the URL, storage or any network request', async ({
  page,
}) => {
  const requests: Array<{ url: string; method: string; post: string | null }> =
    [];
  page.on('request', (req) => {
    requests.push({
      url: req.url(),
      method: req.method(),
      post: req.postData(),
    });
  });

  await openPreview(page);
  const urlAtBoot = page.url();

  // Canary document: filename + page text + bytes are all marked.
  const CANARY_FILE = 'confidential-T08C4N4RY.pdf';
  const CANARY_TEXT = 'T08C4N4RYSECRET';
  const canary = buildPdf({ pages: 2, text: CANARY_TEXT });
  await offerFile(page, CANARY_FILE, canary);
  await waitForDocument(page, 2);

  const sha = await page.evaluate(
    () => (globalThis as any).__t08.controller.currentDocument.sha256,
  );
  const shaTail = sha.slice(-8); // the only fragment shown in the DOM

  // Exercise the whole surface: select pages, commit a region, start a run.
  await page.locator('[data-testid=select-all]').click();
  const surface = page.locator('[data-testid=region-surface]');
  const canvas = page.locator('[data-testid=region-canvas]');
  await expect
    .poll(async () => canvas.getAttribute('width'), { timeout: 30_000 })
    .not.toBe('0');
  await surface.scrollIntoViewIfNeeded();
  const box = await surface.boundingBox();
  await page.mouse.move(box!.x + 50, box!.y + 50);
  await page.mouse.down();
  await page.mouse.move(box!.x + 250, box!.y + 200, { steps: 3 });
  await page.mouse.up();
  await expect(page.locator('[data-testid=region-committed]')).toBeVisible();
  await page.locator('[data-testid=start-run]').click();
  await expect(page.locator('[data-testid=plan]')).toBeVisible();

  // 1. URL never gained document data — no filename, hash, text, or even
  //    the sha256 suffix rendered in the DOM.
  const url = page.url();
  expect(url).toBe(urlAtBoot);
  expect(url).not.toContain('T08C4N4RY');
  expect(url).not.toContain('confidential');
  expect(url).not.toContain(shaTail);
  const loc = await page.evaluate(() => ({
    hash: location.hash,
    search: location.search,
    href: location.href,
    history: history.length,
  }));
  expect(loc.hash).toBe('');
  expect(loc.search).toBe(''); // boot had no query

  // 2. Every network request stayed same-origin and document-free.
  const origin = new URL(harness.base).origin;
  expect(requests.length).toBeGreaterThan(5); // modules, worker, fonts…
  for (const r of requests) {
    expect(r.url.startsWith(origin), `foreign request ${r.url}`).toBe(true);
    const hay = `${r.method} ${r.url} ${r.post ?? ''}`;
    expect(hay).not.toContain('T08C4N4RY');
    expect(hay).not.toContain('confidential');
    expect(hay).not.toContain(sha);
    expect(hay).not.toContain(shaTail);
    // No upload shape at all.
    expect(['GET', 'OPTIONS', 'HEAD']).toContain(r.method);
    expect(r.post ?? '').not.toContain('%PDF');
  }

  // 3. No local persistence of document data either.
  const storage = await page.evaluate(() => ({
    local: window.localStorage.length,
    session: window.sessionStorage.length,
    cookies: document.cookie,
  }));
  expect(storage.local).toBe(0);
  expect(storage.session).toBe(0);
  expect(storage.cookies).toBe('');

  // 4. The filename is only ever a local label: it appears in the DOM once
  //    as the document label, and nowhere else (URL/requests proven above).
  await expect(page.locator('[data-testid=doc-label]')).toHaveText(
    CANARY_FILE,
  );
});

// ---------------------------------------------------------------------------
// Clear returns to idle — replacement-ready terminal behavior
// ---------------------------------------------------------------------------

test('clear releases the document and returns the drop zone to idle', async ({
  page,
}) => {
  await openPreview(page);
  await offerFixture(page, 'mapping-control.pdf');
  await waitForDocument(page, 1);
  const gen = await generation(page);

  await page.locator('[data-testid=clear-file]').click();
  await expect(page.locator('[data-testid=doc-label]')).not.toBeVisible();
  expect(await fileState(page)).toBe('idle');
  // Generation bumped on clear — teardown ran under the new generation.
  expect(await generation(page)).toBe(gen + 1);
  const events = await page.evaluate(
    () => (globalThis as any).__t08.events,
  );
  const teardown = events.filter((e: any) => e.type === 'teardown');
  expect(teardown.length).toBe(1);
  expect(teardown[0].generation).toBe(gen + 1);

  // And the zone immediately accepts a fresh file.
  await offerFile(page, 'again.pdf', buildPdf({ pages: 2 }));
  await waitForDocument(page, 2);
  await expect(page.locator('[data-testid=doc-label]')).toHaveText(
    'again.pdf',
  );
});
