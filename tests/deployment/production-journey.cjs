/* Independent production-build journey driver (test-only, lives outside public source).
 * Drives the wrangler-served production build at PROD_BASE_URL through the core
 * user journey with hard assertions on identity and content. */
const pwModule = process.env.PLAYWRIGHT_MODULE
  ? require(process.env.PLAYWRIGHT_MODULE)
  : require("@playwright/test");
const { chromium } = pwModule;
const { createHash } = require("crypto");
const fs = require("fs");
const path = require("path");

const BASE = process.env.PROD_BASE_URL || "http://127.0.0.1:41820";
const ROOT = path.resolve(__dirname, "..", "..");
const FIXTURE = path.join(ROOT, "fixtures", "public", "mapping-amount.pdf");
const FIXTURE_SHA = "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80";
const EVIDENCE = path.join(__dirname, "evidence");
const results = [];
function record(step, ok, detail) {
  results.push({ step, ok, detail: detail || "" });
  console.log(`${ok ? "PASS" : "FAIL"} ${step}${detail ? " — " + detail : ""}`);
  if (!ok) process.exitCode = 1;
}

(async () => {
  const recorded = JSON.parse(fs.readFileSync(path.join(ROOT, ".private/distribution/dist-manifest.json"), "utf8"));
  const recordedIndex = recorded.files.find(f => f.path === "apps/web/dist/index.html");
  const recordedScript = recorded.files.find(f => /assets\/index-.*\.js$/.test(f.path));
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // ---- production-output identity ----
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  const scriptSrc = await page.getAttribute("script[type=module][src]", "src");
  record("prod: entry script matches recorded hashed asset",
    scriptSrc === "/" + recordedScript.path.replace("apps/web/dist/", ""),
    scriptSrc);
  const hooks = await page.evaluate(() => {
    return typeof __INKFLIP_TEST_HOOKS__ === "undefined" ? "absent" : String(__INKFLIP_TEST_HOOKS__);
  });
  record("prod: test hooks absent in production bundle", hooks === "absent", "hooks=" + hooks);
  const cspResp = await page.request.get(BASE + "/index.html");
  const csp = cspResp.headers()["content-security-policy"] || "";
  record("headers: CSP present on served page", /default-src 'none'/.test(csp), csp.slice(0, 60) + "…");

  // ---- Journey A: captured example ----
  await page.click("#btn-try-example");
  await page.waitForSelector("[id^=finding-item-]", { timeout: 30000 });
  const findingText = await page.locator("[id^=finding-item-]").first().innerText();
  record("example: finding card shows real disagreement content",
    /amount|reads|\$/.test(findingText), findingText.split("\n")[0]);
  // occurrence selection: click first finding, expect evidence/selection response
  await page.locator("[id^=finding-item-]").first().click();
  await page.waitForTimeout(300);
  const evidenceVisible = await page.locator("[id^=finding-item-]").count();
  record("example: findings listed", evidenceVisible > 0, `${evidenceVisible} findings`);

  // ---- Journey B: open own local fixture PDF ----
  await page.click("#btn-close-doc");
  await page.waitForSelector("#input-open-pdf", { state: "attached", timeout: 30000 });
  await page.setInputFiles("#input-open-pdf", FIXTURE);
  await page.waitForSelector("[data-testid=doc-label]", { timeout: 30000 });
  // open stage shows the recorded digest metadata before the run starts
  await page.waitForFunction(
    () => {
      const el = document.querySelector("[data-testid=doc-meta]");
      return el && /sha256/i.test(el.textContent || "");
    },
    { timeout: 30000 },
  );
  const ownDocMeta = await page.textContent("[data-testid=doc-meta]");
  record("own PDF: opened with recorded digest metadata",
    /sha256/i.test(ownDocMeta || ""), (ownDocMeta || "").trim().slice(0, 80));
  // the run button is labeled by the app's selection copy ("Compare selected pages")
  await page.waitForSelector("[data-testid=start-run]", { state: "visible", timeout: 30000 });
  await page.click("[data-testid=start-run]");
  await page.waitForSelector("[id^=finding-item-]", { timeout: 90000 });

  // ---- export default JSON (no source) ----
  const jsonButton = page.getByRole("button", { name: "Download portable JSON" });
  await jsonButton.waitFor({ state: "visible", timeout: 60000 });
  await page.waitForFunction(() => {
    const buttons = [...document.querySelectorAll("button")];
    const b = buttons.find(x => /Download portable JSON/.test(x.textContent || ""));
    return b && !b.disabled;
  }, { timeout: 90000 });
  const exportDefault = page.waitForEvent("download", { timeout: 60000 });
  await jsonButton.click();
  const dl = await exportDefault;
  const defaultPath = path.join(EVIDENCE, "export-default.json");
  await dl.saveAs(defaultPath);
  const defaultJson = JSON.parse(fs.readFileSync(defaultPath, "utf8"));
  const defaultStr = JSON.stringify(defaultJson);
  const defaultHasSource = /source_pdf|embedded.*pdf|"bytes":\s*"JVBERi/.test(defaultStr);
  record("export default: report downloaded without embedded source bytes",
    !defaultHasSource, "bytes=" + defaultStr.length);
  const defaultId = defaultJson.report_id || (defaultJson.identity && defaultJson.identity.report_id);
  record("export default: report identity present", Boolean(defaultId), String(defaultId).slice(0, 20) + "…");

  // ---- source opt-in export: decoded bytes hash must match active document ----
  const sourceToggle = page.getByLabel("Include the original PDF");
  await sourceToggle.waitFor({ state: "visible", timeout: 60000 });
  await sourceToggle.check();
  await page.waitForFunction(() => {
    const buttons = [...document.querySelectorAll("button")];
    const b = buttons.find(x => /Download portable JSON/.test(x.textContent || ""));
    return b && !b.disabled;
  }, { timeout: 90000 });
  const exportSource = page.waitForEvent("download", { timeout: 60000 });
  await page.getByRole("button", { name: "Download portable JSON" }).click();
  const dl2 = await exportSource;
  const sourcePath = path.join(EVIDENCE, "export-with-source.json");
  await dl2.saveAs(sourcePath);
  const sourceJson = JSON.parse(fs.readFileSync(sourcePath, "utf8"));
  const sourceStr = JSON.stringify(sourceJson);
  let embeddedSha = null;
  const candidates = sourceStr.match(/"([A-Za-z0-9+/=]{200,})"/g) || [];
  for (const cand of candidates) {
    const raw = cand.slice(1, -1);
    try {
      const decoded = Buffer.from(raw, "base64");
      if (decoded.subarray(0, 5).toString() === "%PDF-") {
        embeddedSha = createHash("sha256").update(decoded).digest("hex");
        break;
      }
    } catch {}
  }
  record("source opt-in: embedded original bytes hash matches active document",
    embeddedSha === FIXTURE_SHA,
    "embedded=" + (embeddedSha || "none").slice(0, 16) + "… expected=" + FIXTURE_SHA.slice(0, 16) + "…");

  // ---- neighbor: Help/return preserves the live workspace ----
  await page.click("#btn-header-help");
  await page.waitForTimeout(400);
  await page.click("#btn-help-back-workspace");
  await page.waitForTimeout(400);
  const liveTitle = await page.textContent("#workspace-doc-title");
  record("neighbor: Help/return preserves the live workspace",
    /mapping-amount/.test(liveTitle || ""), (liveTitle || "").trim());

  // ---- neighbor: tampered source-bearing report rejected, live report kept ----
  const tampered = JSON.parse(fs.readFileSync(sourcePath, "utf8"));
  const tamperedStr2 = JSON.stringify(tampered).replace(
    /"([0-9a-f]{64})"/, '"0000000000000000000000000000000000000000000000000000000000000000"');
  const tamperedPath = path.join(EVIDENCE, "tampered-with-source.json");
  fs.writeFileSync(tamperedPath, tamperedStr2);
  await page.setInputFiles("#input-import-report", tamperedPath);
  // Importing while a report is open raises the replace-confirmation modal.
  // Confirming ("Clear and open file") proceeds to validation, which rejects
  // the tampered digest (HASH: Report digest mismatch) and keeps the live
  // workspace. Either path must leave the live report intact.
  const confirmBtn = page.getByRole("button", { name: "Clear and open file" });
  const errEl = page.locator("#import-error");
  await Promise.race([
    confirmBtn.waitFor({ state: "visible", timeout: 20000 }).then(() => confirmBtn.click()),
    errEl.waitFor({ state: "visible", timeout: 20000 }),
  ]).catch(() => {});
  await page.waitForTimeout(1500);
  const importError = await errEl.isVisible().catch(() => false);
  const keptTitle = await page.textContent("#workspace-doc-title").catch(() => "");
  record("neighbor: tampered source-bearing report rejected; live report kept",
    importError && /mapping-amount/.test(keptTitle || ""),
    `error visible=${importError}; workspace title=${(keptTitle || "").trim()}`);
  // dismiss the still-open replace dialog so the workspace stays usable
  await page.keyboard.press("Escape");
  await page.waitForTimeout(400);
  const backdropGone = !(await page.locator("[data-testid=modal-backdrop]").isVisible().catch(() => false));
  if (!backdropGone) {
    const cancel = page.locator("[data-testid=modal-backdrop] button", { hasText: /cancel|keep/i });
    if (await cancel.count()) await cancel.first().click();
    await page.waitForTimeout(300);
  }

  // ---- reimport the default (no-source) export ----
  await page.click("#btn-close-doc");
  await page.waitForSelector("#input-import-report", { state: "attached", timeout: 30000 });
  await page.setInputFiles("#input-import-report", defaultPath);
  await page.waitForSelector("[id^=finding-item-]", { timeout: 60000 });
  const reTitle = await page.textContent("#workspace-doc-title");
  record("reimport default: report reopens with findings",
    (reTitle || "").trim().length > 0, (reTitle || "").trim());

  await browser.close();
  await browser.close();
  fs.writeFileSync(path.join(EVIDENCE, "journey-results.json"),
    JSON.stringify({ base: BASE, results, at: new Date().toISOString() }, null, 2));
  console.log("evidence written to", EVIDENCE);
})().catch(e => { console.error("DRIVER ERROR:", e); process.exit(1); });
