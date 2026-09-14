/**
 * T22 — Strict local JSON import and reopen flow: real Chromium coverage.
 *
 * The suite boots the REAL app path: Vite serves
 * `apps/web/src/features/import/preview.html`, which mounts the import
 * feature wired to the T11 RunCoordinator (generation-first lifecycle),
 * the T24 import gate through `packages/reports/import`, and the T09
 * pdf.js adapter as the installed-reader allowlist. Reports are offered
 * through real <input type="file"> elements; exports are produced
 * in-page by the real T16 `projectReport`/`serializeReportJson`
 * pipeline — nothing is mocked at the contract surface.
 *
 * Acceptance criteria coverage (exact strings from the T22 contract):
 *
 * - "Real selected export reopens without upload"
 *   A real `projectReport` selection export is serialized canonically
 *   and reopened through the file input: scope/included/omissions,
 *   coverage counts, readers, findings, cited occurrences and the
 *   sanitized crop render. Every request stays same-origin GET; no
 *   report text, id or document hash appears in URL/storage/payloads.
 * - "source omission and unavailable reader explicit"
 *   The evidence export shows the source-missing state, the verbatim
 *   copy, the explicit local chooser and the named unavailable readers;
 *   a replayable export shows the embedded source plus the recorded-
 *   environment requirement.
 * - "malicious report cannot fetch/execute/select profile"
 *   A hostile corpus (archive/container magics, markup, UTF-16,
 *   malformed/deep/duplicate/nonfinite JSON, prototype keys, executable/
 *   profile/external-pointer fields, wrong artifact kinds, oversized
 *   strings/assets) is rejected inside the gate; a valid report carrying
 *   markup/URL/script-shaped strings renders them as inert text. Egress
 *   tripwires and DOM markers prove nothing fetched or executed.
 * - "hash mismatch blocks replay"
 *   A delivered tampered-digest example and a mutated asset hash are
   rejected at the gate; mismatched source bytes are refused before any
 *   attachment, so replay never becomes possible on wrong bytes.
 * - "comparison asks for exact locally selected source reports"
 *   The compare panel takes only explicit local file selections; two
 *   same-document reports are ready, identical reports are called out,
 *   different-document reports are incomparable, and a rejected side
 *   shows its own failure — no ids, URLs or remote pointers accepted.
 *
 * Fixture honesty: F24/F25/F26 (overlap-ink, annotation-mode, asset-
 * cache family) are specified-not-generated in this branch; their
 * import semantics are exercised through constructed report variants
 * (reader substitution, hostile strings, annotations opt-in) built on
 * the real delivered example reports.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const WEB = join(ROOT, "apps", "web");
const FIXTURE_PUBLIC = join(ROOT, "fixtures", "public");
const EXAMPLES_VALID = join(ROOT, "planning", "contracts", "examples", "valid");
const EXAMPLES_INVALID = join(ROOT, "planning", "contracts", "examples", "invalid");
const PREVIEW = "/src/features/import/preview.html";

const NATIVE_EVIDENCE = JSON.parse(
  readFileSync(join(EXAMPLES_VALID, "native-evidence.inkflip.json"), "utf8"),
);
const NATIVE_REPLAY = readFileSync(join(EXAMPLES_VALID, "native-replay.inkflip.json"));
const COMPARISON_ARTIFACT = readFileSync(join(EXAMPLES_VALID, "comparison.json"));
const TAMPERED_REPORT = readFileSync(join(EXAMPLES_INVALID, "tampered-report-hash.json"));
const SOURCE_PDF = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
const WRONG_PDF = readFileSync(join(FIXTURE_PUBLIC, "mapping-control.pdf"));

const DOC_SHA = "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80";
const MAX_JSON_BYTES = 32 * 1024 * 1024;

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
    join(WEB, "node_modules", "vite", "dist", "node", "index.js"),
  ).href;
  const { createServer } = (await import(viteEntry)) as {
    createServer: (opts: { root: string; server: { port: number }; logLevel: string }) => Promise<{
      listen: () => Promise<void>;
      resolvedUrls: { local: string[] };
      close: () => Promise<void>;
    }>;
  };
  const server = await createServer({
    root: WEB,
    server: { port: 0 },
    logLevel: "warn",
  });
  await server.listen();
  const base = server.resolvedUrls.local[0].replace(/\/$/, "");
  harness = { base, close: () => server.close() };
});

test.afterAll(async () => {
  await harness.close();
});

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => {
    console.log(`[pageerror] ${error}`);
  });
});

test.setTimeout(120_000);

/**
 * Arm egress tripwires BEFORE any app script runs: every fetch, XHR,
 * beacon, WebSocket, EventSource and window.open attempt is recorded in
 * `window.__egress`. Vite's own HMR WebSocket is expected (same origin);
 * everything else must stay empty.
 */
async function armEgress(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as {
      __egress: string[];
      fetch: unknown;
      WebSocket: unknown;
      EventSource: unknown;
      XMLHttpRequest: unknown;
      navigator: { sendBeacon?: unknown };
      open: unknown;
    };
    w.__egress = [];
    const record = (kind: string, target: unknown) => {
      w.__egress.push(`${kind}:${String(target)}`);
    };
    const NativeWebSocket = window.WebSocket;
    // @ts-expect-error tripwire wrapper
    window.WebSocket = class extends NativeWebSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        record("websocket", url);
        super(url, protocols);
      }
    };
    if (typeof window.EventSource === "function") {
      const NativeEventSource = window.EventSource;
      // @ts-expect-error tripwire wrapper
      window.EventSource = class extends NativeEventSource {
        constructor(url: string | URL) {
          record("eventsource", url);
          super(url);
        }
      };
    }
    const nativeFetch = window.fetch?.bind(window);
    window.fetch = ((input: unknown, init?: unknown) => {
      record("fetch", typeof input === "string" ? input : (input as Request)?.url);
      return (nativeFetch as (i: unknown, n?: unknown) => Promise<Response>)(input, init);
    }) as typeof fetch;
    const nativeOpen = window.XMLHttpRequest.prototype.open;
    window.XMLHttpRequest.prototype.open = function (
      this: XMLHttpRequest,
      method: string,
      url: string | URL,
    ) {
      record("xhr", url);
      // @ts-expect-error passthrough with original arity
      return nativeOpen.apply(this, arguments);
    };
    const nativeBeacon = window.navigator.sendBeacon?.bind(window.navigator);
    if (nativeBeacon) {
      window.navigator.sendBeacon = ((url: string, data?: unknown) => {
        record("beacon", url);
        return (nativeBeacon as (u: string, d?: unknown) => boolean)(url, data);
      }) as typeof navigator.sendBeacon;
    }
    const nativeWindowOpen = window.open?.bind(window);
    window.open = ((url?: unknown) => {
      record("window.open", url);
      return nativeWindowOpen ? nativeWindowOpen(url as string) : null;
    }) as typeof window.open;
  });
}

