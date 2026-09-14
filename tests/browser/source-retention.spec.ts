/**
 * Source-retention races in InspectionSession.offerFile: a delayed second
 * read of PDF A must not clear or overwrite a newer document's verified
 * bytes. Export inclusion stays opt-in and bound to those bytes.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const ROOT = path.resolve(process.cwd());
const WEB = path.join(ROOT, "apps", "web");
const AMOUNT_SHA = "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80";
const DUPLICATES_SHA = "036db55ee2f8c320252c7c9fb220daa38699387800e8a3bbf8c6bb73463feb1f";
const DUPLICATES_BYTES = 754;
const AMOUNT_BYTES = 1437;

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

type Snap = {
  sha: string | null;
  reportSha: string | null;
  bytes: number | null;
  error: string | null;
  hasSourceBytes: boolean;
};

type RaceKind =
  | "resolve-on-b"
  | "reject-on-b"
  | "resolve-after-close"
  | "resolve-on-imported-report"
  | "reject-after-aba";

async function gotoWorkspace(page: Page): Promise<void> {
  await page.goto(`${baseUrl}/#/workspace`);
  await page.waitForFunction(() => (globalThis as { __inspect?: unknown }).__inspect);
}

async function runHeldSourceRead(page: Page, kind: RaceKind): Promise<{
  error?: string;
  attached?: boolean;
  before?: Snap;
  after?: Snap;
}> {
  return page.evaluate(async ({ kind, duplicatesSha }) => {
    const s = (
      globalThis as {
        __inspect?: {
          offerFile(candidate: {
            name: string;
            type: string;
            size: number;
            slice: (a: number, b: number) => { arrayBuffer(): Promise<ArrayBuffer> };
            arrayBuffer(): Promise<ArrayBuffer>;
          }): Promise<void>;
          close(): void;
          retainVerifiedSourceBytes(
            bytes: Uint8Array,
            expectedSha256: string,
            generation: number,
          ): Promise<boolean>;
          sourcePdfBytes(): Uint8Array | null;
          getState(): {
            doc?: { sha256?: string } | null;
            report?: { document?: { sha256?: string } } | null;
            error?: { message?: string } | null;
            hasSourceBytes?: boolean;
            generation?: number;
          };
        };
      }
    ).__inspect;
    if (!s) return { error: "no-inspect" };

    const snap = () => ({
      sha: s.getState().doc?.sha256 ?? null,
      reportSha: s.getState().report?.document?.sha256 ?? null,
      bytes: s.sourcePdfBytes()?.length ?? null,
      error: s.getState().error?.message ?? null,
      hasSourceBytes: s.getState().hasSourceBytes === true,
    });
    const fetchPdf = async (id: string) => {
      const manifest = (await (await fetch(`/examples/${id}/manifest.json`)).json()) as {
        files: { source: { download_url: string } };
      };
      return (await fetch(manifest.files.source.download_url)).arrayBuffer();
    };
    const pdfFile = (bytes: ArrayBuffer, name: string) =>
      new File([bytes], name, { type: "application/pdf" });

    const a = await fetchPdf("amount");
    const b = await fetchPdf("duplicates");
    let unblock!: () => void;
    const held = new Promise<void>((resolve) => {
      unblock = resolve;
    });
    let started!: () => void;
    const ready = new Promise<void>((resolve) => {
      started = resolve;
    });
    let reads = 0;
    const pending = s.offerFile({
      name: "a.pdf",
      type: "application/pdf",
      size: a.byteLength,
      slice: (x, y) => new Blob([a]).slice(x, y),
      arrayBuffer: async () => {
        reads += 1;
        if (reads === 2) {
          started();
          await held;
          if (kind === "reject-on-b" || kind === "reject-after-aba") {
            throw new Error("stale source read failed");
          }
          return a.slice(0);
        }
        return a.slice(0);
      },
    });
    await ready;

    let attached: boolean | undefined;
    if (kind === "resolve-after-close") {
      s.close();
    } else if (kind === "resolve-on-imported-report") {
      const reportText = await (await fetch("/examples/duplicates/report.json")).text();
      const reportBytes = new TextEncoder().encode(reportText);
      await s.offerFile({
        name: "duplicates.inkflip.json",
        type: "application/json",
        size: reportBytes.byteLength,
        slice: (x, y) => ({
          arrayBuffer: async () => reportBytes.slice(x, y).buffer as ArrayBuffer,
        }),
        arrayBuffer: async () => reportBytes.buffer as ArrayBuffer,
      });
      attached = await s.retainVerifiedSourceBytes(
        new Uint8Array(b.slice(0)),
        duplicatesSha,
        s.getState().generation ?? 0,
      );
    } else {
      await s.offerFile(pdfFile(b, "b.pdf"));
      if (kind === "reject-after-aba") {
        await s.offerFile(pdfFile(a, "a-again.pdf"));
      }
    }

    const before = snap();
    unblock();
    await pending;
    return { attached, before, after: snap() };
  }, { kind, duplicatesSha: DUPLICATES_SHA });
}

test("delayed PDF A source read does not clear B's retained bytes", async ({ page }) => {
  await gotoWorkspace(page);
  const result = await runHeldSourceRead(page, "resolve-on-b");
  expect(result.error ?? null).toBeNull();
  expect(result.before?.sha).toBe(DUPLICATES_SHA);
  expect(result.before?.bytes).toBe(DUPLICATES_BYTES);
  expect(result.after?.sha).toBe(DUPLICATES_SHA);
  expect(result.after?.bytes, "stale A completion must not clear B's source").toBe(DUPLICATES_BYTES);
  expect(result.after?.error).toBeNull();
});

test("stale rejected source read does not clear B or publish an error on B", async ({ page }) => {
  await gotoWorkspace(page);
  const result = await runHeldSourceRead(page, "reject-on-b");
  expect(result.before?.sha).toBe(DUPLICATES_SHA);
  expect(result.before?.bytes).toBe(DUPLICATES_BYTES);
  expect(result.after?.sha).toBe(DUPLICATES_SHA);
  expect(result.after?.bytes).toBe(DUPLICATES_BYTES);
  expect(result.after?.error).toBeNull();
});

test("close while a source read is pending does not restore A's bytes", async ({ page }) => {
  await gotoWorkspace(page);
  const result = await runHeldSourceRead(page, "resolve-after-close");
  expect(result.before?.sha).toBeNull();
  expect(result.before?.bytes).toBeNull();
  expect(result.after?.sha).toBeNull();
  expect(result.after?.bytes).toBeNull();
  expect(result.after?.error).toBeNull();
});

test("stale PDF source read does not clear a newer imported report's verified bytes", async ({
  page,
}) => {
  await gotoWorkspace(page);
  const result = await runHeldSourceRead(page, "resolve-on-imported-report");
  expect(result.attached).toBe(true);
  expect(result.before?.reportSha).toBe(DUPLICATES_SHA);
  expect(result.before?.bytes).toBe(DUPLICATES_BYTES);
  expect(result.after?.reportSha).toBe(DUPLICATES_SHA);
  expect(result.after?.bytes).toBe(DUPLICATES_BYTES);
  expect(result.after?.error).toBeNull();
});

test("rapid A then B then A keeps the live A's verified bytes", async ({ page }) => {
  await gotoWorkspace(page);
  const result = await runHeldSourceRead(page, "reject-after-aba");
  expect(result.before?.sha).toBe(AMOUNT_SHA);
  expect(result.before?.bytes).toBe(AMOUNT_BYTES);
  expect(result.after?.sha).toBe(AMOUNT_SHA);
  expect(result.after?.bytes).toBe(AMOUNT_BYTES);
  expect(result.after?.error).toBeNull();
});

test("refused import keeps the live PDF and its verified source bytes", async ({ page }) => {
  await gotoWorkspace(page);
  const result = await page.evaluate(async (duplicatesSha) => {
    const s = (
      globalThis as {
        __inspect?: {
          offerFile(candidate: {
            name: string;
            type: string;
            size: number;
            slice: (a: number, b: number) => { arrayBuffer(): Promise<ArrayBuffer> };
            arrayBuffer(): Promise<ArrayBuffer>;
          }): Promise<void>;
          sourcePdfBytes(): Uint8Array | null;
          getState(): {
            doc?: { sha256?: string } | null;
            report?: { document?: { sha256?: string } } | null;
            error?: { message?: string } | null;
            hasSourceBytes?: boolean;
          };
        };
      }
    ).__inspect;
    if (!s) return { error: "no-inspect" };
    const snap = () => ({
      sha: s.getState().doc?.sha256 ?? null,
      reportSha: s.getState().report?.document?.sha256 ?? null,
      bytes: s.sourcePdfBytes()?.length ?? null,
      error: s.getState().error?.message ?? null,
      hasSourceBytes: s.getState().hasSourceBytes === true,
    });
    const manifest = (await (await fetch("/examples/duplicates/manifest.json")).json()) as {
      files: { source: { download_url: string } };
    };
    const b = await (await fetch(manifest.files.source.download_url)).arrayBuffer();
    await s.offerFile(new File([b], "b.pdf", { type: "application/pdf" }));
    const before = snap();
    const bad = new TextEncoder().encode(JSON.stringify({ kind: "nope" }));
    await s.offerFile({
      name: "malformed.json",
      type: "application/json",
      size: bad.byteLength,
      slice: (x, y) => ({
        arrayBuffer: async () => bad.slice(x, y).buffer as ArrayBuffer,
      }),
      arrayBuffer: async () => bad.buffer as ArrayBuffer,
    });
    return { duplicatesSha, before, after: snap() };
  }, DUPLICATES_SHA);
  expect(result.before?.sha).toBe(DUPLICATES_SHA);
  expect(result.before?.bytes).toBe(DUPLICATES_BYTES);
  expect(result.after?.sha).toBe(DUPLICATES_SHA);
  expect(result.after?.bytes).toBe(DUPLICATES_BYTES);
  expect(result.after?.error).toBeTruthy();
});

test("after the A→B race, B's verified bytes are the only source a real export can include", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await gotoWorkspace(page);
  const raced = await page.evaluate(async () => {
    const s = (
      globalThis as {
        __inspect?: {
          offerFile(candidate: {
            name: string;
            type: string;
            size: number;
            slice: (a: number, b: number) => { arrayBuffer(): Promise<ArrayBuffer> };
            arrayBuffer(): Promise<ArrayBuffer>;
          }): Promise<void>;
          sourcePdfBytes(): Uint8Array | null;
          getState(): {
            doc?: { sha256?: string } | null;
            report?: { document?: { sha256?: string } } | null;
            error?: { message?: string } | null;
            hasSourceBytes?: boolean;
          };
        };
      }
    ).__inspect;
    if (!s) return { error: "no-inspect" };
    const fetchPdf = async (id: string) => {
      const manifest = (await (await fetch(`/examples/${id}/manifest.json`)).json()) as {
        files: { source: { download_url: string } };
      };
      return (await fetch(manifest.files.source.download_url)).arrayBuffer();
    };
    const a = await fetchPdf("amount");
    const b = await fetchPdf("duplicates");
    let unblock!: () => void;
    const held = new Promise<void>((resolve) => {
      unblock = resolve;
    });
    let started!: () => void;
    const ready = new Promise<void>((resolve) => {
      started = resolve;
    });
    let reads = 0;
    const pending = s.offerFile({
      name: "a.pdf",
      type: "application/pdf",
      size: a.byteLength,
      slice: (x, y) => new Blob([a]).slice(x, y),
      arrayBuffer: async () => {
        reads += 1;
        if (reads === 2) {
          started();
          await held;
          return a.slice(0);
        }
        return a.slice(0);
      },
    });
    await ready;
    await s.offerFile(new File([b], "b.pdf", { type: "application/pdf" }));
    unblock();
    await pending;
    return {
      sha: s.getState().doc?.sha256 ?? null,
      bytes: s.sourcePdfBytes()?.length ?? null,
      error: s.getState().error?.message ?? null,
    };
  });
  expect(raced.error ?? null).toBeNull();
  expect(raced.sha).toBe(DUPLICATES_SHA);
  expect(raced.bytes).toBe(DUPLICATES_BYTES);

  await expect(page.getByTestId("start-run")).toBeEnabled({ timeout: 15_000 });
  await page.getByTestId("start-run").click();
  await expect(page.getByRole("button", { name: "Download portable JSON" })).toBeEnabled({
    timeout: 60_000,
  });
  const live = await page.evaluate(() => {
    const s = (
      globalThis as {
        __inspect?: {
          sourcePdfBytes(): Uint8Array | null;
          getState(): {
            doc?: { sha256?: string } | null;
            report?: { document?: { sha256?: string } } | null;
          };
        };
      }
    ).__inspect;
    return {
      sha: s?.getState().doc?.sha256 ?? s?.getState().report?.document?.sha256 ?? null,
      bytes: s?.sourcePdfBytes()?.length ?? null,
    };
  });
  expect(live.sha).toBe(DUPLICATES_SHA);
  expect(live.bytes).toBe(DUPLICATES_BYTES);

  const defaultPending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download portable JSON" }).click();
  const defaultFile = await (await defaultPending).path();
  expect(defaultFile).toBeTruthy();
  const defaultPayload = JSON.parse(readFileSync(defaultFile as string, "utf8"));
  expect(defaultPayload.document.sha256).toBe(DUPLICATES_SHA);
  expect(defaultPayload.document.source_asset_id ?? null).toBeNull();
  const defaultSources = (defaultPayload.assets ?? []).filter(
    (asset: { purpose?: string }) => asset.purpose === "source_pdf",
  );
  expect(defaultSources).toHaveLength(0);
  expect(JSON.stringify(defaultPayload.export.omissions)).toContain("Original PDF excluded");

  await page.getByLabel("Include the original PDF").check();
  await expect(page.getByText("Requested original bytes unavailable — evidence only.")).toHaveCount(
    0,
  );
  const includedPending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download portable JSON" }).click();
  const includedFile = await (await includedPending).path();
  expect(includedFile).toBeTruthy();
  const includedPayload = JSON.parse(readFileSync(includedFile as string, "utf8"));
  const includedSources = (includedPayload.assets ?? []).filter(
    (asset: { purpose?: string }) => asset.purpose === "source_pdf",
  );
  expect(includedSources).toHaveLength(1);
  const asset = includedSources[0];
  expect(asset.sha256).toBe(DUPLICATES_SHA);
  const decoded = Buffer.from(asset.data_base64, "base64");
  expect(decoded.length).toBe(DUPLICATES_BYTES);
  expect(createHash("sha256").update(decoded).digest("hex")).toBe(DUPLICATES_SHA);
  expect(includedPayload.export.included).toContain("source_pdf");

  await page.locator("#btn-close-doc").click();
  await page.locator("#input-import-report").setInputFiles({
    name: "roundtrip.inkflip.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(defaultPayload)),
  });
  await page.waitForFunction(
    (sha) =>
      (
        globalThis as {
          __inspect?: { getState(): { report?: { document?: { sha256?: string } } | null } };
        }
      ).__inspect?.getState().report?.document?.sha256 === sha,
    DUPLICATES_SHA,
    { timeout: 15_000 },
  );
  const reimportedBytes = await page.evaluate(
    () =>
      (
        globalThis as { __inspect?: { sourcePdfBytes(): Uint8Array | null } }
      ).__inspect?.sourcePdfBytes()?.length ?? null,
  );
  expect(reimportedBytes).toBeNull();
});
