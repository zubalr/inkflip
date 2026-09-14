import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect, type Page } from "@playwright/test";

/**
 * TEST-20: Repeated, ambiguous, order and unmatched evidence UX (T20).
 *
 * Acceptance criteria:
 * 1. Four repeated amounts never jump to first string match.
 * 2. order-only differences remain order-only.
 * 3. incomplete extraction cannot be claimed missing visible text.
 * 4. keyboard selection returns to originating finding.
 *
 * Drives the real public workspace (/#/workspace) through a Vite dev
 * server. Real-PDF legs run the genuine pdf.js + Tesseract + alignment
 * pipeline; the bundled example document exercises ambiguous candidate
 * navigation deterministically.
 */

const WEB_ROOT = path.resolve(process.cwd(), "apps/web");

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
// Minimal PDF builder — real xref tables, positioned text spans.
// spans are emitted in stream order; pdf.js ordinals follow that order.
// ---------------------------------------------------------------------------

interface Span {
  text: string;
  x: number;
  y: number;
  size?: number;
}

function buildPdf(spans: Span[]): Uint8Array {
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
  const stream = spans
    .map((s) => `BT /F1 ${s.size ?? 24} Tf ${s.x} ${s.y} Td (${s.text}) Tj ET`)
    .join("\n");
  push("%PDF-1.4\n");
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  obj(2, "<< /Type /Pages /Kids [5 0 R] /Count 1 >>");
  obj(3, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  obj(4, `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
  obj(
    5,
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " +
      "/Resources << /Font << /F1 3 0 R >> >> /Contents 4 0 R >>",
  );
  const xrefPos = len;
  let xref = "xref\n0 6\n0000000000 65535 f \n";
  for (let i = 1; i < 6; i++) {
    xref += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  push(xref);
  push(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`);
  const out = new Uint8Array(len);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

const REPEATED_PDF = buildPdf([
  { text: "$1,000.00", x: 100, y: 700 },
  { text: "$1,000.00", x: 100, y: 620 },
  { text: "$1,000.00", x: 100, y: 540 },
  { text: "$1,000.00", x: 100, y: 460 },
]);

const ORDER_PDF = buildPdf([
  // Emitted right-column-first in the stream; rendered order is left-first.
  { text: "RIGHTCOL", x: 400, y: 700 },
  { text: "LEFTCOL", x: 72, y: 700 },
  { text: "SECOND-ROW", x: 72, y: 650 },
]);

const TINY_PDF = buildPdf([
  { text: "NORMAL LINE", x: 72, y: 700 },
  { text: "tiny", x: 72, y: 600, size: 1 },
]);

async function openAndRun(page: Page, bytes: Uint8Array, name: string) {
  await page
    .locator('[data-testid="file-input"]')
    .setInputFiles({ name, mimeType: "application/pdf", buffer: Buffer.from(bytes) });
  await page.waitForSelector('[data-testid="pages-summary"]');
  await page.locator('[data-testid="start-run"]').click();
  await page.waitForSelector("#viewer-stage", { timeout: 120_000 });
}

// ---------------------------------------------------------------------------

test("repeated identical amounts stay individually addressable — never first string match", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${baseUrl}/#/workspace`);
  await openAndRun(page, REPEATED_PDF, "repeated.pdf");

  // The text equivalent lists every identical string as a distinct
  // occurrence with its own ordinal — nothing is collapsed by text.
  const items = page.locator("#accessible-text-equivalent li", {
    hasText: "$1,000.00",
  });
  expect(await items.count()).toBeGreaterThanOrEqual(4);

  // Occurrence ids come from the li element ids (text-occ-{id}).
  const ids = await items.evaluateAll((els) => els.map((el) => el.id.replace(/^text-occ-/, "")));
  expect(new Set(ids).size).toBe(ids.length);

  // Selecting occurrence #3 by its own control highlights #3 — and not
  // the first identical string. Selection is identity-addressed.
  const third = ids[2];
  await page.locator(`#text-occ-${third} button`).click();
  await expect(page.locator(`#highlight-${third}`)).toHaveClass(/highlightSelected/);
  const first = ids[0];
  if (first !== third) {
    await expect(page.locator(`#highlight-${first}`)).not.toHaveClass(/highlightSelected/);
  }
});

test("ambiguous finding exposes every candidate and pre-picks none", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  // The bundled example document carries a deterministic ambiguous
  // finding naming three occurrences — two of them identical strings.
  // Deterministic synthetic fixture kept for occurrence-identity assertions.
  await page.goto(`${baseUrl}/#/workspace?example=fixture`);
  await page.waitForSelector("#viewer-stage");

  await page.locator("#finding-item-finding-ambig-amounts").click();

  const detail = page.locator('[data-testid="alignment-detail"]');
  await expect(detail).toHaveAttribute("data-alignment-class", "ambiguous");

  // All three named occurrences are navigable candidates.
  for (const id of ["occ-p0-dup1", "occ-p0-dup2", "occ-p0-pypdf1"]) {
    await expect(page.locator(`[data-testid="occ-candidate-${id}"]`)).toBeVisible();
  }
  // The identical strings are labeled as distinct positions, and no
  // candidate arrives pre-selected — never first-match-wins.
  await expect(page.locator('[data-testid="occ-identical-occ-p0-dup1"]')).toContainText(
    "identical text",
  );
  await expect(page.locator('[data-candidate-id][aria-pressed="true"]')).toHaveCount(0);

  // Pointer selection: clicking a candidate inside the card must stick —
  // the card's own click handler must not wipe the chosen occurrence.
  const dup2 = page.locator('[data-testid="occ-candidate-occ-p0-dup2"]');
  await dup2.click();
  await expect(dup2).toHaveAttribute("aria-pressed", "true");
  // The chosen occurrence is the selection; the other named candidates
  // stay marked as candidates, not as if the engine had picked them.
  await expect(page.locator("#highlight-occ-p0-dup2")).toHaveClass(/highlightSelected/);
  await expect(page.locator("#highlight-occ-p0-dup1")).not.toHaveClass(/highlightSelected/);
  // Clicking elsewhere in the expanded detail does not discard the pick.
  await page.locator('[data-testid="alignment-body"]').click();
  await expect(dup2).toHaveAttribute("aria-pressed", "true");
});