async function openPreview(page: Page): Promise<void> {
  await page.goto(`${harness.base}${PREVIEW}`);
  await page.waitForFunction(
    () => (globalThis as { __t22?: unknown }).__t22 !== undefined,
    undefined,
    { timeout: 30_000 },
  );
  await expect(page.locator("[data-testid=import-drop]")).toBeVisible();
}

/** Produce a real canonical export in-page via the T16 engine. */
async function makeExport(
  page: Page,
  request: Record<string, unknown> = {},
  source: Record<string, unknown> = NATIVE_EVIDENCE,
): Promise<string> {
  return page.evaluate(
    async ({ src, req }) => {
      const t = (globalThis as any).__t22;
      const clone = JSON.parse(JSON.stringify(src));
      const { report } = t.exportEngine.projectReport(clone, req);
      return t.exportEngine.serializeReportJson(report);
    },
    { src: source, req: request },
  );
}

/** Replayable export: embed the real original bytes (supplied as array). */
async function makeReplayableExport(page: Page, sourceBytes: Uint8Array): Promise<string> {
  return page.evaluate(
    async ({ src, pdf }) => {
      const t = (globalThis as any).__t22;
      const clone = JSON.parse(JSON.stringify(src));
      const { report } = t.exportEngine.projectReport(clone, {
        sourcePdf: new Uint8Array(pdf),
      });
      return t.exportEngine.serializeReportJson(report);
    },
    { src: NATIVE_EVIDENCE, pdf: Array.from(sourceBytes) },
  );
}

/**
 * Reader-substitution variant: the delivered report's native readers are
 * replaced by the browser's installed pdf.js reader records and every
 * `reader_id`/`reader_ids` reference is remapped before resealing —
 * exercises the installed-reader path on real contract data.
 */
async function makeBrowserReaderExport(page: Page): Promise<string> {
  return page.evaluate(async (src) => {
    const t = (globalThis as any).__t22;
    const rep = JSON.parse(JSON.stringify(src));
    const [text, render] = t.installed;
    rep.readers = [text, render];
    const map: Record<string, string> = {
      r_pdfium: text.id,
      r_tesseract: render.id,
    };
    for (const o of rep.occurrences) {
      o.reader_id = map[o.reader_id] ?? o.reader_id;
    }
    for (const c of rep.plan.checks) {
      c.reader_ids = c.reader_ids.map((id: string) => map[id] ?? id);
    }
    t.contracts.seal(rep);
    const { report } = t.exportEngine.projectReport(rep, {});
    return t.exportEngine.serializeReportJson(report);
  }, NATIVE_EVIDENCE);
}

async function offerReport(page: Page, name: string, json: string | Buffer): Promise<void> {
  await page.locator("[data-testid=import-file-input]").setInputFiles({
    name,
    mimeType: "application/json",
    buffer: typeof json === "string" ? Buffer.from(json, "utf8") : json,
  });
}

async function offerSourceFile(page: Page, bytes: Buffer): Promise<void> {
  await page.locator("[data-testid=source-file-input]").setInputFiles({
    name: "chosen.pdf",
    mimeType: "application/pdf",
    buffer: bytes,
  });
}

async function offerCompareSide(
  page: Page,
  side: "left" | "right",
  json: string | Buffer,
): Promise<void> {
  await page.locator(`[data-testid=compare-input-${side}]`).setInputFiles({
    name: `${side}.inkflip.json`,
    mimeType: "application/json",
    buffer: typeof json === "string" ? Buffer.from(json, "utf8") : json,
  });
}

async function fileState(page: Page): Promise<string> {
  return page.evaluate(() => (globalThis as any).__t22.coordinator.fileState);
}

async function generation(page: Page): Promise<number> {
  return page.evaluate(() => (globalThis as any).__t22.coordinator.currentGeneration);
}

async function events(page: Page): Promise<Array<Record<string, unknown>>> {
  return page.evaluate(() => (globalThis as any).__t22.events);
}

async function egress(page: Page): Promise<string[]> {
  return page.evaluate(() => (globalThis as unknown as { __egress: string[] }).__egress ?? []);
}

// ---------------------------------------------------------------------------
// 1. Real selected export reopens without upload
// ---------------------------------------------------------------------------

test("a real selected export reopens locally — no upload, scope/omissions shown", async ({
  page,
}) => {
  const requests: Array<{ url: string; method: string; post: string | null }> = [];
  page.on("request", (req) => {
    requests.push({ url: req.url(), method: req.method(), post: req.postData() });
  });
  await armEgress(page);
  await openPreview(page);
  const urlAtBoot = page.url();

  // Real selected export through the real T16 engine.
  const json = await makeExport(page, { annotations: true });
  expect(json.endsWith("\n")).toBe(true);
  const reportId = JSON.parse(json).report_id as string;

  await offerReport(page, "selected.inkflip.json", json);
  await expect(page.locator("[data-testid=import-report]")).toBeVisible({
    timeout: 30_000,
  });

  // Workspace bound to the recorded document identity.
  expect(await fileState(page)).toBe("selecting");
  await expect(page.locator("[data-testid=report-title]")).toHaveText("Imported report");
  await expect(page.locator("[data-testid=report-id]")).toContainText(reportId.slice(0, 16));
  await expect(page.locator("[data-testid=report-id]")).toContainText(DOC_SHA.slice(-12));

  // Scope disclosure verbatim: included categories + omissions.
  const included = page.locator("[data-testid=scope-included]");
  await expect(included).toContainText("selected_text");
  await expect(included).toContainText("crops");
  await expect(included).toContainText("document_hash");
  const omissions = page.locator("[data-testid=scope-omissions]");
  await expect(omissions).toContainText("Original PDF excluded.");
  await expect(omissions).toContainText("Filename excluded.");
  await expect(page.locator("[data-testid=report-scope]")).toContainText("evidence");

  // Coverage counts reflect the recorded checks exactly.
  await expect(page.locator("[data-testid=coverage-checks]")).toHaveText("3");
  await expect(page.locator("[data-testid=coverage-completed]")).toHaveText("2");
  await expect(page.locator("[data-testid=coverage-unsupported]")).toHaveText("1");
  await expect(page.locator("[data-testid=coverage-produced]")).toHaveText("119");
  await expect(page.locator("[data-testid=coverage-retained]")).toHaveText("2");
  await expect(page.locator("[data-testid=coverage-pages]")).toHaveText("1 of 1");

  // Findings and cited occurrences render the recorded raw text.
  await expect(page.locator("[data-testid=finding-f_amount]")).toContainText(
    "Two readings of the selected region differ",
  );
  await expect(page.locator("[data-testid=occurrence-raw-o_pdfium_amount]")).toHaveText("$1,000");
  await expect(page.locator("[data-testid=occurrence-raw-o_tess_amount]")).toHaveText("$100");

  // The crop renders from the sanitized re-encode — a data: URL, never a
  // remote or report-supplied one.
  const cropSrc = await page.locator("[data-testid=asset-img-a_crop]").getAttribute("src");
  expect(cropSrc?.startsWith("data:image/png;base64,")).toBe(true);

  // Limitations visible.
  await expect(page.locator("[data-testid=report-limitations]")).toContainText(
    "Original bytes are required for replay",
  );

  // --- No upload / no egress -------------------------------------------
  expect(page.url()).toBe(urlAtBoot);
  const origin = new URL(harness.base).origin;
  expect(requests.length).toBeGreaterThan(3);
  for (const r of requests) {
    expect(r.url.startsWith(origin), `foreign request ${r.url}`).toBe(true);
    expect(["GET", "OPTIONS", "HEAD"]).toContain(r.method);
    const hay = `${r.url} ${r.post ?? ""}`;
    expect(hay).not.toContain(reportId);
    expect(hay).not.toContain(DOC_SHA);
    expect(hay).not.toContain("1,000");
  }
  // No egress attempts beyond the same-origin Vite HMR socket.
  for (const entry of await egress(page)) {
    expect(entry.startsWith("websocket:ws://localhost")).toBe(true);
  }
  const storage = await page.evaluate(() => ({
    local: window.localStorage.length,
    session: window.sessionStorage.length,
    cookies: document.cookie,
  }));
  expect(storage.local).toBe(0);
  expect(storage.session).toBe(0);
  expect(storage.cookies).toBe("");
});

