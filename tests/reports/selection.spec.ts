/**
 * T23 — Export selection, annotations and privacy preview: real Chromium.
 *
 * Part A boots the T16 export preview harness
 * (`apps/web/src/features/export/preview.html`) wired to the real
 * `projectReport`/`serializeReportJson` engine — nothing is mocked at the
 * contract surface. It proves:
 *
 * - Multi-finding selection exports only the chosen findings; unrelated
 *   occurrence text never leaks; deselected findings stay disclosed;
 *   `produced_occurrence_count` and the check list survive subsetting.
 * - "Include my notes" is the only path for annotations into the export;
 *   notes never become occurrences.
 * - The original-PDF opt-in is explicit and its warning copy discloses
 *   every page and hidden content; a crop stays an excerpt, not a safe
 *   redaction, and its real pixels are previewed before download.
 *
 * Part B boots the real app at `/#/workspace`, imports the delivered
 * example report, authors a note through the actual FindingNotes UI inside
 * the viewer, then exports through the real panel — proving a note the
 * user typed lands in `annotations` (origin `human_entered`) only after
 * opt-in, and never in `occurrences`.
 */
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import type { ExportHarnessApi } from "../../apps/web/src/features/export/mount";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const WEB = join(ROOT, "apps", "web");
const PREVIEW_URL = "/src/features/export/preview.html";
const EXAMPLE_REPORT = join(
  ROOT,
  "planning",
  "contracts",
  "examples",
  "valid",
  "native-evidence.inkflip.json",
);

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
    createServer: (opts: {
      root: string;
      server: { port: number; strictPort?: boolean; fs?: { allow?: string[] } };
      logLevel: string;
    }) => Promise<{
      listen: () => Promise<void>;
      resolvedUrls: { local: string[] };
      close: () => Promise<void>;
    }>;
  };
  const server = await createServer({
    root: WEB,
    server: { port: 0, strictPort: false, fs: { allow: [ROOT] } },
    logLevel: "warn",
  });
  await server.listen();
  harness = { base: server.resolvedUrls.local[0].replace(/\/$/, ""), close: () => server.close() };
});

test.afterAll(async () => {
  if (harness) await harness.close();
});

/** Run a function inside the page against `globalThis.__exportHarness`. */
function withHarness<T>(
  page: Page,
  fn: (h: ExportHarnessApi) => T,
): Promise<T> {
  return page.evaluate(
    `(${fn.toString()})(globalThis.__exportHarness)`,
  ) as Promise<T>;
}