test("order-only differences remain order-only", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${baseUrl}/#/workspace`);
  await openAndRun(page, ORDER_PDF, "order.pdf");

  // The real pipeline records an order difference — never a text one.
  const orderCard = page.locator('[id^="finding-item-"]', {
    hasText: "different emitted order",
  });
  await expect(orderCard.first()).toBeVisible();
  await orderCard.first().click();

  const detail = page.locator('[data-testid="alignment-detail"]').first();
  await expect(detail).toHaveAttribute("data-alignment-class", "order_only");
  await expect(detail.locator('[data-testid="alignment-body"]')).toContainText(
    "not a text difference",
  );
  // Order-only candidates are listed but none is pre-picked either.
  await expect(detail.locator('[data-candidate-id][aria-pressed="true"]')).toHaveCount(0);

  // No content-difference finding claims the same readings differ.
  const page_text = await page.locator("#viewer-stage").textContent();
  expect(page_text).not.toContain("These readings differ here");
  expect(page_text).not.toContain("This amount reads differently");
});

test("unmatched readings are never claimed as missing visible text", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${baseUrl}/#/workspace`);
  await openAndRun(page, TINY_PDF, "tiny.pdf");

  // The 1pt string is real text-layer evidence OCR cannot see — the
  // finding names it without claiming the document lacks text.
  const card = page.locator('[id^="finding-item-"]', {
    hasText: "No matching reading found here",
  });
  await expect(card.first()).toBeVisible();
  await card.first().click();

  const detail = page.locator('[data-testid="alignment-detail"]').first();
  await expect(detail).toHaveAttribute("data-alignment-class", "unmatched");
  await expect(detail.locator('[data-testid="alignment-body"]')).toContainText(
    "not proof of missing document text",
  );

  // The forbidden verdict phrasing never appears anywhere.
  const all = await page.locator("#viewer-stage").textContent();
  expect(all).not.toContain("missing from the document");
  expect(all).not.toContain("Text is missing");
});

test("keyboard selection returns focus to the originating finding", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${baseUrl}/#/workspace?example=fixture`);
  await page.waitForSelector("#viewer-stage");

  const card = page.locator("#finding-item-finding-ambig-amounts");
  await card.focus();
  await card.press("Enter");

  // The candidate list is inside the expanded finding; focus a candidate
  // by keyboard and choose it — focus must return to the finding card.
  const candidate = page.locator('[data-testid="occ-candidate-occ-p0-dup2"]');
  await candidate.focus();
  await candidate.press("Enter");
  await expect(page.locator(":focus")).toHaveId("finding-item-finding-ambig-amounts");
  await expect(candidate).toHaveAttribute("aria-pressed", "true");

  // Escape also returns focus without requiring a new selection.
  const other = page.locator('[data-testid="occ-candidate-occ-p0-pypdf1"]');
  await other.focus();
  await other.press("Escape");
  await expect(page.locator(":focus")).toHaveId("finding-item-finding-ambig-amounts");
});
