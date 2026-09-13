/* T21 gallery smoke — committed suite: six cards render on Home and an
 * example card imports its real captured report through the app. */
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { expect, test } from "@playwright/test";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const WEB = join(ROOT, "apps", "web");

let baseUrl: string;
let viteServer: { close: () => Promise<void> } | null = null;

test.beforeAll(async () => {
  const viteModulePath = resolve(WEB, "node_modules/vite/dist/node/index.js");
  const { createServer } = (await import(pathToFileURL(viteModulePath).href)) as {
    createServer: (o: object) => Promise<{
      listen: () => Promise<void>;
      resolvedUrls: { local: string[] };
      close: () => Promise<void>;
    }>;
  };
  viteServer = await createServer({
    root: WEB,
    server: { port: 0, strictPort: false, fs: { allow: [ROOT] } },
    logLevel: "silent",
  });
  await viteServer.listen();
  baseUrl = viteServer.resolvedUrls.local[0].replace(/\/$/, "");
});

test.afterAll(async () => {
  await viteServer?.close();
});

test("gallery renders six cards; detail shows real files; open report imports", async ({ page }) => {
  await page.goto(`${baseUrl}/#/`);
  const gallery = page.getByTestId("examples-gallery");
  await expect(gallery).toBeVisible({ timeout: 15000 });
  await expect(gallery.getByRole("button")).toHaveCount(6);
  await expect(gallery.getByText("The same $100, four times")).toBeVisible();

  await page.getByTestId("example-card-duplicates").click();
  const detail = page.getByTestId("example-detail-duplicates");
  await expect(detail).toBeVisible();
  await expect(detail.getByText("duplicates-four.pdf")).toBeVisible();
  await expect(detail.getByText("tesseract.js 7.0.0")).toBeVisible();

  await page.getByTestId("open-example-duplicates").click();
  // The imported report mounts the viewer + export panel through the real
  // import gate.
  await expect(page.getByRole("region", { name: "PDF reading inspector viewer stage" })).toBeVisible({
    timeout: 30000,
  });
  await expect(page.locator("#doc-stats, [data-testid=doc-stats]")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Preview what you will export" })).toBeVisible();
  const card = page.locator("[id^=finding-item-]").first();
  await expect(card).toBeVisible();
  await card.click();
});
