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
  { path: "/examples/index.json", sha256: null, kind: "example" },
  { path: "/examples/amount/amount.css", sha256: null, kind: "example" },
  { path: "/examples/amount/index.html", sha256: null, kind: "example" },
  { path: "/examples/amount/manifest.json", sha256: null, kind: "example" },
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
    path: "/examples/amount/native-unicode-control.pdf",
    sha256: "3456ae2c3cd0bac03c76656f7f0150b9e1be92ad384006d4b158a39feef7b421",
    kind: "example",
  },
  {
    path: "/examples/amount/native-unicode-native.pdf",
    sha256: "5ae99c803de6701b334c3328dedde576e9ee425d4c0aa040d5b5c8da7349b159",
    kind: "example",
  },
  { path: "/examples/amount/report.control.json", sha256: null, kind: "example" },
  { path: "/examples/amount/report.json", sha256: null, kind: "example" },
  { path: "/examples/amount/report.native-unicode-control.json", sha256: null, kind: "example" },
  { path: "/examples/amount/report.native-unicode-native.json", sha256: null, kind: "example" },
  {
    path: "/examples/covered/covered-amount.pdf",
    sha256: "5dfb2dd71cff34e36f6e909e42fdbb67e4b976f8d88a0a521bdc5029c226b888",
    kind: "example",
  },
  {
    path: "/examples/covered/covered-control.pdf",
    sha256: "cf003f5a746ace7ea6efab9c86733b267159cd8f6bc0343f6a09f0233d95d03d",
    kind: "example",
  },
  { path: "/examples/covered/manifest.json", sha256: null, kind: "example" },
  { path: "/examples/covered/report.control.json", sha256: null, kind: "example" },
  { path: "/examples/covered/report.json", sha256: null, kind: "example" },
  { path: "/examples/covered/report.white-contrast-control.json", sha256: null, kind: "example" },
  { path: "/examples/covered/report.white-contrast-white.json", sha256: null, kind: "example" },
  {
    path: "/examples/covered/white-contrast-control.pdf",
    sha256: "cdf06d357a1db2771061290669ec2083c39ab75b0a9473f80082028e7fefb804",
    kind: "example",
  },
  {
    path: "/examples/covered/white-contrast-white.pdf",
    sha256: "333a621576c9d023751da527760e7f4deb380bac10dd0e0fab22fa116da5ef8c",
    kind: "example",
  },
  {
    path: "/examples/duplicates/duplicates-control.pdf",
    sha256: "e588ab80759c0e6e1615c1b3c8a1059a651611a7972e80486616c6d3e0461b1f",
    kind: "example",
  },
  {
    path: "/examples/duplicates/duplicates-four.pdf",
    sha256: "036db55ee2f8c320252c7c9fb220daa38699387800e8a3bbf8c6bb73463feb1f",
    kind: "example",
  },
  { path: "/examples/duplicates/manifest.json", sha256: null, kind: "example" },
  {
    path: "/examples/duplicates/ocr-material-control.pdf",
    sha256: "d78643ef2a2206d06b833c352992d985b04d01104da72bd992ce62cf3f40c0cf",
    kind: "example",
  },
  {
    path: "/examples/duplicates/ocr-material-sign-ambiguity.pdf",
    sha256: "cfb1d4b62cf655a5400a23ddcfff986bad7ebc23d4dd37513b8b4a82664ff547",
    kind: "example",
  },
  { path: "/examples/duplicates/report.control.json", sha256: null, kind: "example" },
  { path: "/examples/duplicates/report.json", sha256: null, kind: "example" },
  { path: "/examples/duplicates/report.ocr-material-control.json", sha256: null, kind: "example" },
  { path: "/examples/duplicates/report.ocr-material-sign-ambiguity.json", sha256: null, kind: "example" },
  {
    path: "/examples/geometry/geometry-0.pdf",
    sha256: "42b3bdedd0563b259b497bdd81c8631b710f362448b6bd1e59e424b2a34d8531",
    kind: "example",
  },
  {
    path: "/examples/geometry/geometry-180.pdf",
    sha256: "5447a3de234f99e6eae2afcedb711c6e86e6053054027010087a58da54faac23",
    kind: "example",
  },
  {
    path: "/examples/geometry/geometry-270.pdf",
    sha256: "743bb29a07c556bbe2ab3a29ad9d61909e2ce4fe2c52494c139b91b491cffede",
    kind: "example",
  },
  {
    path: "/examples/geometry/geometry-90.pdf",
    sha256: "a9e8b167a9b244459254842daca0daadbf67a07a15706e9ec3dda3d8a990625f",
    kind: "example",
  },
  {
    path: "/examples/geometry/geometry-control.pdf",
    sha256: "19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed",
    kind: "example",
  },
  { path: "/examples/geometry/manifest.json", sha256: null, kind: "example" },
  { path: "/examples/geometry/report.control.json", sha256: null, kind: "example" },
  { path: "/examples/geometry/report.geometry-0.json", sha256: null, kind: "example" },
  { path: "/examples/geometry/report.geometry-180.json", sha256: null, kind: "example" },
  { path: "/examples/geometry/report.geometry-270.json", sha256: null, kind: "example" },
  { path: "/examples/geometry/report.json", sha256: null, kind: "example" },
  { path: "/examples/reading-order/manifest.json", sha256: null, kind: "example" },
  {
    path: "/examples/reading-order/reading-order-control.pdf",
    sha256: "41a20c6a460fd9e7c91ffc500573a2ae32e97f9bb6ee5410a33d256b23ba9db4",
    kind: "example",
  },
  {
    path: "/examples/reading-order/reading-order-reordered.pdf",
    sha256: "cdedafa22cf2a54386998ebea5e7d8c597f541fcd2c702f7909e16d43c2499df",
    kind: "example",
  },
  { path: "/examples/reading-order/report.control.json", sha256: null, kind: "example" },
  { path: "/examples/reading-order/report.json", sha256: null, kind: "example" },
  { path: "/examples/scan/manifest.json", sha256: null, kind: "example" },
  { path: "/examples/scan/report.json", sha256: null, kind: "example" },
  { path: "/examples/scan/report.scan-raster-only.json", sha256: null, kind: "example" },
  { path: "/examples/scan/report.scan-shifted.json", sha256: null, kind: "example" },
  {
    path: "/examples/scan/scan-correct.pdf",
    sha256: "86a17f4a2ee4c4e75bd2eb406266b20ed3f960f644631841c5fad8b0e7ff4f5f",
    kind: "example",
  },
  {
    path: "/examples/scan/scan-raster-only.pdf",
    sha256: "29b36a189b356fd6320f70846a68741399415789f378171f34152d6d0abf7ddf",
    kind: "example",
  },
  {
    path: "/examples/scan/scan-shifted.pdf",
    sha256: "2b855c7ee27d22c71696d3be9f63758f61b8449e51e03cdfa80272afc4d62158",
    kind: "example",
  },
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