// ---------------------------------------------------------------------------
// 2. Source omission and unavailable reader are explicit
// ---------------------------------------------------------------------------

test("evidence export: missing source, chooser and unavailable readers are explicit", async ({
  page,
}) => {
  await openPreview(page);
  await offerReport(page, "evidence.inkflip.json", await makeExport(page));
  await expect(page.locator("[data-testid=import-report]")).toBeVisible();

  // Source omission is an explicit state, never a silent gap.
  await expect(page.locator("[data-testid=source-missing]")).toHaveText(
    "The original PDF is not included. The saved evidence is still available.",
  );
  await expect(page.locator("[data-testid=source-file-input]")).toBeAttached();
  await expect(page.locator("[data-testid=source-nofetch]")).toHaveText(
    "Reports never fetch missing files or install readers automatically.",
  );

  // Replay is inspectable-not-runnable with the verbatim copy.
  await expect(page.locator("[data-testid=replay-state]")).toHaveText(
    "Original PDF not included. This report can be inspected, but replay requires the matching original.",
  );

  // Both recorded native readers are named unavailable — never silently
  // substituted by the installed pdf.js readers.
  await expect(page.locator("[data-testid=reader-r_pdfium]")).toContainText(
    "PDFium via pypdfium2 5.8.0",
  );
  await expect(page.locator("[data-testid=reader-missing-r_pdfium]")).toHaveText("unavailable");
  await expect(page.locator("[data-testid=reader-missing-r_tesseract]")).toHaveText("unavailable");
  const missing = page.locator("[data-testid=replay-missing-readers]");
  await expect(missing).toContainText("PDFium via pypdfium2 5.8.0");
  await expect(missing).toContainText("Tesseract 5.5.0");
  await expect(page.locator("[data-testid=replay-ready]")).toHaveCount(0);
});

