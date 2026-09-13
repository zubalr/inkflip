import { defineConfig } from "@playwright/test";

/**
 * Confine spec discovery to the top-level tests/ directory.
 *
 * The canonical checkout nests worker/review worktrees under worktrees/,
 * each carrying its own tests/ tree and node_modules. Without a config,
 * Playwright scans the whole checkout root, and a spec-path filter like
 * `tests/browser/x.spec.ts` also matches worktrees/star/tests/browser/x.spec.ts
 * -- loading a second @playwright/test instance and aborting the run.
 * testDir keeps canonical runs (and each worktree's own runs) on exactly
 * their own specs. No other option is set; defaults are unchanged.
 */
export default defineConfig({
  projects: [
    {
      name: "tests",
      testDir: "./tests",
    },
    {
      // Experiments register acceptance commands that pass spec paths like
      // experiments/P12/browser.spec.ts; they need discovery outside tests/.
      name: "experiments",
      testDir: "./experiments",
      testMatch: "**/*.spec.ts",
    },
  ],
});
