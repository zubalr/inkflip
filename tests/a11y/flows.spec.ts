import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * TEST-37: Accessibility flows on the real workspace (T37).
 *
 * Acceptance criteria:
 * 1. All core flows completed without mouse.
 * 2. Focus restored — dialogs and candidate selection return focus to
 *    the originating control.
 * 3. Amount alternatives and partial coverage announced correctly.
 * 4. 400% zoom usable.
 * 5. Reduced motion honored.
 * 6. Zero serious/critical automated violations.
 *
 * Drives the public workspace (/#/workspace) through a Vite dev server:
 * - ?example=true mounts the bundled example document — ambiguous
 *   amount finding, page-level finding, order-only finding.
 * - ?example=scan imports the captured scan report through the real
 *   import gate, mounting CoveragePanel and ExportPanel.
 * - The sealed native-evidence contract example imports through
 *   #input-import-report for the partial-coverage leg (its alignment
 *   check is recorded as unsupported — 2 of 3 checks completed).
 *
 * The keyboard legs never call locator.click(). Only .focus(),
 * elementHandle.press(), page.keyboard.* and file-input setInputFiles
 * (the OS file chooser itself is native, not page UI) are used.
 */

const WEB_ROOT = path.resolve(process.cwd(), "apps/web");
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const SEALED_REPORT = path.resolve(
  process.cwd(),
  "planning/contracts/examples/valid/native-evidence.inkflip.json",
);

let viteServer: { close(): Promise<void>; resolvedUrls: { local: string[] } };
let baseUrl: string;

test.beforeAll(async () => {
  const viteModulePath = path.resolve(WEB_ROOT, "node_modules/vite/dist/node/index.js");
  const { createServer } = await import(pathToFileURL(viteModulePath).href);
  viteServer = await createServer({
    root: WEB_ROOT,
    server: {
      port: 0,
      strictPort: false,
      fs: { allow: [path.resolve(process.cwd())] },
    },
    logLevel: "silent",
  });
  await viteServer.listen();
  baseUrl = viteServer.resolvedUrls.local[0].replace(/\/$/, "");
});

test.afterAll(async () => {
  await viteServer?.close();
});

// ---------------------------------------------------------------------------

interface FocusInfo {
  id: string;
  tag: string;
  role: string | null;
  ancestorId: string;
}

async function focusedInfo(page: Page): Promise<FocusInfo> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el) return { id: "", tag: "", role: null, ancestorId: "" };
    return {
      id: el.id ?? "",
      tag: el.tagName,
      role: el.getAttribute("role"),
      ancestorId: el.closest("[id]")?.id ?? "",
    };
  });
}

/** Real Tab-key walk. Returns the ordered list of focused element ids
 *  (falling back to the nearest labelled ancestor or tag name). Stops
 *  when `stopId` holds focus or `max` presses are exhausted. */
async function tabWalk(page: Page, stopId: string, max = 120): Promise<string[]> {
  const seen: string[] = [];
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const info = await focusedInfo(page);
    seen.push(info.id || info.ancestorId || info.tag);
    if (info.id === stopId) break;
  }
  return seen;
}

/** Parse a computed transition-duration list ("0.12s", "0.01ms", comma
 *  separated) and return the longest entry in milliseconds. */
function maxDurationMs(css: string): number {
  let worst = 0;
  for (const part of css.split(",")) {
    const m = part.trim().match(/^([\d.]+)(ms|s)$/);
    if (!m) continue;
    const value = parseFloat(m[1]);
    worst = Math.max(worst, m[2] === "s" ? value * 1000 : value);
  }
  return worst;
}

const MINIMAL_PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n" +
    "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n" +
    "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n" +
    "trailer\n<< /Root 1 0 R >>\n%%EOF\n",
);

async function openScanReport(page: Page): Promise<void> {
  await page.goto(`${baseUrl}/#/workspace?example=scan`);
  await page.waitForSelector("#viewer-stage", { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Preview what you will export" })).toBeVisible({
    timeout: 30_000,
  });
}

/** The workspace is a hash-routed SPA: goto() between hashes fires
 *  hashchange in the live app instead of reloading, and a mounted
 *  document survives the route change. reload() forces a clean boot at
 *  the current URL so each leg starts from a known state. */