test("replayable export shows embedded source and the environment requirement", async ({
  page,
}) => {
  await openPreview(page);
  // Delivered replayable example — real embedded source_pdf asset.
  await offerReport(page, "replay.inkflip.json", NATIVE_REPLAY);
  await expect(page.locator("[data-testid=import-report]")).toBeVisible();
  await expect(page.locator("[data-testid=source-embedded]")).toContainText(
    "Original PDF included",
  );
  await expect(page.locator("[data-testid=report-scope]")).toContainText("replayable");
  await expect(page.locator("[data-testid=replay-state]")).toHaveText(
    "Original PDF included. Replay also requires the recorded reader environment.",
  );
  // Source bytes do not make the absent readers runnable.
  await expect(page.locator("[data-testid=replay-missing]")).toBeVisible();
  await expect(page.locator("[data-testid=replay-ready]")).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// 3. Explicit local source association + hash mismatch blocks replay
// ---------------------------------------------------------------------------

test("source attach requires exact bytes; mismatch is never attached", async ({ page }) => {
  await openPreview(page);
  await offerReport(page, "evidence.inkflip.json", await makeExport(page));
  await expect(page.locator("[data-testid=source-missing]")).toBeVisible();

  // Wrong length — a different real PDF — rejected at the declared-size
  // gate with verbatim copy and never attached.
  await offerSourceFile(page, WRONG_PDF);
  await expect(page.locator("#source-mismatch")).toContainText(
    "does not match the original document checksum",
  );
  await expect(page.locator("[data-testid=source-error-detail]")).toHaveText(
    "source:length-mismatch",
  );
  await expect(page.locator("[data-testid=source-missing]")).toBeVisible();
  await expect(page.locator("[data-testid=source-attached]")).toHaveCount(0);

  // Same length, different bytes — the declared-size gate passes, so the
  // digest itself must refuse: byte length alone is never sufficient.
  const corrupt = Buffer.from(SOURCE_PDF);
  corrupt[corrupt.length - 1] ^= 0x01;
  await offerSourceFile(page, corrupt);
  await expect(page.locator("[data-testid=source-error-detail]")).toHaveText(
    "source:sha256-mismatch",
  );
  await expect(page.locator("[data-testid=source-attached]")).toHaveCount(0);
  const rejected = (await events(page)).filter((e) => e.type === "source_rejected");
  expect(rejected.map((e) => e.detail)).toEqual([
    "source:length-mismatch",
    "source:sha256-mismatch",
  ]);

  // The exact original bytes attach and replay state updates.
  await offerSourceFile(page, SOURCE_PDF);
  await expect(page.locator("[data-testid=source-attached]")).toBeVisible();
  await expect(page.locator("#source-mismatch")).toHaveCount(0);
  await expect(page.locator("[data-testid=replay-state]")).toHaveText(
    "Original PDF included. Replay also requires the recorded reader environment.",
  );
  const attached = (await events(page)).filter((e) => e.type === "source_attached");
  expect(attached.length).toBe(1);
  expect(attached[0].sha256).toBe(DOC_SHA);
});

test("hash mismatch blocks replay: tampered report and asset are rejected", async ({ page }) => {
  await openPreview(page);
  // Delivered tampered-digest example — mutated content under the
  // original report_id — is a HASH failure, never a report.
  await offerReport(page, "tampered.inkflip.json", TAMPERED_REPORT);
  await expect(page.locator("#import-error-invalid")).toBeVisible();
  await expect(page.locator("#import-error-invalid")).toContainText("Nothing in it was executed");
  await expect(page.locator("[data-testid=import-error-detail]")).toContainText("HASH");
  await expect(page.locator("[data-testid=import-report]")).toHaveCount(0);
  expect(await fileState(page)).toBe("idle");

  // Mutating a retained occurrence without resealing breaks the digest —
  // the report cannot open, so no replay can ever run on it.
  const mutated = JSON.parse(await makeExport(page));
  mutated.occurrences[0].raw_text = "$9,999";
  mutated.occurrences[0].normalized_text = "$9,999";
  const out = await page.evaluate(async (rep) => {
    const r = (globalThis as any).__t22.engine.openReport(
      new TextEncoder().encode(JSON.stringify(rep)),
    );
    return r.ok ? { ok: true } : { ok: false, kind: r.failure.kind, code: r.failure.code };
  }, mutated);
  expect(out).toEqual({ ok: false, kind: "invalid", code: "HASH" });

  // A resealed report whose crop payload was swapped fails asset
  // verification — signatures are re-checked at the boundary.
  const assetTampered = await page.evaluate(async (src) => {
    const t = (globalThis as any).__t22;
    const rep = JSON.parse(JSON.stringify(src));
    const { report } = t.exportEngine.projectReport(rep, {});
    // Swap the crop payload for different bytes while keeping the
    // declared sha256 — the audit must catch it.
    const asset = report.assets.find((a: any) => a.purpose === "crop");
    asset.data_base64 = "bm90LXRoZS1yZWFsLW9yaWdpbmFsLWJ5dGVz";
    return JSON.stringify(report);
  }, NATIVE_EVIDENCE);
  const assetOut = await page.evaluate(async (rep) => {
    const r = (globalThis as any).__t22.engine.openReport(new TextEncoder().encode(rep));
    return r.ok ? { ok: true } : { ok: false, kind: r.failure.kind, code: r.failure.code };
  }, assetTampered);
  expect(assetOut.ok).toBe(false);
  expect(assetOut.code === "ASSET" || assetOut.code === "HASH").toBe(true);
});

test("schema version refusal is explicit", async ({ page }) => {
  await openPreview(page);
  const upgraded = JSON.parse(await makeExport(page));
  upgraded.schema_version = "2.0.0";
  const out = await page.evaluate(async (rep) => {
    const r = (globalThis as any).__t22.engine.openReport(
      new TextEncoder().encode(JSON.stringify(rep)),
    );
    return r.ok ? { ok: true } : { ok: false, kind: r.failure.kind, version: r.failure.version };
  }, upgraded);
  expect(out).toEqual({
    ok: false,
    kind: "unsupported_version",
    version: "2.0.0",
  });
  await offerReport(page, "v2.inkflip.json", JSON.stringify(upgraded));
  await expect(page.locator("#import-error-unsupported_version")).toContainText(
    "uses schema 2.0.0",
  );
});

// ---------------------------------------------------------------------------
// 4. Malicious report cannot fetch/execute/select profile
// ---------------------------------------------------------------------------

test("hostile corpus: every input rejected, zero egress, nothing executed", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (req) => requests.push(req.url()));
  await armEgress(page);
  await openPreview(page);

  // A hostile "report" whose strings carry markup/URLs/scripts — the
  // content is contract-valid, so the proof is that rendering stays
  // inert.
  const hostile = await page.evaluate(async (src) => {
    const t = (globalThis as any).__t22;
    const rep = JSON.parse(JSON.stringify(src));
    const PAYLOAD =
      '</bdi><img src="https://evil.invalid/x.png" onerror="window.__pwned=1"><script>window.__pwned2=1</script>';
    rep.document.display_name = PAYLOAD;
    rep.findings[0].title = PAYLOAD;
    rep.findings[0].explanation = '"><form action="https://evil.invalid/collect"><input>';
    const n = t.contracts.normalize("javascript:alert(1) " + PAYLOAD);
    rep.occurrences[0].raw_text = "javascript:alert(1) " + PAYLOAD;
    rep.occurrences[0].normalized_text = n.text;
    rep.occurrences[0].normalization_map = n.map;
    rep.readers[0].name = "file:///etc/passwd wget";
    rep.limitations.push("https://evil.invalid/steal?x=");
    rep.annotations.push({
      id: "a_note",
      finding_id: rep.findings[0].id,
      page_index: 0,
      text: PAYLOAD,
      author_label: "attacker",
      origin: "human_entered",
    });
    t.contracts.seal(rep);
    const { report } = t.exportEngine.projectReport(rep, {
      annotations: true,
      filename: true,
    });
    return t.exportEngine.serializeReportJson(report);
  }, NATIVE_EVIDENCE);
  const scriptsBefore = await page.locator("script").count();
  await offerReport(page, "hostile.inkflip.json", hostile);
  await expect(page.locator("[data-testid=import-report]")).toBeVisible();

  // The hostile strings render as literal text — never as elements.
  await expect(page.locator("[data-testid=report-title]")).toContainText(
    '<img src="https://evil.invalid/x.png"',
  );
  expect(await page.locator('img[src^="http"]').count()).toBe(0);
  expect(await page.locator("script").count()).toBe(scriptsBefore);
  const pwned = await page.evaluate(() => ({
    p1: (globalThis as any).__pwned,
    p2: (globalThis as any).__pwned2,
  }));
  expect(pwned.p1).toBeUndefined();
  expect(pwned.p2).toBeUndefined();

  // Now the rejectable corpus through the same gate the controller uses.
  const enc = new TextEncoder();
  const corpus: Array<[string, Uint8Array, string]> = [
    // container/archive magics — no decompression surface at all
    ["zip", Uint8Array.from([0x50, 0x4b, 0x03, 0x04, 1, 2, 3]), "not_a_report"],
    ["zip-eocd", Uint8Array.from([0x50, 0x4b, 0x05, 0x06, 0, 0]), "not_a_report"],
    ["gzip", Uint8Array.from([0x1f, 0x8b, 0x08, 0, 0]), "not_a_report"],
    ["7z", Uint8Array.from([0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c, 0]), "not_a_report"],
    ["rar", Uint8Array.from([0x52, 0x61, 0x72, 0x21, 0x1a, 0x07, 0]), "not_a_report"],
    ["xz", Uint8Array.from([0xfd, 0x37, 0x7a, 0x58, 0x5a, 0]), "not_a_report"],
    ["bzip2", Uint8Array.from([0x42, 0x5a, 0x68, 0x39, 0]), "not_a_report"],
    ["zstd", Uint8Array.from([0x28, 0xb5, 0x2f, 0xfd, 0]), "not_a_report"],
    ["cab", Uint8Array.from([0x4d, 0x53, 0x43, 0x46, 0]), "not_a_report"],
    ["ole", Uint8Array.from([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1, 0]), "not_a_report"],
    // a bare PDF is a document, never a report
    ["pdf", enc.encode("%PDF-1.4\n%%EOF"), "not_a_report"],
    // UTF-16 BOMs
    ["utf16le", Uint8Array.from([0xff, 0xfe, 0x7b, 0x00]), "not_a_report"],
    ["utf16be", Uint8Array.from([0xfe, 0xff, 0x00, 0x7b]), "not_a_report"],
    // markup / svg / xml
    ["html", enc.encode("<!doctype html><html><script>alert(1)</script>"), "not_a_report"],
    [
      "svg",
      enc.encode('  <svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'),
      "not_a_report",
    ],
    ["xml", enc.encode('<?xml version="1.0"?><x/>'), "not_a_report"],
    // malformed / bound-violating JSON
    ["truncated", enc.encode('{"kind":"report",'), "not_a_report"],
    ["not-json", enc.encode("open me please"), "not_a_report"],
    ["deep", enc.encode("[".repeat(30) + "1" + "]".repeat(30)), "not_a_report"],
    ["dupkeys", enc.encode('{"a":1,"a":2}'), "not_a_report"],
    ["nonfinite", enc.encode('{"x":1e999}'), "not_a_report"],
    ["unsafe-int", enc.encode('{"x":9007199254740993}'), "not_a_report"],
    // wrong artifact kinds — valid elsewhere, not a report
    ["comparison", COMPARISON_ARTIFACT, "not_a_report"],
  ];
  // tar magic lives at offset 257
  const tar = new Uint8Array(300);
  tar.set(enc.encode("ustar"), 257);
  corpus.push(["tar", tar, "not_a_report"]);

  const results = await page.evaluate(
    async (cases) => {
      const out: Array<{ name: string; ok: boolean; kind: string | null; code: string | null }> =
        [];
      for (const { name, bytes } of cases) {
        const r = (globalThis as any).__t22.engine.openReport(new Uint8Array(bytes));
        out.push({
          name,
          ok: r.ok,
          kind: r.ok ? null : r.failure.kind,
          code: r.ok ? null : r.failure.code,
        });
      }
      return out;
    },
    corpus.map(([name, bytes, expected]) => ({ name, bytes: Array.from(bytes), expected })),
  );

  for (let i = 0; i < corpus.length; i++) {
    const [, , expectedKind] = corpus[i];
    expect(results[i], `corpus ${corpus[i][0]}`).toMatchObject({
      ok: false,
      kind: expectedKind,
    });
  }

  // Report-shaped attacks through the same gate: prototype keys (own
  // JSON members — string surgery, since a JS assignment would set the
  // prototype, not a member), executable/profile/external-pointer
  // fields and a schema-valid worker_message — all rejected (I10: a
  // report can never select a reader executable or a profile).
  const attackResults = await page.evaluate(
    async ({ src, comparisonOk }) => {
      void comparisonOk;
      const t = (globalThis as any).__t22;
      const out: Array<{ name: string; ok: boolean; kind: string | null; code: string | null }> =
        [];
      const tryImport = (name: string, text: string) => {
        const r = t.engine.openReport(new TextEncoder().encode(text));
        out.push({
          name,
          ok: r.ok,
          kind: r.ok ? null : r.failure.kind,
          code: r.ok ? null : r.failure.code,
        });
      };
      const validJson = () => {
        const { report } = t.exportEngine.projectReport(JSON.parse(JSON.stringify(src)), {});
        return t.exportEngine.serializeReportJson(report);
      };
      // Prototype-polluting members inserted as real JSON text members.
      for (const key of ["__proto__", "constructor", "prototype"]) {
        const json = validJson();
        tryImport(
          `proto-${key}`,
          `${json.slice(0, json.lastIndexOf("}"))},"${key}":{"polluted":true}}`,
        );
      }
      // Unknown members rejected by the closed schema.
      const mutations: Array<[string, (rep: any) => void]> = [
        [
          "exec-field",
          (r) => {
            r.readers[0].executable = "/bin/sh -c evil";
          },
        ],
        [
          "exec-cmd",
          (r) => {
            r.command = "open https://evil.invalid";
          },
        ],
        [
          "profile-pick",
          (r) => {
            r.profile = "aggressive";
          },
        ],
        [
          "external-ref",
          (r) => {
            r.$ref = "https://evil.invalid/report.json";
          },
        ],
        [
          "source-url",
          (r) => {
            r.document.source_url = "https://evil.invalid/doc.pdf";
          },
        ],
        [
          "reader-path",
          (r) => {
            r.readers[0].binary_path = "/tmp/evil";
          },
        ],
        [
          "fetch-field",
          (r) => {
            r.fetch = "https://evil.invalid/beacon";
          },
        ],
        [
          "remote-asset",
          (r) => {
            r.assets[0].href = "https://evil.invalid/a.png";
          },
        ],
      ];
      for (const [name, mutate] of mutations) {
        const rep = JSON.parse(validJson());
        mutate(rep);
        tryImport(name, JSON.stringify(rep));
      }
      // A schema-valid worker_message artifact — right shape, wrong kind.
      const mf = new t.MessageFactory({
        generation: 1,
        documentSha256: "0".repeat(64),
        runKey: "a".repeat(64),
        jobId: "j_1",
      });
      tryImport("worker-message", JSON.stringify(mf.progress("chk_x", 1)));
      return out;
    },
    { src: NATIVE_EVIDENCE, comparisonOk: true },
  );
  const attackExpected: Record<string, string> = {
    "proto-__proto__": "not_a_report",
    "proto-constructor": "not_a_report",
    "proto-prototype": "not_a_report",
    "exec-field": "invalid",
    "exec-cmd": "invalid",
    "profile-pick": "invalid",
    "external-ref": "invalid",
    "source-url": "invalid",
    "reader-path": "invalid",
    "fetch-field": "invalid",
    "remote-asset": "invalid",
    "worker-message": "not_a_report",
  };
  for (const r of attackResults) {
    expect(r.ok, `attack ${r.name}`).toBe(false);
    expect(r.kind, `attack ${r.name}`).toBe(attackExpected[r.name]);
  }

  // UI-level proof: representative hostile files through the real
  // input. Confirming replacement with a non-report refuses the import
  // and keeps the previously validated session.
  const preservedTitle = await page.locator("[data-testid=report-title]").textContent();
  await offerReport(page, "page.html", "<html><body><script>alert(1)</script></body></html>");
  const hostileDialog = page.locator("[role=dialog]");
  await expect(hostileDialog).toBeVisible();
  await hostileDialog.getByRole("button", { name: "Clear and open report" }).click();
  await expect(page.locator("#import-error-not_a_report")).toBeVisible();
  await expect(page.locator("[data-testid=import-report]")).toBeVisible();
  await expect(page.locator("[data-testid=report-title]")).toHaveText(preservedTitle ?? "");
  const zipRefused = await page.evaluate(async () => {
    const t = (globalThis as any).__t22;
    const out = await t.controller.offer({
      name: "bundle.zip",
      size: 8,
      arrayBuffer: async () => Uint8Array.from([0x50, 0x4b, 0x03, 0x04, 1, 2, 3, 4]).buffer,
    });
    return {
      ok: out.ok,
      kind: out.ok ? null : out.failure.kind,
      stillOpen: t.controller.currentImport !== null,
    };
  });
  expect(zipRefused).toEqual({ ok: false, kind: "not_a_report", stillOpen: true });
  const otherRefused = await page.evaluate(async (comparison) => {
    const t = (globalThis as any).__t22;
    const bytes = new TextEncoder().encode(comparison);
    const out = await t.controller.offer({
      name: "other.inkflip.json",
      size: bytes.byteLength,
      arrayBuffer: async () => bytes.buffer,
    });
    return { ok: out.ok, kind: out.ok ? null : out.failure.kind, stillOpen: t.controller.currentImport !== null };
  }, COMPARISON_ARTIFACT.toString("utf8"));
  expect(otherRefused.ok).toBe(false);
  expect(otherRefused.stillOpen).toBe(true);
  await expect(page.locator("[data-testid=import-report]")).toBeVisible();

  // Zero egress: every recorded request is same-origin, and the
  // tripwires captured nothing beyond Vite's HMR socket.
  const origin = new URL(harness.base).origin;
  for (const url of requests) {
    expect(url.startsWith(origin), `foreign request ${url}`).toBe(true);
  }
  for (const entry of await egress(page)) {
    expect(entry.startsWith("websocket:ws://localhost")).toBe(true);
  }
  const markers = await page.evaluate(() => ({
    p1: (globalThis as any).__pwned,
    p2: (globalThis as any).__pwned2,
  }));
  expect(markers.p1).toBeUndefined();
  expect(markers.p2).toBeUndefined();
});

