/**
 * Offline manifest construction (T25).
 *
 * The prepare-offline action precaches exactly the entries a manifest
 * names. Three sources make up the allowlist, all same-origin and all
 * versioned:
 *
 * 1. `config/resolved-assets.json` — the T02-frozen registry of staged
 *    reader runtimes and the pinned OCR model. Every entry carries its
 *    upstream sha256; the service worker verifies those digests both at
 *    store time and at serve time (I13).
 * 2. The curated public example mount (`/examples/amount/`) — release-
 *    versioned fixture copies. The four example PDFs carry the digests
 *    published in the example's own `manifest.json`; the remaining
 *    support files are recorded-digest entries bound at prepare time.
 * 3. The running application shell — `/` + `/index.html`, the built
 *    script/style/modulepreload tags present in the live document, the
 *    emitted `pdf.worker` bundle (imported here through the same `?url`
 *    specifier the session uses, so the build emits and names the exact
 *    asset the app will request), plus every same-origin `/assets/`
 *    resource the page has actually fetched (performance entries). These
 *    are hashed-name build artifacts: their prepare-time digests are
 *    recorded in the cache and re-verified on every serve.
 *
 * The manifest's normalized form is the cache generation's only input:
 * change any path or declared digest and a different generation is
 * produced — model updates can never reuse a wrong-hash slot.
 */
import resolvedAssets from "../../../../config/resolved-assets.json";
import pdfWorkerUrl from "pdfjs-dist/legacy/build/pdf.worker.mjs?url";

export const OFFLINE_MANIFEST_SCHEMA = "inkflip-offline-manifest/1" as const;

export type OfflineEntryKind = "app" | "reader" | "model" | "example" | "notice";

export interface OfflineManifestEntry {
  /** Exact same-origin path ("/…"), never a prefix or pattern. */
  readonly path: string;
  /**
   * Declared sha256 when the registry/example manifest pins one; null
   * for build artifacts whose digest is recorded at prepare time.
   */
  readonly sha256: string | null;
  readonly kind: OfflineEntryKind;
}

export interface OfflineManifest {
  readonly schema: typeof OFFLINE_MANIFEST_SCHEMA;
  /** Release label carried into the generation record. */
  readonly release: string;
  readonly entries: readonly OfflineManifestEntry[];
}

/**
 * Curated public example files (apps/web/public/examples/amount/). The
 * PDF digests mirror that directory's committed manifest.json; support
 * files stay recorded-digest. Regenerating the examples requires
 * refreshing these constants — the spec fails integrity loudly if they
 * drift.
 */
const EXAMPLE_ENTRIES: readonly OfflineManifestEntry[] = [
  {
    path: "/examples/amount/mapping-amount.pdf",
    sha256: "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80",
    kind: "example",
  },
  {
    path: "/examples/amount/mapping-control.pdf",
    sha256: "19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed",
    kind: "example",
  },
  {
    path: "/examples/amount/covered-amount.pdf",
    sha256: "5dfb2dd71cff34e36f6e909e42fdbb67e4b976f8d88a0a521bdc5029c226b888",
    kind: "example",
  },
  {
    path: "/examples/amount/covered-control.pdf",
    sha256: "cf003f5a746ace7ea6efab9c86733b267159cd8f6bc0343f6a09f0233d95d03d",
    kind: "example",
  },
  { path: "/examples/amount/manifest.json", sha256: null, kind: "example" },
  { path: "/examples/amount/report.json", sha256: null, kind: "example" },
  { path: "/examples/amount/index.html", sha256: null, kind: "example" },
  { path: "/examples/amount/amount.css", sha256: null, kind: "example" },
  { path: "/examples/amount/amount.js", sha256: null, kind: "example" },
];

/** resolved-assets `kind` → manifest kind (the allowlist is exact). */
function manifestKind(assetKind: string): OfflineEntryKind {
  if (assetKind === "ocr-model") return "model";
  if (assetKind === "notice") return "notice";
  return "reader";
}

