/**
 * Structural types for the public examples gallery (T21).
 *
 * Mirrors the generated `/examples/index.json` + per-card `manifest.json`
 * written by scripts/prepare_examples.py. Every hash/version/count shown
 * in the UI is read from these committed artifacts — never hardcoded.
 */

export interface ExampleFileEntry {
  readonly filename: string;
  readonly sha256: string;
  readonly byte_length: number;
  readonly download_url: string;
  readonly role: string;
  readonly report_file: string;
  readonly renders_identical?: boolean;
}

export interface ExampleReader {
  readonly id?: string;
  readonly name: string;
  readonly version: string;
  readonly method: string;
  readonly environment?: string;
  readonly adapter_version?: string;
  readonly model_sha256?: string;
}

export interface ExampleFinding {
  readonly id: string;
  readonly title: string;
  readonly category: string;
  readonly page_index: number;
  readonly explanation?: string;
}

export interface ExampleCard {
  readonly example_id: string;
  readonly card_title: string;
  readonly mechanism: string;
  readonly fixture_id: string;
  readonly family: string;
  readonly manifest_url: string;
  readonly report_url: string;
  readonly source: ExampleFileEntry;
  readonly readers: readonly ExampleReader[];
  readonly finding_count: number;
  readonly variant_count: number;
  readonly timing_ms: number;
}

export interface ExampleIndex {
  readonly schema_version: string;
  readonly cards: readonly ExampleCard[];
}

export interface ExampleManifest {
  readonly schema_version: string;
  readonly example_id: string;
  readonly family: string;
  readonly fixture_id: string;
  readonly card_title: string;
  readonly mechanism: string;
  readonly rights: string;
  readonly provenance: string;
  readonly timing: {
    readonly duration_ms: number;
    readonly method: string;
    readonly description: string;
  };
  readonly files: Record<string, ExampleFileEntry>;
  readonly readers: Record<string, ExampleReader>;
  readonly findings: readonly ExampleFinding[];
  readonly report_file: string;
  readonly report_id: string;
  readonly run_key: string;
}