// ---------------------------------------------------------------------------
// 5. Comparison asks for exact locally selected source reports
// ---------------------------------------------------------------------------

test("comparison requires two exact local selections — no ids, no urls", async ({ page }) => {
  await armEgress(page);
  await openPreview(page);
  await expect(page.locator("[data-testid=compare-panel]")).toContainText(
    "Both reports must be chosen locally",
  );

  const evidenceA = await makeExport(page);
  const evidenceB = await makeExport(page, { scope: "run" });

  // Two distinct reports over the SAME document bytes → ready.
  await offerCompareSide(page, "left", evidenceA);
  await expect(page.locator("[data-testid=compare-left-id]")).toBeVisible();
  expect(await page.locator("[data-testid=compare-verdict]").count()).toBe(0);
  await offerCompareSide(page, "right", evidenceB);
  await expect(page.locator("[data-testid=compare-status-ready]")).toContainText(
    "same document bytes",
  );
  await expect(page.locator("[data-testid=compare-left-id]")).toContainText(
    JSON.parse(evidenceA).report_id.slice(0, 16),
  );
  await expect(page.locator("[data-testid=compare-right-id]")).toContainText(
    JSON.parse(evidenceB).report_id.slice(0, 16),
  );

  // Identical selection twice → called out, not a comparison.
  await offerCompareSide(page, "right", evidenceA);
  await expect(page.locator("[data-testid=compare-status-same]")).toContainText("same report");

  // A different-document report is incomparable — different bytes are
  // not the same file.
  const different = await page.evaluate(async (src) => {
    const t = (globalThis as any).__t22;
    const rep = JSON.parse(JSON.stringify(src));
    rep.document.sha256 = "a".repeat(64);
    rep.document.byte_length = 42;
    t.contracts.seal(rep);
    const { report } = t.exportEngine.projectReport(rep, {});
    return t.exportEngine.serializeReportJson(report);
  }, NATIVE_EVIDENCE);
  await offerCompareSide(page, "right", different);
  await expect(page.locator("[data-testid=compare-status-incomparable]")).toContainText(
    "not comparable",
  );

  // An invalid side shows its own failure — never silently ignored.
  await offerCompareSide(page, "right", "not a report at all");
  await expect(page.locator("[data-testid=compare-right-error]")).toBeVisible();
  expect(await page.locator("[data-testid=compare-verdict]").count()).toBe(0);

  // Nothing fetched — compare sides are validated locally.
  for (const entry of await egress(page)) {
    expect(entry.startsWith("websocket:ws://localhost")).toBe(true);
  }
});

