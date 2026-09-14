/**
 * Home-only helper: light view of the shipped "amount" example's captured
 * manifest (/examples/amount/manifest.json). The heavy interactive sample
 * stays at /examples/amount/index.html — this helper only reads the recorded
 * manifest so the hero can show one real text difference without a second
 * PDF/OCR engine or remote assets.
 */

export interface HomeSampleReader {
  name: string;
  version: string;
}

export interface HomeSample {
  /** Human situation line, e.g. "The amount that reads differently". */
  title: string;
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
}

export async function loadHomeSample(): Promise<HomeSample> {
  const res = await fetch("/examples/amount/manifest.json");
  if (!res.ok) {
    throw new Error(`Sample manifest unavailable (${res.status})`);
  }
  const m = (await res.json()) as ManifestLike;

  const title = typeof m.card_title === "string" ? m.card_title : "";
  const mechanism = typeof m.mechanism === "string" ? m.mechanism : "";

  const readers: HomeSampleReader[] = Object.values(m.readers ?? {})
    .filter(
      (r): r is { name: string; version?: string } =>
        typeof r === "object" && r !== null && typeof (r as { name?: unknown }).name === "string",
    )
    .map((r) => ({
      name: r.name,
      version: typeof r.version === "string" ? r.version : "",
    }));

  // The two dollar figures are recorded in the manifest's own mechanism
  // sentence ("visual $100 becomes extracted $1,000") — parsed, not hardcoded.
  let visualAmount: string | null = null;
  let extractedAmount: string | null = null;
  const pair = mechanism.match(/visual\s+(\S+)\s+becomes\s+extracted\s+(\S+)/i);
  if (pair) {
    visualAmount = pair[1];
    extractedAmount = pair[2];
  }

  return {
    title,
    mechanism,
    visualAmount,
    extractedAmount,
    readers,
    sampleUrl: "/examples/amount/index.html",
    reportUrl: "/examples/amount/report.json",
  };
}