async function gotoFresh(page: Page, url: string): Promise<void> {
  await page.goto(url);
  await page.reload();
}

// ---------------------------------------------------------------------------

test.describe("T37: accessibility flows on the real workspace", () => {
  test("core flow: every control operated by keyboard only — walk, select, candidates, modes, export, close", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1280, height: 900 });
    await openScanReport(page);

    // -- Tab walk: header → stage → toolbar → text equivalent → findings --
    const walk = await tabWalk(page, "btn-next-finding");
    for (const expected of [
      "btn-back-home",
      "btn-header-import-report",
      "btn-header-open-pdf",
      "btn-close-doc",
      "viewer-stage",
      "tab-mode-page",
      "btn-zoom-out",
      "btn-zoom-in",
      "btn-zoom-fit",
      "btn-rotate",
      "btn-toggle-shortcuts",
      "btn-prev-finding",
      "btn-next-finding",
    ]) {
      expect(walk, `Tab order never reached #${expected}`).toContain(expected);
    }
    // The text-equivalent Select buttons sit in the Tab order between the
    // toolbar and the finding navigation — canvas content stays reachable.
    expect(walk.some((s) => s.startsWith("text-occ-"))).toBe(true);
    // Focus never fell back to the page body.
    expect(walk).not.toContain("BODY");

    // -- Select a finding with Enter on its option card --
    const firstCard = page.locator("[id^='finding-item-']").first();
    const firstCardId = (await firstCard.getAttribute("id")) as string;
    await firstCard.focus();
    await expect(firstCard).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(firstCard).toHaveAttribute("aria-current", "true");
    await expect(page.locator('[data-testid="alignment-detail"]')).toBeVisible();
    await expect(page.locator("#findings-counter")).toContainText("1 of");

    // -- Candidate pick returns focus to the originating finding card --
    const candidate = page.locator("[data-candidate-id]").first();
    await candidate.focus();
    const candidateId = (await candidate.getAttribute("data-candidate-id")) as string;
    await page.keyboard.press("Enter");
    await expect(candidate).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(`#highlight-${candidateId}`)).toHaveClass(/highlightSelected/);
    await expect(page.locator(":focus")).toHaveId(firstCardId);

    // -- Escape inside candidates returns focus without a new pick --
    await candidate.focus();
    await page.keyboard.press("Escape");
    await expect(page.locator(":focus")).toHaveId(firstCardId);

    // -- Stage shortcuts cycle the view representation --
    await page.keyboard.press("f");
    await expect(page.locator("#tab-mode-reading")).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("f");
    await expect(page.locator("#tab-mode-compare")).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("f");
    await expect(page.locator("#tab-mode-page")).toHaveAttribute("aria-selected", "true");

    // -- Zoom and rotate via focused toolbar buttons --
    const zoomIn = page.locator("#btn-zoom-in");
    await zoomIn.focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Enter");
    await expect(page.locator("#label-zoom")).toHaveText("150%");
    const rotate = page.locator("#btn-rotate");
    await rotate.focus();
    await page.keyboard.press("Enter");
    await expect(rotate).toContainText("90°");

    // -- Prev/Next finding buttons --
    const nextBtn = page.locator("#btn-next-finding");
    await nextBtn.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("#findings-counter")).toContainText("2 of");
    const prevBtn = page.locator("#btn-prev-finding");
    await prevBtn.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("#findings-counter")).toContainText("1 of");

    // -- Note drafting: typing 'f' inside the textarea must not trigger
    //    the mode shortcut (single-character keys are suppressed in text
    //    entry) --
    const noteInput = page.locator('[data-testid="note-input"]').first();
    await noteInput.focus();
    await page.keyboard.type("f note on this finding");
    await expect(page.locator("#tab-mode-page")).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Tab");
    const addNote = page.locator('[data-testid="note-add"]').first();
    await expect(addNote).toBeFocused();
    await expect(addNote).toBeEnabled();
    await page.keyboard.press("Enter");
    await expect(page.locator("[data-note-id]").first()).toBeVisible();

    // -- Export flow: inclusion checkbox + findings subset by Space --
    const firstFindingCheck = page.locator("[data-testid^='finding-check-']").first();
    await firstFindingCheck.focus();
    await expect(firstFindingCheck).toBeChecked();
    await page.keyboard.press("Space");
    await expect(firstFindingCheck).not.toBeChecked();
    // The aria-live preview publishes the deselection honestly.
    await expect(page.locator('[data-testid="deselected-findings"]')).toBeVisible();
    await page.keyboard.press("Space");
    await expect(firstFindingCheck).toBeChecked();

    const jsonBtn = page.getByRole("button", { name: "Download portable JSON" });
    await jsonBtn.focus();
    const download = page.waitForEvent("download", { timeout: 15_000 }).catch(() => null);
    await page.keyboard.press("Enter");
    await download;
    await expect(page.locator("p[role='status']")).toContainText("Report downloaded");

    // -- Close document returns to the intake surface --
    const closeBtn = page.locator("#btn-close-doc");
    await closeBtn.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator('[data-testid="file-drop"]')).toBeVisible();
    await expect(page.locator("#btn-open-pdf")).toBeVisible();
  });

  test("replace-confirmation dialog traps focus and restores it to the originating control", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 1280, height: 900 });
    await openScanReport(page);

    const trigger = page.locator("#btn-header-open-pdf");
    await trigger.focus();
    await expect(trigger).toBeFocused();

    // Offering a file while a report is open surfaces the confirmed-
    // replacement dialog. The file input is the same one the focused
    // control activates; the chooser itself is a native OS surface.
    await page.locator("#input-open-pdf").setInputFiles({
      name: "replacement.pdf",
      mimeType: "application/pdf",
      buffer: MINIMAL_PDF,
    });

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute("aria-modal", "true");

    // Focus moved into the dialog (the modal shifts it after paint).
    await expect
      .poll(async () =>
        page.evaluate(() => {
          const dlg = document.querySelector('[role="dialog"]');
          return dlg ? dlg.contains(document.activeElement) : false;
        }),
      )
      .toBe(true);

    // Focus cycles inside the modal — never escapes to the page behind it.
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("Tab");
      const inside = await page.evaluate(() => {
        const dlg = document.querySelector('[role="dialog"]');
        return dlg ? dlg.contains(document.activeElement) : false;
      });
      expect(inside).toBe(true);
    }

    // Escape dismisses; focus returns to the control that opened it.
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();

    // The explicit cancel path restores focus the same way.
    await page.locator("#input-open-pdf").setInputFiles({
      name: "replacement.pdf",
      mimeType: "application/pdf",
      buffer: MINIMAL_PDF,
    });
    await expect(dialog).toBeVisible();
    const keepBtn = dialog.getByRole("button", { name: "Keep this file" });
    await keepBtn.focus();
    await page.keyboard.press("Enter");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();

    // The report is still mounted — cancel preserved the open evidence.
    await expect(page.locator("#viewer-stage")).toBeVisible();
  });

  test("announcements: ambiguous amount alternatives reach accessible names; page-level state and partial coverage are announced", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");

    // -- Ambiguous amount finding: alternatives are individually named --
    const card = page.locator("#finding-item-finding-ambig-amounts");
    await card.focus();
    await page.keyboard.press("Enter");
    await expect(card).toHaveAttribute("aria-current", "true");

    const detail = page.locator('[data-testid="alignment-detail"]');
    await expect(detail).toHaveAttribute("data-alignment-class", "ambiguous");
    await expect(page.locator('[data-testid="alignment-class-badge"]')).toHaveText(
      "Ambiguous — candidates kept",
    );

    // Each candidate button's accessible name carries its alternative.
    await expect(page.locator('[data-testid="occ-candidate-occ-p0-dup1"]')).toHaveAccessibleName(
      /\$1,000\.00/,
    );
    await expect(page.locator('[data-testid="occ-candidate-occ-p0-dup2"]')).toHaveAccessibleName(
      /\$1,000\.00.*occurrence #2/,
    );
    await expect(page.locator('[data-testid="occ-candidate-occ-p0-pypdf1"]')).toHaveAccessibleName(
      /\$10,000\.00/,
    );

    // Keyboard selection returns focus to the finding card's activator
    // button; its accessible name carries the finding identity and the
    // ambiguous state (the alternatives themselves are announced by the
    // candidate buttons' names, asserted above).
    const dup2 = page.locator('[data-testid="occ-candidate-occ-p0-dup2"]');
    await dup2.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator(":focus")).toHaveId("finding-item-finding-ambig-amounts");
    await expect(page.locator(":focus")).toHaveAccessibleName(/Ambiguous/);
    await expect(page.locator(":focus")).toHaveAccessibleName(
      /Several locations could match this reading/,
    );

    // -- Partial coverage on the example document: the page's recorded
    //    limit is published inside the labelled text-equivalent region.
    //    (Checked while the viewer is still on page 1 — selecting the
    //    page-level finding below navigates to page 2.) --
    await expect(page.locator("#accessible-text-equivalent")).toContainText(
      "OCR verification was not run on page 0.",
    );

    // -- Page-level finding announces through a role=status live region --
    const pageLevel = page.locator("#finding-item-finding-page1-unknown");
    await pageLevel.focus();
    await page.keyboard.press("Enter");
    await expect(pageLevel).toHaveAttribute("aria-current", "true");
    const notice = page.locator("#page-level-geometry-notice");
    await expect(notice).toBeVisible();
    await expect(notice).toHaveAttribute("role", "status");
    await expect(notice).toHaveAttribute("aria-live", "polite");
    await expect(notice).toContainText("applies to Page 2 as a whole");
    await expect(notice).toContainText("No localized bounding coordinates exist");

    // -- Partial coverage on an imported sealed report: 2 of 3 checks.
    //    The example document is not a session document, so the import
    //    gate accepts the sealed report without a replace prompt. --
    await page.locator("#input-import-report").setInputFiles(SEALED_REPORT);
    await expect(page.locator("#coverage-heading")).toHaveText("What was checked", {
      timeout: 30_000,
    });

    await expect(page.locator("#coverage-heading")).toHaveText("What was checked");
    await expect(page.locator("#stat-unsupported")).toBeVisible();
    await expect(page.locator("#stat-unsupported")).toContainText("1");
    await expect(page.locator("#stat-unsupported")).toContainText("Unsupported");
    const incompleteList = page.locator('[role="list"][aria-label="Incomplete checks detail"]');
    await expect(incompleteList).toBeVisible();
    await expect(incompleteList).toContainText("c_alignment");
    await expect(incompleteList).toContainText("Not supported by this reader");
    await expect(
      page.locator("text=2 checks completed · 1 incomplete or unsupported"),
    ).toBeVisible();

    // The aria-live export preview states the partial coverage too.
    const preview = page.locator('[class*="preview"][aria-live="polite"]');
    await expect(preview).toContainText("Checks complete");
    await expect(preview).toContainText("2 / 3");

    // The imported amount finding keeps both readings as named candidates.
    const amountCard = page.locator("#finding-item-f_amount");
    await amountCard.focus();
    await page.keyboard.press("Enter");
    await expect(
      page.locator('[data-testid="occ-candidate-o_pdfium_amount"]'),
    ).toHaveAccessibleName(/\$1,000/);
    await expect(page.locator('[data-testid="occ-candidate-o_tess_amount"]')).toHaveAccessibleName(
      /\$100/,
    );
  });

  test("400% zoom equivalent: no page-level horizontal overflow and core controls stay keyboard-operable", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    // 1280px baseline at 400% browser zoom ≈ 320 CSS px of layout.
    await page.setViewportSize({ width: 320, height: 256 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);

    // Core controls are still focusable and operable by keyboard.
    const card = page.locator("#finding-item-finding-dup1");
    await card.focus();
    await page.keyboard.press("Enter");
    await expect(card).toHaveAttribute("aria-current", "true");
    await expect(page.locator('[data-testid="alignment-detail"]')).toBeVisible();

    // The viewer's own zoom reaches 400% through the '+' shortcut; the
    // overflow stays inside the stage's scroll container, not the page.
    const stage = page.locator("#viewer-stage");
    await stage.focus();
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press("+");
    }
    await expect(page.locator("#label-zoom")).toHaveText("400%");
    const overflowAtZoom = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflowAtZoom).toBeLessThanOrEqual(1);

    // Keyboard-driven finding navigation still works at 400%.
    await page.keyboard.press("n");
    const counter = await page.locator("#findings-counter").textContent();
    expect(counter).toMatch(/of 5/);

    // Scrollable paper area keeps focusable content reachable: a text-
    // equivalent Select button accepts focus and scrolls into view.
    const selectBtn = page.locator("#accessible-text-equivalent li button").first();
    await selectBtn.focus();
    await expect(selectBtn).toBeFocused();
    const box = await selectBtn.boundingBox();
    expect(box).not.toBeNull();
  });

  test("reduced motion: prefers-reduced-motion collapses transition and animation durations", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 1280, height: 900 });
    await openScanReport(page);

    // Baseline: the paper container has a live transition (>50ms).
    const paper = page.locator("#document-paper");
    const baseDuration = maxDurationMs(
      await paper.evaluate((el) => getComputedStyle(el).transitionDuration),
    );
    expect(baseDuration).toBeGreaterThan(50);
    const baseMotionToken = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--motion-state").trim(),
    );
    expect(baseMotionToken).toBe("120ms");

    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(
      true,
    );

    const reducedMotionToken = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--motion-state").trim(),
    );
    expect(reducedMotionToken).toBe("0ms");

    // Every animated surface drops to the effectively-zero floor.
    const paperReduced = maxDurationMs(
      await paper.evaluate((el) => getComputedStyle(el).transitionDuration),
    );
    expect(paperReduced).toBeLessThanOrEqual(0.05);

    const jsonBtn = page.getByRole("button", { name: "Download portable JSON" });
    const btnReduced = maxDurationMs(
      await jsonBtn.evaluate((el) => getComputedStyle(el).transitionDuration),
    );
    expect(btnReduced).toBeLessThanOrEqual(0.05);

    const animationReduced = maxDurationMs(
      await paper.evaluate((el) => getComputedStyle(el).animationDuration),
    );
    expect(animationReduced).toBeLessThanOrEqual(0.05);
  });

  test("axe: zero serious or critical violations on loaded workspace states", async ({ page }) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 1280, height: 900 });

    const problems: string[] = [];
    const scan = async (label: string) => {
      const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
      for (const v of results.violations) {
        if (v.impact === "serious" || v.impact === "critical") {
          for (const n of v.nodes) {
            problems.push(`${label}: ${v.id} (${v.impact}) ${JSON.stringify(n.target)}`);
          }
        }
      }
      return results;
    };

    // Intake surface (no document loaded).
    await gotoFresh(page, `${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');
    await scan("intake");

    // Bundled example document, findings listed, none expanded.
    await gotoFresh(page, `${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");
    await scan("example-doc/listed");

    // Imported report, viewer + coverage + export panel mounted.
    await openScanReport(page);
    await scan("imported-report/listed");

    expect(problems).toEqual([]);
  });

  test("axe: zero serious or critical violations with a finding expanded", async ({ page }) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 1280, height: 900 });
    await openScanReport(page);

    const card = page.locator("[id^='finding-item-']").first();
    await card.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator('[data-testid="alignment-detail"]')).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );

    const fs = await import("node:fs");
    const dir = path.resolve(process.cwd(), "artifacts/a11y");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, "axe-expanded-finding.json"),
      JSON.stringify(
        {
          url: `${baseUrl}/#/workspace?example=scan`,
          tags: AXE_TAGS,
          scannedAt: new Date().toISOString(),
          violationCount: results.violations.length,
          seriousOrCritical: serious.map((v) => ({
            id: v.id,
            impact: v.impact,
            help: v.help,
            nodes: v.nodes.map((n) => ({ target: n.target, html: n.html })),
          })),
        },
        null,
        2,
      ),
    );

    // T37-F1 regression coverage: finding cards were role="option" hosting
    // focusable descendants (nested-interactive, serious). The card is now
    // listitem + a button activator; this assertion guards the fix.
    expect(
      serious.map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" "))}`),
    ).toEqual([]);
  });
});
