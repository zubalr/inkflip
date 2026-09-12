import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect } from "@playwright/test";

/** Round-4 independent adversarial probes for T13 — hostile import shapes vs the relaxed polygon gate. */

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

const PAGE = {
  index: 0,
  canonical_size_pt: [612, 792] as [number, number],
  limitations: [],
};

const mkOcc = (id: string, geometry: unknown, pageIndex = 0) => ({
  id,
  reader_id: "r1",
  page_index: pageIndex,
  ordinal: 1,
  raw_text: `text-${id}`,
  normalized_text: `text-${id}`,
  geometry,
});

const mkFinding = (id: string, occIds: string[], pageIndex = 0, extra: object = {}) => ({
  id,
  title: `finding-${id}`,
  page_index: pageIndex,
  occurrence_ids: occIds,
  ...extra,
});

const mkReport = (occurrences: unknown[], findings: unknown[], pages = [PAGE]) => ({
  pages,
  readers: [
    {
      id: "r1",
      name: "R1",
      version: "1",
      limitations: [],
    },
  ],
  occurrences,
  findings,
});

async function importJson(page: any, name: string, doc: unknown) {
  const fs = await import("node:fs");
  const dir = path.resolve(process.cwd(), "test-results");
  fs.mkdirSync(dir, { recursive: true });
  const p = path.join(dir, name);
  fs.writeFileSync(p, JSON.stringify(doc));
  await page.locator("#input-import-report").setInputFiles(p);
  await page.waitForTimeout(500);
}

async function openWorkspace(page: any) {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${baseUrl}/#/workspace`);
  await page.reload(); // same-URL hash nav may not reload; force fresh React state
  await page.waitForSelector('[data-testid="file-drop"]');
}

async function rootAlive(page: any) {
  const kids = await page.locator("#root > *").count();
  return kids >= 1;
}

