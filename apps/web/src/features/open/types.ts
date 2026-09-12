/**
 * Shared types for the open feature (T08).
 *
 * The feature is deliberately structural about its two collaborators — the
 * lifecycle host (`OpenHost`, satisfied by `RunCoordinator` from
 * packages/runtime) and the reader (`OpenAdapter`, satisfied by the
 * `@inkflip/readers-pdfjs` adapter). This mirrors `state/store.ts`: the app
 * tsconfig cannot resolve cross-package `.ts` specifiers, so the contract is
 * expressed here and the concrete wiring lives in the composition mount.
 */

/** Minimal File/Blob surface the validator and reader need. */
export interface FileCandidate {
  /** Local label only — never an identity, never leaves the browser (I08). */
  readonly name: string;
  /** Declared MIME type — a hint verified against the header bytes. */
  readonly type: string;
  /** Declared byte size — checked before any byte is read. */
  readonly size: number;
  /** Bounded slice for header sniffing. */
  slice(start: number, end: number): { arrayBuffer(): Promise<ArrayBuffer> };
  /** Full bytes — requested only after every cheap check passed. */
  arrayBuffer(): Promise<ArrayBuffer>;
}

/**
 * Distinct local validation/open failures. `not_pdf`, `too_large`,
 * `encrypted` and `malformed` are the acceptance-required distinct buckets;
 * `too_many_pages`, `open_timeout` and `open_failed` keep later failures
 * honest instead of collapsing them into "malformed".
 */
export type OpenErrorKind =
  | "not_pdf"
  | "too_large"
  | "too_many_pages"
  | "encrypted"
  | "malformed"
  | "open_timeout"
  | "open_failed";

export interface OpenError {
  readonly kind: OpenErrorKind;
  /** Canonical copy shown to the user. */
  readonly message: string;
  /** Public-safe detail (reason code), never raw exception text or paths. */
  readonly detail?: string;
}

/** Per-page metadata needed by selection/region (canonical page space). */
export interface PageMeta {
  readonly index: number;
  /** Canonical page size in physical points (unrotated effective view). */
  readonly widthPt: number;
  readonly heightPt: number;
  readonly rotation: 0 | 90 | 180 | 270;
  /** Contract transform id for pdf_user -> canonical on this page. */
  readonly canonicalTransformId: string;
}

/** Document summary handed to the workspace once metadata loaded. */
export interface OpenedDocumentInfo {
  /** Original filename — a local label only (I08). */
  readonly label: string;
  readonly byteLength: number;
  /** SHA-256 of the immutable source bytes (document identity). */
  readonly sha256: string;
  readonly pageCount: number;
  readonly pages: readonly PageMeta[];
}

export type OpenOutcome =
  | { readonly ok: true; readonly document: OpenedDocumentInfo }
  | { readonly ok: false; readonly error: OpenError };

/**
 * Lifecycle host contract — the file-state half of `RunCoordinator`
 * (validating_file -> loading_metadata -> selecting, plus generation-first
 * clear/replace). Structurally identical so this module needs no
 * cross-package `.ts` import.
 */
export interface OpenHost {
  readonly fileState: string;
  /** Monotonic generation — increments BEFORE any old handle is released. */
  readonly currentGeneration: number;
  openFile(): void;
  fileValidated(): void;
  metadataLoaded(document: { sha256: string; page_count: number }): void;
  requestClear(next?: "idle" | "replace"): unknown;
  /** Register a file-scoped owned resource released on clear/replace. */
  own(resource: unknown, label?: string, teardown?: () => unknown): void;
}

/** Reader contract the open flow consumes (satisfied by PdfJsReaderAdapter). */
export interface OpenAdapter<Handle = unknown> {
  open(input: {
    bytes: Uint8Array;
    sha256: string;
    generation: number;
  }): Promise<Handle>;
  /** Page count plus contract geometry metadata for every page. */
  pages(handle: Handle): Promise<{
    count: number;
    pages: readonly {
      index: number;
      canonical_size_pt: readonly [number, number];
      rotation: 0 | 90 | 180 | 270;
      raw_to_canonical_transform_id: string;
    }[];
  }>;
  close(handle: Handle): Promise<void>;
}
