/**
 * Home-only helper: light view of the shipped "amount" example's captured
 * manifest (/examples/amount/manifest.json). The interactive sample itself
 * lives at /#/workspace?example=amount — the real inspector — so this
 * helper only reads the recorded manifest to show one real text difference
 * without a second PDF/OCR engine or remote assets.
 */

export interface HomeSampleReader {
  name: string;
  version: string;
  /** Reader method — lets the preview pair readings by real evidence kind
   *  (native_text vs ocr) instead of generic "page vs extracted" labels. */
  method: string;
}

export interface HomeSample {
  /** Human situation line from the recorded manifest (gallery overlays everyday copy). */
  title: string;
  /** First recorded finding title, when the manifest lists one. */
  findingTitle: string | null;
  /** Recorded mechanism sentence from the example manifest. */
  mechanism: string;
  /** The visual amount and the extracted amount, parsed from the recorded mechanism. */
  visualAmount: string | null;
  extractedAmount: string | null;
  /** Readers that produced the recorded readings (name + version). */
  readers: HomeSampleReader[];
  /** Where the sample's own interactive page lives (same origin). */
  sampleUrl: string;
  /** The matching captured report (validated by the same import gate as user files). */
  reportUrl: string;
}

interface ManifestLike {
  card_title?: unknown;
  mechanism?: unknown;
  readers?: unknown;
  findings?: unknown;
}

let cachedSample: Promise<HomeSample> | null = null;

export function loadHomeSample(): Promise<HomeSample> {
  // One fetch per session — the manifest is static content; a failure
  // clears the cache so a later mount retries rather than re-failing.
  cachedSample ??= fetchHomeSample().catch((err: unknown) => {
    cachedSample = null;
    throw err;
  });
  return cachedSample;
}

async function fetchHomeSample(): Promise<HomeSample> {
  const res = await fetch("/examples/amount/manifest.json");
  if (!res.ok) {
    throw new Error(`Sample manifest unavailable (${res.status})`);
  }
  const m = (await res.json()) as ManifestLike;

  const title = typeof m.card_title === "string" ? m.card_title : "";
  const mechanism = typeof m.mechanism === "string" ? m.mechanism : "";
  const firstFinding = Array.isArray(m.findings) ? m.findings[0] : null;
  const findingTitle =
    firstFinding !== null &&
    typeof firstFinding === "object" &&
    typeof (firstFinding as { title?: unknown }).title === "string"
      ? (firstFinding as { title: string }).title
      : null;

  const readers: HomeSampleReader[] = Object.values(m.readers ?? {})
    .filter(
      (r): r is { name: string; version?: string; method?: string } =>
        typeof r === "object" && r !== null && typeof (r as { name?: unknown }).name === "string",
    )
    .map((r) => ({
      name: r.name,
      version: typeof r.version === "string" ? r.version : "",
      method: typeof r.method === "string" ? r.method : "",
    }));

  // The two dollar figures are recorded in the manifest's own mechanism
  // sentence ("visual $100 becomes extracted $1,000") — parsed, not hardcoded.
  let visualAmount: string | null = null;
  let extractedAmount: string | null = null;
  const pair = mechanism.match(/visual\s+(\S+)\s+becomes\s+extracted\s+(\S+)/i);
  if (pair) {
    visualAmount = pair[1] ?? null;
    extractedAmount = pair[2] ?? null;
  }

  return {
    title,
    findingTitle,
    mechanism,
    visualAmount,
    extractedAmount,
    readers,
    sampleUrl: "/#/workspace?example=amount",
    reportUrl: "/examples/amount/report.json",
  };
}
