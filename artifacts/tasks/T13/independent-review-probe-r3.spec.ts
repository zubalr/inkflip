import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect } from "@playwright/test";

/** Round-3 independent adversarial probes for T13. */

const WEB_ROOT = path.resolve(process.cwd(), "apps/web");
let viteServer: any;
let baseUrl: string;

test.beforeAll(async () => {
  const viteModulePath = path.resolve(WEB_ROOT, "node_modules/vite/dist/node/index.js");
  const { createServer } = await import(pathToFileURL(viteModulePath).href);
  viteServer = await createServer({
    root: WEB_ROOT,
    server: { port: 0, strictPort: false, fs: { allow: [path.resolve(process.cwd())] } },
    logLevel: "silent",
  });
  await viteServer.listen();
  baseUrl = viteServer.resolvedUrls.local[0].replace(/\/$/, "");
});
test.afterAll(async () => {
  if (viteServer) await viteServer.close();
});

const mk = (dir: string, name: string, content: string | Buffer) => {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  return { dir, name, content };
};

test.describe("T13 round-3 adversarial probes", () => {
  test("A: valid PDF shows honest notice, NO canned findings; oversized exe rejected", async ({
    page,
  }) => {
    const fs = await import("node:fs");
    const dir = path.resolve(process.cwd(), "test-results");
    fs.mkdirSync(dir, { recursive: true });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    // valid %PDF header, plausible size
    const pdfPath = path.join(dir, "my-tax-return.pdf");
    fs.writeFileSync(pdfPath, "%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n");
    await page.locator("#input-open-pdf").setInputFiles(pdfPath);
    await page.waitForTimeout(600);
    // honest state: no viewer, no findings, explicit notice
    await expect(page.locator("#viewer-stage")).toHaveCount(0);
    await expect(page.locator("#findings-nav-list")).toHaveCount(0);
    await expect(page.locator("#pdf-received-notice")).toBeVisible();
    console.log("notice:", await page.locator("#pdf-received-notice").textContent());
    // title must NOT claim the file became the doc
    const header = await page.locator("header").first().textContent();
    console.log("header:", header);
    expect(header).not.toContain("3 findings");

    // 25MB non-PDF named .pdf -> size/type rejection, no mount
    const bigPath = path.join(dir, "x.pdf");
    fs.writeFileSync(bigPath, Buffer.alloc(25 * 1024 * 1024, 0x4d)); // 25MB of 'M'
    await page.locator("#input-open-pdf").setInputFiles(bigPath);
    await page.waitForTimeout(600);
    await expect(page.locator("#import-error")).toBeVisible();
    console.log("big file error:", await page.locator("#import-error").textContent());
    await expect(page.locator("#viewer-stage")).toHaveCount(0);
    await expect(page.locator("#pdf-received-notice")).toHaveCount(0);
  });

  test("B: canonical report containing a page-level (polygon:null) occurrence", async ({ page }) => {
    const fs = await import("node:fs");
    const dir = path.resolve(process.cwd(), "test-results");
    fs.mkdirSync(dir, { recursive: true });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    // Report shaped like the app's own EXAMPLE_DOC (has polygon:null page-level occ)
    const report = {
      document: { display_name: "page-level-report" },
      pages: [
        {
          index: 0,
          media_box: [0, 0, 612, 792],
          crop_box: [0, 0, 612, 792],
          effective_view_box: [0, 0, 612, 792],
          box_source: "media_box",
          user_unit: 1,
          rotation: 0,
          canonical_size_pt: [612, 792],
          raw_to_canonical_transform_id: "t0",
          limitations: [],
        },
      ],
      readers: [],
      occurrences: [
        {
          id: "o1",
          reader_id: "r1",
          page_index: 0,
          ordinal: 1,
          raw_text: "page-level note",
          normalized_text: "page-level note",
          normalization_map: [],
          geometry: {
            precision: "page_only",
            space: "canonical_page",
            polygon: null,
            transform_ids: [],
            basis: "dict",
          },
          engine_score: null,
          source_asset_id: null,
          raw_source_locator: "p0:d",
          limitations: [],
        },
      ],
      findings: [
        {
          id: "f1",
          kind: "observed_structure",
          title: "Page-level finding",
          explanation: "x",
          page_index: 0,
          occurrence_ids: ["o1"],
          check_ids: [],
          alignment: "page_level",
          region_id: null,
          priority: "informational",
          basis: "x",
          limitations: [],
        },
      ],
    };
    const p = path.join(dir, "page-level-report.json");
    fs.writeFileSync(p, JSON.stringify(report));
    await page.locator("#input-import-report").setInputFiles(p);
    await page.waitForTimeout(700);
    const stage = await page.locator("#viewer-stage").count();
    const err = await page.locator("#import-error").count();
    const errText = err ? await page.locator("#import-error").textContent() : null;
    console.log("page-level import: stage=", stage, "err=", err, errText);
    // CANONICAL: polygon:null is valid per schema -> should mount (if rejected => bug)
  });

  test("C: malformed shapes fail closed, never unmount app", async ({ page }) => {
    const fs = await import("node:fs");
    const dir = path.resolve(process.cwd(), "test-results");
    fs.mkdirSync(dir, { recursive: true });
    const rootKids = () =>
      page.evaluate(() => document.getElementById("root")?.childElementCount ?? -1);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    const cases: Array<[string, object | string]> = [
      ["empty-pages", { pages: [], findings: [] }],
      ["occ-no-geometry", { pages: [{ index: 0, canonical_size_pt: [612, 792] }], findings: [], occurrences: [{ id: "o", page_index: 0 }] }],
      ["page-missing-size", { pages: [{ index: 0 }], findings: [] }],
      ["finding-no-id", { pages: [{ index: 0, canonical_size_pt: [612, 792] }], findings: [{ title: "x" }] }],
      ["pages-not-array", { pages: "x", findings: [] }],
      ["primitive", "42"],
    ];
    for (const [name, obj] of cases) {
      const p = path.join(dir, `${name}.json`);
      fs.writeFileSync(p, typeof obj === "string" ? obj : JSON.stringify(obj));
      await page.locator("#input-import-report").setInputFiles(p);
      await page.waitForTimeout(350);
      const kids = await rootKids();
      const stage = await page.locator("#viewer-stage").count();
      const errVisible = await page.locator("#import-error").count();
      console.log(`${name}: rootKids=${kids} stage=${stage} err=${errVisible}`);
      expect(kids).toBeGreaterThan(0); // app must never unmount
      expect(stage).toBe(0); // degenerate must not mount viewer
      expect(errVisible).toBe(1); // must surface explicit error
    }
  });

  test("D: regression — real report import + drop path + 360px home/workspace", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto(`${baseUrl}/#/`);
    await page.waitForSelector("#hero-headline");
    let ov = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    console.log("home360 overflow:", ov);
    expect(ov).toBeLessThanOrEqual(1);

    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');
    const fs = await import("node:fs");
    const reportBytes = fs.readFileSync(
      path.resolve(process.cwd(), "planning/contracts/examples/valid/native-evidence.inkflip.json"),
    );
    const dt = await page.evaluateHandle((bytes) => {
      const d = new DataTransfer();
      d.items.add(
        new File([new Uint8Array(bytes)], "evidence.inkflip.json", { type: "application/json" }),
      );
      return d;
    }, Array.from(reportBytes));
    await page.locator('[data-testid="file-drop"]').dispatchEvent("drop", { dataTransfer: dt });
    await page.waitForSelector("#viewer-stage");
    await expect(page.locator("#document-paper")).toBeVisible();

    // 360px workspace overflow check with doc mounted
    await page.setViewportSize({ width: 360, height: 740 });
    ov = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    console.log("workspace360 overflow:", ov);
    expect(ov).toBeLessThanOrEqual(1);
  });
});
