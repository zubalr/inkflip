/**
 * OpenController (T08) — orchestrates one offered file through the file
 * lifecycle: candidate → validating_file → loading_metadata → selecting.
 *
 * Ordering guarantees that carry the invariants:
 *
 * - I07 generation-first replacement: a new offer while a document (or run)
 *   is live calls `host.requestClear("replace")`, which increments the
 *   generation BEFORE any owned resource is released — the recorded teardown
 *   event below always observes the *new* generation, and every message from
 *   the old generation is stale by construction.
 * - I01/I08 the candidate is checked by declared size, declared MIME hint
 *   and a ≤1 KiB header slice before its bytes are read; nothing is hashed,
 *   stored or transmitted beyond the local reader. The filename is kept as
 *   a display label only.
 * - Failure taxonomy: wrong type/header, oversized, encrypted and malformed
 *   are DISTINCT `OpenError.kind`s with distinct canonical copy — a failure
 *   never lands in `selecting` and never looks like success.
 *
 * The controller never touches the DOM, never fetches and never mutates the
 * candidate. Its collaborators are the structural `OpenHost` (RunCoordinator)
 * and `OpenAdapter` (pdf.js reader adapter) injected by the composition.
 */
import { OPEN_COPY } from "./copy";
import type { OpenProfile } from "./limits";
import { validateCandidate } from "./validate";
import type {
  FileCandidate,
  OpenAdapter,
  OpenError,
  OpenErrorKind,
  OpenHost,
  OpenOutcome,
  OpenedDocumentInfo,
  PageMeta,
} from "./types";

/** Diagnostic event stream — lets tests observe ordering without mocks. */
export type ControllerEvent =
  | { readonly type: "clear"; readonly generation: number; readonly next: "idle" | "replace" }
  | { readonly type: "teardown"; readonly generation: number; readonly label: string }
  | { readonly type: "validated"; readonly generation: number }
  | { readonly type: "opened"; readonly generation: number; readonly sha256: string }
  | { readonly type: "metadata"; readonly generation: number; readonly pageCount: number; readonly document: OpenedDocumentInfo }
  | { readonly type: "rejected"; readonly generation: number; readonly kind: OpenErrorKind; readonly error: OpenError };

export interface OpenControllerOptions {
  readonly host: OpenHost;
  readonly adapter: OpenAdapter;
  readonly profile: OpenProfile;
  readonly onEvent?: (event: ControllerEvent) => void;
}

