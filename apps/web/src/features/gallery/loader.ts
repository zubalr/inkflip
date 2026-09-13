/**
 * Loader for the committed example index + per-card manifests (T21).
 *
 * Same-origin static reads only — the gallery never fetches a remote URL;
 * `download_url`/`report_url` values are validated to be site-relative
 * (`/examples/…`) before use so a tampered index cannot redirect the app.
 */
import type { ExampleCard, ExampleIndex, ExampleManifest } from "./types";

function isIndex(v: unknown): v is ExampleIndex {
  return (
    typeof v === "object" &&
    v !== null &&
    Array.isArray((v as ExampleIndex).cards) &&
    (v as ExampleIndex).cards.every(
      (c) =>
        typeof c === "object" &&
        c !== null &&
        typeof (c as ExampleCard).example_id === "string" &&
        typeof (c as ExampleCard).report_url === "string",
    )
  );
}

function isManifest(v: unknown): v is ExampleManifest {
  return (
    typeof v === "object" &&
    v !== null &&
    typeof (v as ExampleManifest).example_id === "string" &&
    typeof (v as ExampleManifest).files === "object" &&
    (v as ExampleManifest).files !== null &&
    Array.isArray((v as ExampleManifest).findings)
  );
}

/** True only for site-relative paths under /examples/ — blocks URL exfil. */
export function isLocalExampleUrl(url: string): boolean {
  return /^\/examples\/[A-Za-z0-9._/-]+$/.test(url);
}

export async function loadExampleIndex(
  fetchImpl: typeof fetch = fetch,
): Promise<ExampleIndex> {
  const res = await fetchImpl("examples/index.json", { credentials: "same-origin" });
  if (!res.ok) throw new Error(`examples index unavailable (${res.status})`);
  const data: unknown = await res.json();
  if (!isIndex(data)) throw new Error("examples index failed shape validation");
  for (const card of data.cards) {
    if (!isLocalExampleUrl(card.report_url) || !isLocalExampleUrl(card.manifest_url)) {
      throw new Error(`examples index carries a non-local URL for ${card.example_id}`);
    }
    if (!isLocalExampleUrl(card.source.download_url)) {
      throw new Error(`examples index carries a non-local source URL for ${card.example_id}`);
    }
  }
  return data;
}

export async function loadExampleManifest(
  card: ExampleCard,
  fetchImpl: typeof fetch = fetch,
): Promise<ExampleManifest> {
  if (!isLocalExampleUrl(card.manifest_url)) {
    throw new Error(`refusing non-local manifest URL for ${card.example_id}`);
  }
  const res = await fetchImpl(card.manifest_url, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`manifest unavailable (${res.status})`);
  const data: unknown = await res.json();
  if (!isManifest(data)) throw new Error("manifest failed shape validation");
  return data;
}