/** Staged reader/model assets from the frozen registry. */
export function stagedAssetEntries(): OfflineManifestEntry[] {
  const out: OfflineManifestEntry[] = [];
  for (const asset of resolvedAssets.assets) {
    for (const file of asset.files) {
      out.push({
        path: `/${file.staged_path}`,
        sha256: file.sha256,
        kind: manifestKind(asset.kind),
      });
    }
  }
  return out;
}

/**
 * The application shell section: `/` + `/index.html` navigations, every
 * same-origin script/style/modulepreload/preload in the live document,
 * the emitted pdf.js worker bundle, and any already-fetched same-origin
 * `/assets/` resource (covers lazy fetches seen so far — e.g. a CMap
 * pulled by an earlier document). Digests are recorded at prepare.
 */
export function appShellEntries(): OfflineManifestEntry[] {
  const paths = new Set<string>(["/", "/index.html"]);
  // The running page's own document is a shell entry — for the app root
  // this is already covered ("/"); for feature/preview mounts it is the
  // mount's emitted html path, which an offline reload must be able to
  // serve.
  try {
    const here = new URL(window.location.href);
    if (here.origin === window.location.origin && here.pathname !== "") {
      paths.add(here.pathname);
    }
  } catch {
    /* no usable location — shell entries stay at the defaults */
  }
  const addUrl = (raw: string | null | undefined): void => {
    if (!raw) return;
    try {
      const url = new URL(raw, window.location.origin);
      if (url.origin !== window.location.origin) return;
      if (url.pathname.startsWith("/__inkflip_sw__/")) return;
      paths.add(url.pathname);
    } catch {
      /* unparsable URLs are not shell assets */
    }
  };
  if (typeof document !== "undefined") {
    const nodes = document.querySelectorAll(
      "script[src], link[rel=stylesheet][href], link[rel=modulepreload][href], link[rel=preload][href]",
    );
    for (const node of Array.from(nodes)) {
      addUrl(node.getAttribute("src") ?? node.getAttribute("href"));
    }
  }
  // The pinned pdf.js worker — the same `?url` specifier session.ts and
  // the feature mounts use, so this is the exact emitted asset path.
  addUrl(pdfWorkerUrl);
  if (typeof performance !== "undefined") {
    for (const entry of performance.getEntriesByType("resource")) {
      if (!(entry instanceof PerformanceResourceTiming)) continue;
      const url = new URL(entry.name, window.location.origin);
      if (url.origin !== window.location.origin) continue;
      // Built bundles and staged trees only — never arbitrary fetches.
      if (!url.pathname.startsWith("/assets/")) continue;
      if (!/\.(m?js|css|wasm|bcmap|ttf|pfb|icc|txt|md|json)$/.test(url.pathname)) {
        continue;
      }
      paths.add(url.pathname);
    }
  }
  return [...paths].map((path) => ({
    path,
    sha256: null,
    kind: "app" as const,
  }));
}

export interface BuildManifestOptions {
  /** Release label override (tests record build state). */
  readonly release?: string;
  /** Extra explicit entries merged into the allowlist. */
  readonly extraEntries?: readonly OfflineManifestEntry[];
}

/** Assemble the full versioned allowlist for this release. */
export function buildOfflineManifest(options: BuildManifestOptions = {}): OfflineManifest {
  const byPath = new Map<string, OfflineManifestEntry>();
  for (const entry of [
    ...appShellEntries(),
    ...stagedAssetEntries(),
    ...EXAMPLE_ENTRIES,
    ...(options.extraEntries ?? []),
  ]) {
    byPath.set(entry.path, entry);
  }
  return {
    schema: OFFLINE_MANIFEST_SCHEMA,
    release: options.release ?? "web-static",
    entries: [...byPath.values()].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0)),
  };
}