async function openExportPreview(page: Page): Promise<void> {
  await page.goto(`${harness.base}${PREVIEW_URL}`);
  await page.waitForFunction(
    () =>
      (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness !==
      undefined,
    undefined,
    { timeout: 30_000 },
  );
  await expect(page.locator("h2")).toContainText("Preview what you will export");
}

interface DownloadedJson {
  findings: { id: string }[];
  occurrences: { id: string; raw_text: string }[];
  checks: { id: string; produced_occurrence_count: number }[];
  annotations: { id: string; finding_id: string | null; origin: string; text: string }[];
  assets: { purpose: string }[];
  export: { omissions: string[]; included: string[] };
  document: { display_name: string | null };
}

async function downloadJson(page: Page): Promise<DownloadedJson> {
  const before = await withHarness(page, (h) => h.getDownloads().length);
  await page.getByRole("button", { name: "Download portable JSON" }).click();
  await page.waitForFunction(
    (n) =>
      (globalThis as unknown as { __exportHarness: ExportHarnessApi }).__exportHarness
        .getDownloads().length > n,
    before,
    { timeout: 15_000 },
  );
  const downloads = await withHarness(page, (h) => h.getDownloads());
  const entry = downloads[downloads.length - 1];
  return JSON.parse(entry.text) as DownloadedJson;
}

test.describe("T23 export selection", () => {
  test("multi-finding selection excludes unrelated evidence and preserves produced counts", async ({
    page,
  }) => {
    await openExportPreview(page);
    // Two-finding variant: `f_extra` cites a dedicated occurrence whose
    // text is a unique marker, proving per-finding exclusion.
    await withHarness(page, (h) => {
      const rep = structuredClone(h.defaultReport) as {
        findings: Record<string, unknown>[];
        occurrences: Record<string, unknown>[];
      };
      const extra = structuredClone(rep.occurrences[0]);
      extra.id = "o_extra";
      extra.ordinal = 200;
      extra.raw_text = "UNRELATED-MARKER-7";
      extra.normalized_text = "UNRELATED-MARKER-7";
      rep.occurrences.push(extra);
      const finding = structuredClone(rep.findings[0]);
      finding.id = "f_extra";
      finding.title = "Unrelated region reading";
      finding.occurrence_ids = ["o_extra"];
      finding.region_id = null;
      rep.findings.push(finding);
      h.setSource(rep);
    });

    const picker = page.getByTestId("export-findings");
    await expect(picker).toBeVisible();
    await expect(picker.getByRole("checkbox")).toHaveCount(2);

    // Deselect the second finding; export.
    await page.getByTestId("finding-check-f_extra").uncheck();
    const json = await downloadJson(page);

    // Only the chosen finding survives; its unrelated occurrence text is absent.
    expect(json.findings.map((f) => f.id)).toEqual(["f_amount"]);
    const rawTexts = json.occurrences.map((o) => o.raw_text);
    expect(rawTexts).not.toContain("UNRELATED-MARKER-7");
    expect(json.occurrences.map((o) => o.id)).not.toContain("o_extra");

    // The deselection stays disclosed, not silent — count-level in the
    // payload (the contract's `omissions` strings never name excluded ids),
    // and the panel names exactly which finding was deselected.
    expect(json.export.omissions.join(" ")).toContain(
      "1 finding(s) excluded by selection",
    );
    await expect(page.getByTestId("deselected-findings")).toContainText("f_extra");

    // Check coverage and produced counts are the run's own truth — the
    // subset export never rewrites how much evidence was produced.
    const native = json.checks.find((c) => c.id === "c_native");
    expect(native?.produced_occurrence_count).toBe(118);
    expect(json.checks.map((c) => c.id).sort()).toEqual([
      "c_alignment",
      "c_native",
      "c_ocr",
    ]);

    // Privacy defaults: no source bytes, no filename, no notes.
    expect(json.assets.some((a) => a.purpose === "source_pdf")).toBe(false);
    expect(json.document.display_name).toBeNull();
    expect(json.annotations).toEqual([]);
  });

  test("notes enter the export only through explicit opt-in, never as readings", async ({
    page,
  }) => {
    await openExportPreview(page);
    await withHarness(page, (h) => h.setSource(h.defaultReport));

    // Default: the recorded note stays out and the exclusion is disclosed.
    const offJson = await downloadJson(page);
    expect(offJson.annotations).toEqual([]);
    expect(offJson.export.omissions.join(" ")).toContain("Notes excluded");
    const offOccurrenceIds = offJson.occurrences.map((o) => o.id).sort();

    await page.getByRole("checkbox", { name: "Include my notes" }).check();
    const onJson = await downloadJson(page);
    expect(onJson.annotations).toHaveLength(1);
    expect(onJson.annotations[0].id).toBe("a_note_1");
    expect(onJson.annotations[0].finding_id).toBe("f_amount");
    expect(onJson.annotations[0].origin).toBe("human_entered");
    expect(onJson.annotations[0].text).toContain("Review discrepancy");

    // The note never becomes a machine reading.
    expect(onJson.occurrences.map((o) => o.id).sort()).toEqual(offOccurrenceIds);
    expect(
      onJson.occurrences.some((o) => o.raw_text.includes("Review discrepancy")),
    ).toBe(false);
  });

  test("full-source inclusion is explicit and warned; absent by default", async ({ page }) => {
    await openExportPreview(page);
    await withHarness(page, (h) => h.setSource(h.defaultReport, h.defaultPdfBytes));

    // Unchecked: no source bytes in the bundle, no included-source claim.
    const offJson = await downloadJson(page);
    expect(offJson.assets.some((a) => a.purpose === "source_pdf")).toBe(false);

    // The warning copy only becomes required once the user opts in.
    const sourceBox = page.getByRole("checkbox", { name: "Include the original PDF" });
    await sourceBox.check();
    await expect(
      page.getByText(/every page and any hidden content/i).first(),
    ).toBeVisible();
    await expect(page.getByText(/not a safe redaction/i).first()).toBeVisible();

    const onJson = await downloadJson(page);
    expect(onJson.assets.some((a) => a.purpose === "source_pdf")).toBe(true);
  });

  test("crop preview shows the real excerpt and the not-a-redaction disclosure", async ({
    page,
  }) => {
    await openExportPreview(page);
    await withHarness(page, (h) => h.setSource(h.defaultReport));

    // The delivered example carries one crop asset; the panel renders the
    // actual pixels (decoded data URL), not a placeholder.
    const strip = page.getByTestId("crop-preview");
    await expect(strip).toBeVisible();
    const img = page.getByTestId("crop-image-a_crop");
    await expect(img).toBeVisible();
    await expect(img).toHaveAttribute("src", /^data:image\/png;base64,/);
    await expect(
      strip.getByText(/Cropping is not a redaction guarantee/i),
    ).toBeVisible();
  });
});

test.describe("T23 authored notes", () => {
  test("finding deselection survives note edits — excluded evidence never leaks back", async ({
    page,
  }) => {
    // Review F1 regression: editing notes rebuilds the export source; the
    // user's deselection must persist across that rebuild or the next
    // download would silently contain the excluded finding's text.
    await page.goto(`${harness.base}/#/workspace`);
    await page.locator("#input-import-report").setInputFiles(EXAMPLE_REPORT);
    await expect(page.getByTestId("export-findings")).toBeVisible({ timeout: 30_000 });

    // Deselect the only finding, then author a note on it (the card stays
    // selectable in the viewer; the note is recorded against it).
    await page.getByTestId("finding-check-f_amount").uncheck();
    const card = page.locator("#finding-item-f_amount");
    await card.click();
    await page.getByTestId("note-input").fill("Excluded on purpose");
    await page.getByTestId("note-add").click();
    await expect(page.getByTestId("finding-notes")).toBeVisible();

    // The rebuild must not resurrect the deselected finding.
    await expect(page.getByTestId("finding-check-f_amount")).not.toBeChecked();
    await expect(page.getByTestId("deselected-findings")).toContainText("f_amount");

    await page.getByRole("checkbox", { name: "Include my notes" }).check();
    // The note rides out with its deselected finding — disclosed, not silent.
    await expect(page.getByTestId("notes-excluded-with-findings")).toContainText("1 note(s)");

    let dl = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download portable JSON" }).click();
    let text = await (await dl).createReadStream().then(async (s) => {
      const chunks: Buffer[] = [];
      for await (const c of s) chunks.push(c as Buffer);
      return Buffer.concat(chunks).toString("utf8");
    });
    let json = JSON.parse(text) as DownloadedJson;
    expect(json.findings.map((f) => f.id)).not.toContain("f_amount");
    expect(json.annotations).toEqual([]);

    // Re-selecting restores both the finding and its note.
    await page.getByTestId("finding-check-f_amount").check();
    dl = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download portable JSON" }).click();
    text = await (await dl).createReadStream().then(async (s) => {
      const chunks: Buffer[] = [];
      for await (const c of s) chunks.push(c as Buffer);
      return Buffer.concat(chunks).toString("utf8");
    });
    json = JSON.parse(text) as DownloadedJson;
    expect(json.findings.map((f) => f.id)).toContain("f_amount");
    expect(json.annotations.some((a) => a.text.includes("Excluded on purpose"))).toBe(true);
  });

  test("a note typed in the viewer exports only on opt-in, as human_entered", async ({
    page,
  }) => {
    await page.goto(`${harness.base}/#/workspace`);

    // Import the delivered example report through the real file input.
    await page.locator("#input-import-report").setInputFiles(EXAMPLE_REPORT);
    await expect(page.getByTestId("export-findings")).toBeVisible({ timeout: 30_000 });

    // Select the finding card, then author a note through the notes UI.
    const card = page.locator("#finding-item-f_amount");
    await card.click();
    const notes = page.getByTestId("finding-notes");
    await expect(notes).toBeVisible();
    await page.getByTestId("note-input").fill("Glyph shape looks off here");
    await page.getByTestId("note-add").click();
    await expect(notes.getByText("Glyph shape looks off here")).toBeVisible();

    // The notes opt-in is enabled once a note exists.
    const notesBox = page.getByRole("checkbox", { name: "Include my notes" });
    await expect(notesBox).toBeEnabled();

    // Default export: the authored note stays out.
    let dl = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download portable JSON" }).click();
    let text = await (await dl).createReadStream().then(async (s) => {
      const chunks: Buffer[] = [];
      for await (const c of s) chunks.push(c as Buffer);
      return Buffer.concat(chunks).toString("utf8");
    });
    let json = JSON.parse(text) as DownloadedJson;
    expect(json.annotations).toEqual([]);

    // Opt-in: the note lands in `annotations` as human_entered — and is
    // absent from `occurrences` (it never becomes a machine reading).
    await notesBox.check();
    dl = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download portable JSON" }).click();
    text = await (await dl).createReadStream().then(async (s) => {
      const chunks: Buffer[] = [];
      for await (const c of s) chunks.push(c as Buffer);
      return Buffer.concat(chunks).toString("utf8");
    });
    json = JSON.parse(text) as DownloadedJson;
    const note = json.annotations.find((a) => a.text.includes("Glyph shape"));
    expect(note).toBeDefined();
    expect(note?.origin).toBe("human_entered");
    expect(note?.finding_id).toBe("f_amount");
    expect(
      json.occurrences.some((o) => o.raw_text.includes("Glyph shape")),
    ).toBe(false);
  });
});