function makeError(
  kind: OpenErrorKind,
  message: string,
  detail?: string,
): OpenError {
  return detail === undefined ? { kind, message } : { kind, message, detail };
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const subtle = (globalThis as { crypto?: { subtle?: { digest(a: string, b: BufferSource): Promise<ArrayBuffer> } } })
    .crypto?.subtle;
  if (subtle === undefined) {
    throw new Error("crypto.subtle unavailable");
  }
  const digest = await subtle.digest("SHA-256", bytes as BufferSource);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Map a reader failure to a distinct local error. ReaderError carries a
 * public-safe `reason` code (`encrypted:…`, `resource_limit:…`,
 * `parser_error:…`, `timeout:…`); raw exception text never surfaces.
 */
export function classifyOpenFailure(error: unknown): OpenError {
  const reason =
    typeof error === "object" && error !== null && "reason" in error
      ? String((error as { reason: unknown }).reason)
      : "";
  if (reason.startsWith("encrypted")) {
    return makeError("encrypted", OPEN_COPY.encrypted, reason.slice(0, 160));
  }
  if (reason.startsWith("resource_limit")) {
    return makeError("too_many_pages", OPEN_COPY.tooManyPages, reason.slice(0, 160));
  }
  if (reason.startsWith("timeout")) {
    return makeError("open_timeout", OPEN_COPY.malformed, reason.slice(0, 160));
  }
  return makeError("malformed", OPEN_COPY.malformed, reason.slice(0, 160) || "parser_error");
}

export class OpenController {
  private readonly host: OpenHost;
  private readonly adapter: OpenAdapter;
  private readonly profile: OpenProfile;
  private readonly listeners = new Set<(event: ControllerEvent) => void>();

  private busy = false;
  private handle: unknown | null = null;
  private document: OpenedDocumentInfo | null = null;

  constructor(options: OpenControllerOptions) {
    this.host = options.host;
    this.adapter = options.adapter;
    this.profile = options.profile;
    if (options.onEvent) this.listeners.add(options.onEvent);
  }

  private emit(event: ControllerEvent): void {
    // Set iteration tolerates a listener unsubscribing itself mid-emit.
    for (const listener of this.listeners) listener(event);
  }

  /**
   * Subscribe to the controller event stream (document/rejection/clear).
   * The UI renders from this stream — offers made through any caller
   * surface identically, so no view can drift from the controller state.
   */
  subscribe(listener: (event: ControllerEvent) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** The adapter-owned handle for the live document (render/plan use). */
  get currentHandle(): unknown | null {
    return this.handle;
  }

  get currentDocument(): OpenedDocumentInfo | null {
    return this.document;
  }

  /**
   * Offer one candidate. When a document/run is already live the
   * generation increments first (`requestClear("replace")`), owned
   * teardown runs under the new generation, and only then does validation
   * begin — a stale event can never reach the new document (I07).
   */
  async offer(candidate: FileCandidate): Promise<OpenOutcome> {
    if (this.busy) {
      return {
        ok: false,
        error: makeError("open_failed", OPEN_COPY.malformed, "open:busy"),
      };
    }
    this.busy = true;
    try {
      const state = this.host.fileState;
      if (state === "idle") {
        this.host.openFile();
      } else if (state === "validating_file") {
        // Already in the sniff phase (e.g. a synchronous re-offer): proceed.
      } else if (state === "clearing") {
        return {
          ok: false,
          error: makeError("open_failed", OPEN_COPY.malformed, `open:state:${state}`),
        };
      } else {
        // selecting/running/terminal states: generation-first replacement.
        // The 'clear' event records the generation being retired; the
        // teardown events that follow observe the NEW generation.
        this.emit({
          type: "clear",
          generation: this.host.currentGeneration,
          next: "replace",
        });
        this.host.requestClear("replace");
      }
      // fileState is now validating_file either way.
      const invalid = await validateCandidate(candidate, this.profile);
      if (invalid !== null) {
        this.emit({ type: "rejected", generation: this.host.currentGeneration, kind: invalid.kind, error: invalid });
        this.host.requestClear("idle");
        return { ok: false, error: invalid };
      }
      this.host.fileValidated();
      this.emit({ type: "validated", generation: this.host.currentGeneration });

      let bytes: Uint8Array;
      try {
        bytes = new Uint8Array(await candidate.arrayBuffer());
      } catch {
        this.host.requestClear("idle");
        return {
          ok: false,
          error: makeError("malformed", OPEN_COPY.malformed, "bytes:unreadable"),
        };
      }
      let sha: string;
      try {
        sha = await sha256Hex(bytes);
      } catch {
        this.host.requestClear("idle");
        return {
          ok: false,
          error: makeError("open_failed", OPEN_COPY.malformed, "sha256:unavailable"),
        };
      }

      let handle: unknown;
      try {
        handle = await this.adapter.open({
          bytes,
          sha256: sha,
          generation: this.host.currentGeneration,
        });
      } catch (error) {
        const classified = classifyOpenFailure(error);
        this.emit({
          type: "rejected",
          generation: this.host.currentGeneration,
          kind: classified.kind,
          error: classified,
        });
        this.host.requestClear("idle");
        return { ok: false, error: classified };
      }
      this.emit({
        type: "opened",
        generation: this.host.currentGeneration,
        sha256: sha,
      });
      // File-scoped ownership: the handle is released by clear/replace —
      // and the teardown observes the NEW generation (I07 proof point).
      this.host.own(handle, "pdfjs-document", () => {
        this.emit({
          type: "teardown",
          generation: this.host.currentGeneration,
          label: "pdfjs-document",
        });
        return this.adapter.close(handle);
      });
      this.handle = handle;

      let meta: Awaited<ReturnType<OpenAdapter["pages"]>>;
      try {
        meta = await this.adapter.pages(handle);
      } catch (error) {
        const classified = classifyOpenFailure(error);
        this.emit({
          type: "rejected",
          generation: this.host.currentGeneration,
          kind: classified.kind,
          error: classified,
        });
        this.host.requestClear("idle");
        this.handle = null;
        return { ok: false, error: classified };
      }
      if (meta.count > this.profile.maxDocumentPages) {
        const err = makeError(
          "too_many_pages",
          OPEN_COPY.tooManyPages,
          `pages:${meta.count}>${this.profile.maxDocumentPages}`,
        );
        this.emit({
          type: "rejected",
          generation: this.host.currentGeneration,
          kind: err.kind,
          error: err,
        });
        this.host.requestClear("idle");
        this.handle = null;
        return { ok: false, error: err };
      }

      const pages: PageMeta[] = meta.pages.map((p) => ({
        index: p.index,
        widthPt: p.canonical_size_pt[0],
        heightPt: p.canonical_size_pt[1],
        rotation: p.rotation,
        canonicalTransformId: p.raw_to_canonical_transform_id,
      }));
      this.document = {
        label: candidate.name,
        byteLength: candidate.size,
        sha256: sha,
        pageCount: meta.count,
        pages,
      };
      this.host.metadataLoaded({ sha256: sha, page_count: meta.count });
      this.emit({
        type: "metadata",
        generation: this.host.currentGeneration,
        pageCount: meta.count,
        document: this.document,
      });
      return { ok: true, document: this.document };
    } catch (error) {
      // Lifecycle contract violations (e.g. illegal transitions) surface as
      // open_failed — never as a successful open.
      const failed = makeError(
        "open_failed",
        OPEN_COPY.malformed,
        error instanceof Error ? error.message.slice(0, 160) : "unexpected",
      );
      this.emit({
        type: "rejected",
        generation: this.host.currentGeneration,
        kind: failed.kind,
        error: failed,
      });
      try {
        this.host.requestClear("idle");
      } catch {
        // Already idle/clearing — nothing more to release here.
      }
      return { ok: false, error: failed };
    } finally {
      this.busy = false;
    }
  }

  /** Clear the workspace back to idle (generation increments first). */
  clear(): void {
    this.handle = null;
    this.document = null;
    if (this.host.fileState !== "idle") {
      this.emit({
        type: "clear",
        generation: this.host.currentGeneration,
        next: "idle",
      });
      this.host.requestClear("idle");
    }
  }
}