// ---------------------------------------------------------------------------
// 6. Generation-first replacement (I07)
// ---------------------------------------------------------------------------

test("a new report clears the previous generation before reopening", async ({ page }) => {
  await openPreview(page);
  const reportA = await makeExport(page);
  const reportB = await makeReplayableExport(page, SOURCE_PDF);
  const idA = JSON.parse(reportA).report_id as string;
  const idB = JSON.parse(reportB).report_id as string;
  expect(idA).not.toBe(idB);

  await offerReport(page, "a.inkflip.json", reportA);
  await expect(page.locator("[data-testid=import-report]")).toBeVisible();
  const genA = await generation(page);

  // Replacement through the UI stands behind the confirm dialog.
  await offerReport(page, "b.inkflip.json", reportB);
  const dialog = page.locator("[role=dialog]");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Open a different report?");
  await dialog.getByRole("button", { name: "Keep this report" }).click();
  expect(await generation(page)).toBe(genA);

  await offerReport(page, "b.inkflip.json", reportB);
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Clear and open report" }).click();
  await expect(page.locator("[data-testid=source-embedded]")).toBeVisible();
  await expect(page.locator("[data-testid=report-id]")).toContainText(idB.slice(0, 16));

  const log = await events(page);
  const clear = log.find((e) => e.type === "clear");
  const teardowns = log.filter((e) => e.type === "teardown");
  expect(clear).toBeTruthy();
  // I07: clear intent recorded the OLD generation; teardown observed the
  // NEW one — strictly greater.
  expect(clear!.generation).toBe(genA);
  for (const td of teardowns) {
    expect(td.generation).toBe(genA + 1);
  }
  const order = log.map((e) => e.type);
  expect(order.indexOf("clear")).toBeLessThan(order.indexOf("teardown"));
  expect(order.indexOf("teardown")).toBeLessThan(order.lastIndexOf("imported"));

  // A worker message stamped with the OLD generation is rejected stale
  // by the authority — not merely hidden.
  const stale = await page.evaluate(
    ({ gen }) => {
      const { coordinator, MessageFactory } = (globalThis as any).__t22;
      const mf = new MessageFactory({
        generation: gen,
        documentSha256: "0".repeat(64),
        runKey: "a".repeat(64),
        jobId: "j_1",
      });
      return coordinator.receive(mf.progress("chk_x", 1));
    },
    { gen: genA },
  );
  expect(stale).toEqual({ ok: false, code: "stale_generation" });
});

