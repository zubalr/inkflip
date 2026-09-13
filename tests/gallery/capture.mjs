#!/usr/bin/env node
/**
 * T21 gallery capture tool — produces the REAL sealed reports behind the
 * six public example cards.
 *
 * What this does and why it exists:
 *   Every card's prepared report must be an actual recorded run of the
 *   shipped inspection pipeline, never a hand-authored JSON (GLOSSARY:
 *   "a prepared result is an actual recorded run presented without
 *   pretending to execute it again"). This tool rebuilds the production
 *   bundle with the same `vite build` the release uses, serves the real
 *   `dist/` tree over a plain local HTTP server with the deployment CSP,
 *   drives the shipped `/#/workspace` UI in a real Chromium through
 *   `setInputFiles` -> `start-run`, and stores the sealed `Report` object
 *   the session assembled and validated in-page. No reader is mocked,
 *   no output is edited after the fact; each written file is byte-verbatim
 *   what `assembleReport()` sealed.
 *
 * Usage:
 *   node tests/gallery/capture.mjs            # capture all specs
 *   node tests/gallery/capture.mjs --only=amount   # one card
 *
 * The reports are committed inputs to scripts/prepare_examples.py, which
 * derives the per-card manifests and the gallery index from them. A
 * re-capture refreshes the volatile run envelope (execution id, started_at,
 * duration) — report_id (the content seal) and run_key stay stable because
 * seal() excludes those envelope fields by contract.
 */
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(here, "../..");
const WEB = join(ROOT, "apps/web");
const FIX = join(ROOT, "fixtures");
const EXAMPLES = join(WEB, "public", "examples");

/* ------------------------------------------------------------------ */
/* Capture matrix: one entry per presented asset.                      */
/* `region` is an explicit canonical-space user selection (top-left    */
/* origin, physical points) — a declared input, never an inferred one. */
/* ------------------------------------------------------------------ */
const CAPTURES = [
  // Card 1 — F01 mapping-amount: ToUnicode one-to-many mapping.
  // Region is the proven T17 canonical crop ([40,122,200,195] pt on the
  // 520x400 page) — a declared user selection, never an inferred one.
  {
    card: "amount",
    fixture: "public/mapping-amount.pdf",
    out: "report.json",
    region: [40, 122, 200, 195],
    regionLabel: "Amount token crop",
  },
  {
    card: "amount",
    fixture: "public/mapping-control.pdf",
    out: "report.control.json",
  },
  // F14 native-unicode detail controls presented on the amount card:
  // Identity-H hex strings carrying the same Latin "$100" mechanism.
  {
    card: "amount",
    fixture: "development/native-unicode-native.pdf",
    out: "report.native-unicode-native.json",
  },
  {
    card: "amount",
    fixture: "development/native-unicode-control.pdf",
    out: "report.native-unicode-control.json",
  },
  // Card 2 — F02 covered-text: covered-then-replaced amount.
  {
    card: "covered",
    fixture: "public/covered-amount.pdf",
    out: "report.json",
    region: [40, 122, 200, 195],
    regionLabel: "Amount token crop",
  },
  {
    card: "covered",
    fixture: "public/covered-control.pdf",
    out: "report.control.json",
  },
  // F04 white-contrast detail controls presented on the covered card.
  {
    card: "covered",
    fixture: "development/white-contrast-white.pdf",
    out: "report.white-contrast-white.json",
  },
  {
    card: "covered",
    fixture: "development/white-contrast-control.pdf",
    out: "report.white-contrast-control.json",
  },
  // Card 3 — F03 searchable-scan: correct invisible layer + siblings.
  {
    card: "scan",
    fixture: "development/scan-correct.pdf",
    out: "report.json",
  },
  {
    card: "scan",
    fixture: "development/scan-raster-only.pdf",
    out: "report.scan-raster-only.json",
  },
  {
    card: "scan",
    fixture: "development/scan-shifted.pdf",
    out: "report.scan-shifted.json",
  },
  // Card 4 — F07 origins-rotation: all four rotations + clean control.
  // All five runs share the same declared selection ([30,230,300,380]
  // canonical pt around the painted $100) so the reports are directly
  // comparable across rotations AND stay inside the report contract's
  // per-finding occurrence bound — full-page OCR of the rotated pages
  // emits 50-60 ambiguous tokens, which sealed reports record verbatim
  // but which would overflow Finding.occurrence_ids (maxItems 32) and
  // make the prepared evidence impossible to re-import. The region is
  // an explicit user input, recorded in plan.regions; it is never
  // presented as an inferred or automatic crop.
  {
    card: "geometry",
    fixture: "public/geometry-90.pdf",
    out: "report.json",
    region: [30, 230, 300, 380],
    regionLabel: "Amount area crop",
  },
  {
    card: "geometry",
    fixture: "public/geometry-0.pdf",
    out: "report.geometry-0.json",
    region: [30, 230, 300, 380],
    regionLabel: "Amount area crop",
  },
  {
    card: "geometry",
    fixture: "public/geometry-180.pdf",
    out: "report.geometry-180.json",
    region: [30, 230, 300, 380],
    regionLabel: "Amount area crop",
  },
  {
    card: "geometry",
    fixture: "public/geometry-270.pdf",
    out: "report.geometry-270.json",
    region: [30, 230, 300, 380],
    regionLabel: "Amount area crop",
  },
  {
    card: "geometry",
    fixture: "public/geometry-control.pdf",
    out: "report.control.json",
    region: [30, 230, 300, 380],
    regionLabel: "Amount area crop",
  },
  // Card 5 — F12 reading-order: reordered stream vs ordered control.
  {
    card: "reading-order",
    fixture: "public/reading-order-reordered.pdf",
    out: "report.json",
  },
  {
    card: "reading-order",
    fixture: "public/reading-order-control.pdf",
    out: "report.control.json",
  },
  // Card 6 — F11 duplicates + F15 damaged-raster sibling: repeated
  // identical strings plus one lightly damaged raster region whose OCR
  // ambiguity is left unresolved. The bounded region on the source
  // selects the TOP-LEFT $100 only (pdf Tm 48,180 on the 320x240pt page
  // -> canonical ~x 48..110, y ~48..62; the region [30,20,130,75]
  // contains it fully and excludes the other three occurrences).
  {
    card: "duplicates",
    fixture: "development/duplicates-four.pdf",
    out: "report.json",
    region: [30, 20, 130, 75],
    regionLabel: "First amount only",
  },
  {
    card: "duplicates",
    fixture: "development/duplicates-control.pdf",
    out: "report.control.json",
  },
  {
    card: "duplicates",
    fixture: "development/ocr-material-sign-ambiguity.pdf",
    out: "report.ocr-material-sign-ambiguity.json",
  },
  {
    card: "duplicates",
    fixture: "development/ocr-material-control.pdf",
    out: "report.ocr-material-control.json",
  },
];

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css",
  ".json": "application/json",
  ".pdf": "application/pdf",
  ".wasm": "application/wasm",
  ".bcmap": "application/octet-stream",
  ".traineddata": "application/octet-stream",
  ".pfb": "application/octet-stream",
  ".ttf": "font/ttf",
  ".icc": "application/vnd.iccprofile",
  ".png": "image/png",
};

