# pdf-p7q native binding verification

Root cause: Bun 1.4.0 applies minimumReleaseAge to transitive optional dependencies independently. Existing exemptions named oxlint and oxfmt wrappers only. Their September 7 native bindings were filtered out under the seven-day policy; Bun saved a lock missing all 38 platform records. A clean Mac reproducer failed with Cannot find native binding, matching the reported Homebase missing Linux GNU modules. This is dependency resolution, not an ABI or isolated-linker failure.

Primary documentation: https://bun.com/docs/pm/cli/install#minimum-release-age
Public metadata: https://registry.npmjs.org/@oxlint%2fbinding-linux-x64-gnu and https://registry.npmjs.org/@oxfmt%2fbinding-linux-x64-gnu (pinned releases published 2026-09-07).

Changes: bunfig.toml explicitly exempts the 38 exact scoped binding package names declared by oxlint 1.82.0 and oxfmt 0.67.0. No wildcard scope, version upgrade, linker change, or global age-filter reduction. Exclusions are name-based; comments accurately distinguish this from version pins. bun.lock retains the 38 Bun-generated binding entries from the initial repair. package.json unchanged.

Verification on Mac with Bun 1.4.0:
- Disposable full workspace manifests and updated bunfig, no lock or node_modules: bun install --lockfile-only generated a new lock. All 38 oxlint/oxfmt binding records exactly match the repaired current lock.
- Freshly generated disposable lock: bun install --frozen-lockfile passed from empty node_modules; oxlint --version returned 1.82.0 and oxfmt --version returned 0.67.0 via bun x --no-install.
- Current checkout: bun install --frozen-lockfile passed without changes; both same version commands passed; git diff --check passed.
- Earlier repair verification: clean Linux-x64-targeted frozen install materialized both GNU .node files; registered verify passed 109 tests. Actual Linux execution remains for parent.

Separate finding: full clean resolution logs age-filter errors for five @cloudflare/workerd platform packages at 1.20260910.1 despite exiting zero and saving a lock. This is outside the assigned oxlint/oxfmt fix. The disposable full regenerated lock was not copied over the current repository lock; only the matching ox binding records were verified. No Cloudflare exemptions were added.

Parent Linux validation: copy bunfig.toml and bun.lock, then run bun install --frozen-lockfile; bun x --no-install oxlint --version; bun x --no-install oxfmt --version; bun run verify. Expected versions: 1.82.0 and 0.67.0. No remote operations, Beads mutations, commits, pushes, or app starts performed.