test("a pending source read cannot attach across a superseded generation", async ({ page }) => {
  await openPreview(page);
  const reportA = await makeExport(page);
  // B records a DIFFERENT document — an attach verified against A's
  // identity must never land on it, even as a display claim.
  const reportB = await page.evaluate(async (src) => {
    const t = (globalThis as any).__t22;
    const rep = JSON.parse(JSON.stringify(src));
    rep.document.sha256 = "a".repeat(64);
    rep.document.byte_length = 42;
    t.contracts.seal(rep);
    const { report } = t.exportEngine.projectReport(rep, {});
    return t.exportEngine.serializeReportJson(report);
  }, NATIVE_EVIDENCE);
  const idB = JSON.parse(reportB).report_id as string;

  // Phase 1+2 — busy entry guard, then replace-during-read: the new
  // report wins and the stale read is dropped before it can attach.
  const race = await page.evaluate(
    async ({ aJson, bJson, pdf }) => {
      const t = (globalThis as any).__t22;
      const enc = new TextEncoder();
      const out: Record<string, unknown> = {};
      const defer = (make: () => ArrayBuffer) => {
        let release!: () => void;
        const gate = new Promise<void>((resolve) => {
          release = resolve;
        });
        return { read: () => gate.then(make), release };
      };

      // offerSource during an in-flight report import is refused up
      // front — it never starts a byte read.
      const a = defer(() => enc.encode(aJson).buffer as ArrayBuffer);
      const offerP = t.controller.offer({
        name: "a.inkflip.json",
        size: enc.encode(aJson).byteLength,
        arrayBuffer: a.read,
      });
      const early = await t.controller.offerSource({
        name: "early.pdf",
        size: pdf.length,
        arrayBuffer: async () => new Uint8Array(pdf).buffer as ArrayBuffer,
      });
      out.busy = early.ok ? "accepted" : early.kind;
      a.release();
      out.openA = (await offerP).ok;

      // A source read pending on A, then report B offered (replace):
      // B's generation wins and the in-flight read resolves superseded
      // — no attach, no ownership, no event under B's generation.
      const src = defer(() => new Uint8Array(pdf).buffer as ArrayBuffer);
      const pending = t.controller.offerSource({
        name: "orig.pdf",
        size: pdf.length,
        arrayBuffer: src.read,
      });
      out.openB = (
        await t.controller.offer({
          name: "b.inkflip.json",
          size: enc.encode(bJson).byteLength,
          arrayBuffer: async () => enc.encode(bJson).buffer as ArrayBuffer,
        })
      ).ok;
      src.release();
      const stale = await pending;
      out.stale = stale.ok ? "attached" : stale.kind;
      out.currentIsB = t.controller.currentImport?.view.reportId === JSON.parse(bJson).report_id;
      return out;
    },
    { aJson: reportA, bJson: reportB, pdf: Array.from(SOURCE_PDF) },
  );
  expect(race.busy).toBe("busy");
  expect(race.openA).toBe(true);
  expect(race.openB).toBe(true);
  expect(race.stale).toBe("superseded");
  expect(race.currentIsB).toBe(true);

  // B's own view is untouched by A's pending attach: it still records
  // a missing original and no attach ever displayed.
  await expect(page.locator("[data-testid=report-id]")).toContainText(idB.slice(0, 16));
  await expect(page.locator("[data-testid=source-missing]")).toBeVisible();
  await expect(page.locator("[data-testid=source-attached]")).toHaveCount(0);

  // Phase 3 — clear-during-read: the workspace empties and the stale
  // read cannot resurrect the cleared report.
  const cleared = await page.evaluate(async () => {
    const t = (globalThis as any).__t22;
    const out: Record<string, unknown> = {};
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const pending = t.controller.offerSource({
      name: "late.pdf",
      size: 42,
      arrayBuffer: () => gate.then(() => new ArrayBuffer(42)),
    });
    t.controller.clear();
    release();
    const stale = await pending;
    out.stale = stale.ok ? "attached" : stale.kind;
    out.currentAfterClear = t.controller.currentImport === null;
    out.stateAfterClear = t.coordinator.fileState;
    out.attachEvents = t.events.filter(
      (e: { type: string }) => e.type === "source_attached",
    ).length;
    return out;
  });
  expect(cleared.stale).toBe("superseded");
  expect(cleared.currentAfterClear).toBe(true);
  expect(cleared.stateAfterClear).toBe("idle");
  expect(cleared.attachEvents).toBe(0);
  await expect(page.locator("[data-testid=import-report]")).toHaveCount(0);
  await expect(page.locator("[data-testid=source-attached]")).toHaveCount(0);
});