const SECURITY_HEADERS = {
  "Content-Security-Policy":
    "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; " +
    "worker-src 'self'; connect-src 'self'; img-src 'self' blob: data:; " +
    "font-src 'self' blob:; style-src 'self'; style-src-attr 'unsafe-inline'; " +
    "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'; " +
    "frame-ancestors 'none'; manifest-src 'self'",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "Cross-Origin-Resource-Policy": "same-origin",
};

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

async function main() {
  const only = process.argv.find((a) => a.startsWith("--only="))?.slice(7) ?? null;
  const specs = CAPTURES.filter((c) => only === null || c.card === only);
  if (specs.length === 0) {
    console.error(`no captures matched --only=${only ?? "(none)"}`);
    process.exit(1);
  }

  /* ---- 1. Build the real app (same pinned vite build as the release) ---- */
  const DIST = mkdtempSync(join(tmpdir(), "inkflip-t21-dist-"));
  const viteEntry = pathToFileURL(
    join(WEB, "node_modules", "vite", "dist", "node", "index.js"),
  ).href;
  const vite = await import(viteEntry);
  // The __inspect read-only session handle exists only under this build
  // opt-in; shipped builds omit it (same switch the G1 gate uses).
  process.env.INKFLIP_TEST_HOOKS = "1";
  console.log(`[capture] building ${WEB} -> ${DIST}`);
  await vite.build({
    root: WEB,
    configFile: join(WEB, "vite.config.ts"),
    logLevel: "warn",
    build: {
      outDir: DIST,
      emptyOutDir: true,
      rollupOptions: { input: { index: join(WEB, "index.html") } },
    },
  });

  /* ---- 2. Serve the real dist tree over plain local HTTP ---- */
  const distRoot = resolve(DIST) + sep;
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://static.invalid");
    let pathname = decodeURIComponent(url.pathname);
    if (pathname === "/") pathname = "/index.html";
    const headers = { ...SECURITY_HEADERS, "Cache-Control": "no-cache" };
    if (pathname === "/favicon.ico") {
      res.writeHead(204, headers).end();
      return;
    }
    const file = normalize(join(DIST, pathname));
    if (!file.startsWith(distRoot) || !existsSync(file) || file.endsWith(sep)) {
      res.writeHead(404, headers).end("not found");
      return;
    }
    let body;
    try {
      body = readFileSync(file);
    } catch {
      res.writeHead(404, headers).end("not found");
      return;
    }
    res
      .writeHead(200, { ...headers, "Content-Type": MIME[file.slice(file.lastIndexOf("."))] ?? "application/octet-stream" })
      .end(body);
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const baseURL = `http://127.0.0.1:${server.address().port}`;
  console.log(`[capture] serving dist at ${baseURL}`);

  const { chromium } = await import("@playwright/test");
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on("pageerror", (e) => console.error(`[pageerror] ${e}`));

  const written = [];
  try {
    /* Land on the workspace's empty state through the real app shell. */
    await page.goto(baseURL);
    await page.locator("#btn-open-report").click();
    await page.waitForFunction(
      () => globalThis.__inspect !== undefined,
      undefined,
      { timeout: 30_000 },
    );

    for (const spec of specs) {
      const pdfBytes = readFileSync(join(FIX, spec.fixture));
      const expectedSha = sha256(pdfBytes);
      const name = spec.fixture.split("/").pop();
      const t0 = Date.now();

      await page
        .locator("#input-open-pdf")
        .setInputFiles({ name, mimeType: "application/pdf", buffer: pdfBytes });
      // A still-occupied session asks for confirmed replacement — answer it.
      const dlg = page.locator("[role=dialog]");
      if (await dlg.isVisible().catch(() => false)) {
        await dlg.getByRole("button", { name: "Clear and open file" }).click();
      }
      await page.waitForFunction(
        (expected) => {
          const s = globalThis.__inspect?.getState();
          return s?.doc?.sha256 === expected;
        },
        expectedSha,
        { timeout: 30_000 },
      );

      if (spec.region) {
        await page
          .locator("[data-testid=region-x0]")
          .waitFor({ state: "visible", timeout: 60_000 });
        const [x0, y0, x1, y1] = spec.region;
        await page.locator("[data-testid=region-x0]").fill(String(x0));
        await page.locator("[data-testid=region-y0]").fill(String(y0));
        await page.locator("[data-testid=region-x1]").fill(String(x1));
        await page.locator("[data-testid=region-y1]").fill(String(y1));
        if (spec.regionLabel) {
          const label = page.locator("[data-testid=region-label]");
          if (await label.isVisible().catch(() => false)) {
            await label.fill(spec.regionLabel);
          }
        }
        await page.locator("[data-testid=region-apply]").click();
        await page
          .locator("[data-testid=region-committed]")
          .waitFor({ state: "visible", timeout: 15_000 });
      }

      await page.locator("[data-testid=start-run]").click();
      const report = await page.waitForFunction(
        () => {
          const s = globalThis.__inspect?.getState();
          if (s?.report !== null && s?.reportSource === "run") return s.report;
          if (
            ["complete", "partial", "failed", "cancelled"].includes(s?.fileState) &&
            s?.error
          ) {
            throw new Error(
              `run settled without a report: ${s.error.message} — ${s.error.detail ?? ""}`,
            );
          }
          return false;
        },
        undefined,
        { timeout: 240_000, polling: 500 },
      ).then((h) => h.jsonValue());

      // Defensive re-verification before anything is committed: the sealed
      // document identity must equal the bytes we just offered.
      if (report?.document?.sha256 !== expectedSha) {
        throw new Error(
          `sealed report sha256 ${report?.document?.sha256} != offered ${expectedSha} for ${spec.fixture}`,
        );
      }

      const dir = join(EXAMPLES, spec.card);
      mkdirSync(dir, { recursive: true });
      const dest = join(dir, spec.out);
      writeFileSync(dest, JSON.stringify(report, null, 2) + "\n");
      const ms = Date.now() - t0;
      const checks = (report.checks ?? []).map((c) => `${c.id}:${c.status}`).join(", ");
      console.log(
        `[capture] ${spec.card}/${spec.out} <- ${spec.fixture} ` +
          `(${report.occurrences?.length ?? 0} occurrences, ${report.findings?.length ?? 0} findings, ` +
          `report_id ${report.report_id?.slice(0, 16)}…, ${ms}ms) checks: ${checks}`,
      );
      written.push({ card: spec.card, out: spec.out, fixture: spec.fixture, report_id: report.report_id, run_key: report.execution?.run_key });

      // Return to the empty workspace for the next specimen.
      const closeBtn = page.locator("#btn-close-doc");
      if (await closeBtn.isVisible().catch(() => false)) {
        await closeBtn.click();
        await page.waitForFunction(
          () => {
            const s = globalThis.__inspect?.getState();
            return s?.fileState === "idle" && s?.doc === null && s?.report === null;
          },
          undefined,
          { timeout: 15_000 },
        );
      }
    }
  } finally {
    await browser.close();
    await new Promise((r) => server.close(r));
    rmSync(DIST, { recursive: true, force: true });
  }

  console.log(`[capture] wrote ${written.length} sealed reports under apps/web/public/examples/`);
}

await main();