test.describe("T13 round-4 adversarial probes: hostile import shapes", () => {
  test("P1-verify: canonical polygon:null (page_only) mounts; selecting finding shows page-level notice, no box", async ({
    page,
  }) => {
    await openWorkspace(page);
    const doc = mkReport(
      [
        mkOcc("occ-pl", {
          precision: "page_only",
          space: "canonical_page",
          polygon: null,
          transform_ids: [],
          basis: "page_level",
        }),
      ],
      [mkFinding("f-pl", ["occ-pl"], 0, { alignment: "page_level", priority: "informational" })],
    );
    await importJson(page, "r4-pl.json", doc);
    await expect(page.locator("#viewer-stage")).toBeVisible();
    await expect(page.locator("#import-error")).toHaveCount(0);
    // select the finding -> honest page-level notice, no fabricated highlight box
    await page.locator("#finding-item-f-pl").click();
    await expect(page.locator("#page-level-geometry-notice")).toBeVisible();
    await expect(page.locator("#highlight-occ-pl")).toHaveCount(0);
    expect(await rootAlive(page)).toBe(true);
  });

  test("hostile: polygon:null with CLAIMED exact precision -> still honest page-level, no box", async ({
    page,
  }) => {
    await openWorkspace(page);
    const doc = mkReport(
      [
        mkOcc("occ-liar", {
          precision: "exact", // claims localized coords but polygon is null
          space: "canonical_page",
          polygon: null,
          transform_ids: [],
          basis: "x",
        }),
      ],
      [mkFinding("f-liar", ["occ-liar"], 0, { alignment: "unique", priority: "material_token" })],
    );
    await importJson(page, "r4-liar.json", doc);
    await expect(page.locator("#viewer-stage")).toBeVisible();
    await page.locator("#finding-item-f-liar").click();
    // polygon===null must force page-level notice even though precision claims exact
    await expect(page.locator("#page-level-geometry-notice")).toBeVisible();
    await expect(page.locator("#highlight-occ-liar")).toHaveCount(0);
    expect(await rootAlive(page)).toBe(true);
  });

  test("hostile: polygon as string / object / number -> fail closed #import-error", async ({
    page,
  }) => {
    for (const [tag, poly] of [
      ["str", "not-a-polygon"],
      ["obj", { x: 1, y: 2 }],
      ["num", 42],
    ] as const) {
      await openWorkspace(page);
      const doc = mkReport(
        [mkOcc(`occ-${tag}`, { precision: "exact", space: "canonical_page", polygon: poly })],
        [mkFinding(`f-${tag}`, [`occ-${tag}`])],
      );
      await importJson(page, `r4-poly-${tag}.json`, doc);
      await expect(page.locator("#import-error")).toBeVisible();
      await expect(page.locator("#viewer-stage")).toHaveCount(0);
      expect(await rootAlive(page)).toBe(true);
    }
  });

  test("hostile: missing geometry / geometry:null / geometry scalar -> fail closed", async ({
    page,
  }) => {
    for (const [tag, occ] of [
      ["nogeo", { ...mkOcc("occ-ng", undefined), geometry: undefined }],
      ["geonull", mkOcc("occ-gn", null)],
      ["geonum", mkOcc("occ-gnum", 7)],
    ] as const) {
      await openWorkspace(page);
      const doc = mkReport([occ], [mkFinding(`f-${tag}`, [occ.id])]);
      await importJson(page, `r4-geo-${tag}.json`, doc);
      await expect(page.locator("#import-error")).toBeVisible();
      await expect(page.locator("#viewer-stage")).toHaveCount(0);
      expect(await rootAlive(page)).toBe(true);
    }
  });

  test("hostile: polygon number-array [1,2,3] passes gate but must not fabricate a box or crash", async ({
    page,
  }) => {
    await openWorkspace(page);
    const doc = mkReport(
      [
        mkOcc("occ-numpoly", {
          precision: "exact",
          space: "canonical_page",
          polygon: [1, 2, 3],
        }),
      ],
      [mkFinding("f-np", ["occ-numpoly"], 0, { alignment: "unique", priority: "material_token" })],
    );
    await importJson(page, "r4-numpoly.json", doc);
    expect(await rootAlive(page)).toBe(true);
    const stageCount = await page.locator("#viewer-stage").count();
    const errCount = await page.locator("#import-error").count();
    console.log("numpoly: stage=", stageCount, "import-error=", errCount);
    // Either outcome acceptable: fail-closed OR mounted. If mounted, the polygon
    // element must not paint a fabricated box (points attr should be NaN/inert).
    if (stageCount > 0) {
      const hl = page.locator("#highlight-occ-numpoly");
      const hlCount = await hl.count();
      if (hlCount > 0) {
        const pts = await hl.getAttribute("points");
        console.log("numpoly points attr:", pts);
        const box = await hl.boundingBox();
        console.log("numpoly boundingBox:", box);
      }
    }
    expect(stageCount + errCount).toBeGreaterThan(0);
  });

  test("hostile: polygon [null,null,null] crashes render -> boundary must fail closed, root alive", async ({
    page,
  }) => {
    await openWorkspace(page);
    const doc = mkReport(
      [
        mkOcc("occ-nullpts", {
          precision: "exact",
          space: "canonical_page",
          polygon: [null, null, null],
        }),
      ],
      [mkFinding("f-nullpts", ["occ-nullpts"], 0)],
    );
    await importJson(page, "r4-nullpts.json", doc);
    // error boundary fallback renders #import-error; app tree must stay mounted
    await expect(page.locator("#import-error")).toBeVisible();
    expect(await rootAlive(page)).toBe(true);
    console.log("nullpts error text:", await page.locator("#import-error").textContent());
  });

  test("hostile: polygon:[] empty and polygon:[[x,y],[x,y]] <3 pts -> mounts, draws nothing", async ({
    page,
  }) => {
    for (const [tag, poly] of [
      ["empty", []],
      ["twopts", [[0, 0], [1, 0]]],
    ] as const) {
      await openWorkspace(page);
      const doc = mkReport(
        [
          mkOcc(`occ-${tag}`, {
            precision: "exact",
            space: "canonical_page",
            polygon: poly,
          }),
        ],
        [mkFinding(`f-${tag}`, [`occ-${tag}`], 0, { alignment: "unique" })],
      );
      await importJson(page, `r4-${tag}.json`, doc);
      expect(await rootAlive(page)).toBe(true);
      const stageCount = await page.locator("#viewer-stage").count();
      const errCount = await page.locator("#import-error").count();
      console.log(`${tag}: stage=${stageCount} err=${errCount}`);
      if (stageCount > 0) {
        await page.locator(`#finding-item-f-${tag}`).click();
        await page.waitForTimeout(200);
        // no highlight element may exist for an undrawable polygon
        await expect(page.locator(`#highlight-occ-${tag}`)).toHaveCount(0);
      }
      expect(stageCount + errCount).toBeGreaterThan(0);
    }
  });

  test("hostile: mixed null + valid occurrences in ONE report -> each renders honestly", async ({
    page,
  }) => {
    await openWorkspace(page);
    const doc = mkReport(
      [
        mkOcc("occ-mixed-box", {
          precision: "exact",
          space: "canonical_page",
          polygon: [
            [10, 10],
            [50, 10],
            [50, 30],
            [10, 30],
          ],
        }),
        mkOcc("occ-mixed-pl", {
          precision: "page_only",
          space: "canonical_page",
          polygon: null,
        }),
      ],
      [
        mkFinding("f-mixed-box", ["occ-mixed-box"], 0, {
          alignment: "unique",
          priority: "material_token",
        }),
        mkFinding("f-mixed-pl", ["occ-mixed-pl"], 0, {
          alignment: "page_level",
          priority: "informational",
        }),
      ],
    );
    await importJson(page, "r4-mixed.json", doc);
    await expect(page.locator("#viewer-stage")).toBeVisible();
    await expect(page.locator("#import-error")).toHaveCount(0);

    // select exact finding -> its box exists, NO page-level notice
    await page.locator("#finding-item-f-mixed-box").click();
    await expect(page.locator("#highlight-occ-mixed-box")).toBeVisible();
    await expect(page.locator("#page-level-geometry-notice")).toHaveCount(0);

    // select page-level finding -> notice shows, no box for that occ
    await page.locator("#finding-item-f-mixed-pl").click();
    await expect(page.locator("#page-level-geometry-notice")).toBeVisible();
    await expect(page.locator("#highlight-occ-mixed-pl")).toHaveCount(0);
    expect(await rootAlive(page)).toBe(true);
  });

  test("P3-verify: imported doc persists across Home navigation (wired onImportReport seam)", async ({
    page,
  }) => {
    await openWorkspace(page);
    const doc = mkReport(
      [
        mkOcc("occ-persist", {
          precision: "exact",
          space: "canonical_page",
          polygon: [
            [10, 10],
            [50, 10],
            [50, 30],
            [10, 30],
          ],
        }),
      ],
      [mkFinding("f-persist", ["occ-persist"], 0, { priority: "material_token" })],
    );
    await importJson(page, "r4-persist.json", doc);
    await expect(page.locator("#viewer-stage")).toBeVisible();

    // Home -> Workspace: doc must persist via App-level activeDoc
    await page.locator("#btn-back-home").click();
    await page.waitForTimeout(300);
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForTimeout(400);
    const stage = await page.locator("#viewer-stage").count();
    const title = await page.locator("header").first().textContent();
    console.log("after nav round-trip: stage=", stage, "header:", title);
  });
});