test("a superseded source read that fails emits nothing under the new report", async ({ page }) => {
  await openPreview(page);
  const reportA = await makeExport(page);
  const reportB = await page.evaluate(async (src) => {
    const t = (globalThis as any).__t22;
    const rep = JSON.parse(JSON.stringify(src));
    rep.document.sha256 = "a".repeat(64);
    rep.document.byte_length = 42;
    t.contracts.seal(rep);
    const { report } = t.exportEngine.projectReport(rep, {});
    return t.exportEngine.serializeReportJson(report);
  }, NATIVE_EVIDENCE);
  const idB = JSON.parse(reportB).report_id as string;

  // Phases 1-3: entry refusals emit nothing; a rejecting read
  // superseded by a replace drops its failure silently; the identical
  // failure while still bound emits honestly under its own generation.
  const race = await page.evaluate(
    async ({ aJson, bJson, pdfLen }) => {
      const t = (globalThis as any).__t22;
      const enc = new TextEncoder();
      const out: Record<string, unknown> = {};
      const rejectedCount = () =>
        t.events.filter((e: { type: string }) => e.type === "source_rejected").length;
      const cand = (name: string, size: number, read: () => Promise<ArrayBuffer>) => ({
        name,
        size,
        arrayBuffer: read,
      });

      // Entry refusals — the pick was never evaluated against a report:
      // no_report (nothing open), then busy (a report import holds the
      // lock). Typed kinds return to the caller; no event is emitted.
      const before = rejectedCount();
      const noReport = await t.controller.offerSource(
        cand("none.pdf", pdfLen, async () => new ArrayBuffer(pdfLen)),
      );
      out.noReport = noReport.ok ? "attached" : noReport.kind;
      let releaseA!: () => void;
      const gateA = new Promise<void>((resolve) => {
        releaseA = resolve;
      });
      const offerP = t.controller.offer(
        cand("a.inkflip.json", enc.encode(aJson).byteLength, () =>
          gateA.then(() => enc.encode(aJson).buffer as ArrayBuffer),
        ),
      );
      const busy = await t.controller.offerSource(
        cand("early.pdf", pdfLen, async () => new ArrayBuffer(pdfLen)),
      );
      out.busy = busy.ok ? "attached" : busy.kind;
      releaseA();
      out.openA = (await offerP).ok;
      out.refusalsEmitted = rejectedCount() - before;
      out.genA = t.coordinator.currentGeneration;

      // A pending read on A that REJECTS, superseded by report B: the
      // failure belongs to the gone report — the newer generation must
      // never see it (round-2 residual R1).
      const beforeStale = rejectedCount();
      let release!: () => void;
      const gate = new Promise<void>((resolve) => {
        release = resolve;
      });
      const pending = t.controller.offerSource(
        cand("orig.pdf", pdfLen, () => gate.then(() => Promise.reject(new Error("read failed")))),
      );
      out.openB = (
        await t.controller.offer(
          cand(
            "b.inkflip.json",
            enc.encode(bJson).byteLength,
            async () => enc.encode(bJson).buffer as ArrayBuffer,
          ),
        )
      ).ok;
      out.genB = t.coordinator.currentGeneration;
      release();
      const stale = await pending;
      out.stale = stale.ok ? "attached" : stale.kind;
      out.staleEmitted = rejectedCount() - beforeStale;
      out.currentIsB = t.controller.currentImport?.view.reportId === JSON.parse(bJson).report_id;

      // The identical failure while still bound DOES emit — the pick
      // was evaluated against the open report and genuinely refused.
      const unreadable = await t.controller.offerSource(
        cand("bad.pdf", 42, () => Promise.reject(new Error("still unreadable"))),
      );
      out.unreadable = unreadable.ok ? "attached" : unreadable.kind;
      const last = t.events.filter((e: { type: string }) => e.type === "source_rejected").at(-1);
      out.unreadableDetail = last?.detail;
      out.unreadableGen = last?.generation;
      return out;
    },
    { aJson: reportA, bJson: reportB, pdfLen: SOURCE_PDF.length },
  );
  expect(race.noReport).toBe("no_report");
  expect(race.busy).toBe("busy");
  expect(race.openA).toBe(true);
  expect(race.refusalsEmitted).toBe(0);
  expect(race.openB).toBe(true);
  expect(race.genB).toBe(race.genA + 1);
  expect(race.stale).toBe("superseded");
  expect(race.staleEmitted).toBe(0);
  expect(race.currentIsB).toBe(true);
  expect(race.unreadable).toBe("source_mismatch");
  expect(race.unreadableDetail).toBe("source:unreadable");
  expect(race.unreadableGen).toBe(race.genB);

  // B renders the honest same-context refusal — and only that one.
  await expect(page.locator("[data-testid=report-id]")).toContainText(idB.slice(0, 16));
  await expect(page.locator("[data-testid=source-error-detail]")).toHaveText("source:unreadable");
  await expect(page.locator("[data-testid=source-attached]")).toHaveCount(0);

  // not_required — an embedded-source report refuses the pick before
  // any read: typed kind, no event, nothing rendered as a rejection.
  const embedded = await page.evaluate(
    async ({ replayJson }) => {
      const t = (globalThis as any).__t22;
      const enc = new TextEncoder();
      await t.controller.offer({
        name: "replay.inkflip.json",
        size: enc.encode(replayJson).byteLength,
        arrayBuffer: async () => enc.encode(replayJson).buffer as ArrayBuffer,
      });
      const before = t.events.filter((e: { type: string }) => e.type === "source_rejected").length;
      const notRequired = await t.controller.offerSource({
        name: "extra.pdf",
        size: 1,
        arrayBuffer: async () => new ArrayBuffer(1),
      });
      return {
        notRequired: notRequired.ok ? "attached" : notRequired.kind,
        emitted:
          t.events.filter((e: { type: string }) => e.type === "source_rejected").length - before,
      };
    },
    { replayJson: NATIVE_REPLAY.toString("utf8") },
  );
  expect(embedded.notRequired).toBe("not_required");
  expect(embedded.emitted).toBe(0);
  await expect(page.locator("[data-testid=source-embedded]")).toBeVisible();
  await expect(page.locator("#source-mismatch")).toHaveCount(0);
});

test("declared-size gate rejects before any byte is read", async ({ page }) => {
  await openPreview(page);
  const over = await page.evaluate(async (limit) => {
    const { controller } = (globalThis as any).__t22;
    let reads = 0;
    const fake = {
      name: "huge.inkflip.json",
      size: limit + 1,
      arrayBuffer: async () => {
        reads += 1;
        return new ArrayBuffer(0);
      },
    };
    const out = await controller.offer(fake);
    return {
      ok: out.ok,
      kind: out.ok ? null : out.failure.kind,
      reads,
    };
  }, MAX_JSON_BYTES);
  expect(over).toEqual({ ok: false, kind: "too_large", reads: 0 });
  await expect(page.locator("#import-error-too_large")).toBeVisible();
  expect(await fileState(page)).toBe("idle");
});

// ---------------------------------------------------------------------------
// 7. Installed-reader path: recorded readers present → replay ready
// ---------------------------------------------------------------------------

test("installed readers plus attached source make replay readiness explicit", async ({ page }) => {
  await openPreview(page);
  const variant = await makeBrowserReaderExport(page);
  await offerReport(page, "browser.inkflip.json", variant);
  await expect(page.locator("[data-testid=import-report]")).toBeVisible();

  // The recorded readers match the installed pdf.js allowlist exactly.
  expect(await page.locator("[data-testid^=reader-installed-]").count()).toBe(2);
  expect(await page.locator("[data-testid^=reader-missing-]").count()).toBe(0);

  // Source still required — attach the exact original.
  await expect(page.locator("[data-testid=source-missing]")).toBeVisible();
  await offerSourceFile(page, SOURCE_PDF);
  await expect(page.locator("[data-testid=source-attached]")).toBeVisible();
  await expect(page.locator("[data-testid=replay-ready]")).toContainText(
    "every recorded reader are present locally",
  );
});
