/**
 * Local candidate validation (T08) — MIME hint, %PDF- header sniff and the
 * profile size cap, all checked before the reader sees a byte.
 *
 * Order matters and is part of the contract: the declared size gate runs on
 * metadata alone, so an oversized candidate is rejected without allocating
 * or reading a single byte (the "without giant allocations" half of the
 * size-limit criterion). Only a ≤1 KiB header slice is read for the magic
 * check; full bytes are requested by the caller afterwards.
 *
 * Wrong declared type and a missing %PDF- header share the `not_pdf` bucket
 * (one canonical message, `input.notpdf`); encrypted, malformed, oversized
 * and over-long documents are distinct buckets downstream.
 */
import { OPEN_COPY, byteLimitLabel, fill } from "./copy";
import type { OpenProfile } from "./limits";
import { profileSizeLimitLabel } from "./limits";
import type { FileCandidate, OpenError } from "./types";

/** First-N-bytes window scanned for the %PDF- magic (ISO 32000 header
 *  may sit inside the first KiB behind binary junk). */
export const HEADER_SNIFF_BYTES = 1024;

/** Declared types that carry no format claim — the header decides. */
const GENERIC_TYPES = new Set(["", "application/octet-stream"]);

function error(kind: OpenError["kind"], message: string, detail?: string): OpenError {
  return detail === undefined
    ? { kind, message }
    : { kind, message, detail };
}

/**
 * Size gate: rejects candidates above the profile byte cap using only the
 * declared size — no slice, no arrayBuffer, no allocation. An empty file
 * cannot contain a header and fails as `not_pdf` here too.
 */
export function validateCandidateSize(
  candidate: Pick<FileCandidate, "size">,
  profile: OpenProfile,
): OpenError | null {
  if (!Number.isFinite(candidate.size) || candidate.size < 0) {
    return error("malformed", OPEN_COPY.malformed, "size:unreadable");
  }
  if (candidate.size === 0) {
    return error("not_pdf", OPEN_COPY.notPdf, "header:empty");
  }
  if (candidate.size > profile.maxFileBytes) {
    return error(
      "too_large",
      fill(OPEN_COPY.tooBig, {
        actual: byteLimitLabel(candidate.size),
        limit: profileSizeLimitLabel(profile),
      }),
      `size:${candidate.size}>${profile.maxFileBytes}`,
    );
  }
  return null;
}

/**
 * Type+header gate over a ≤HEADER_SNIFF_BYTES slice. A declared type that
 * names a concrete non-PDF format is wrong even before the bytes are read;
 * a generic/absent type defers to the header, which must contain `%PDF-`
 * inside the window.
 */
export function validateCandidateHeader(
  header: Uint8Array,
  declaredType: string,
): OpenError | null {
  const type = declaredType.trim().toLowerCase();
  if (!GENERIC_TYPES.has(type) && type !== "application/pdf") {
    return error(
      "not_pdf",
      OPEN_COPY.notPdf,
      `mime:${type.slice(0, 64)}`,
    );
  }
  const window = header.subarray(0, Math.min(header.length, HEADER_SNIFF_BYTES));
  let found = false;
  for (let i = 0; i + 5 <= window.length; i++) {
    if (
      window[i] === 0x25 && // %
      window[i + 1] === 0x50 && // P
      window[i + 2] === 0x44 && // D
      window[i + 3] === 0x46 && // F
      window[i + 4] === 0x2d // -
    ) {
      found = true;
      break;
    }
  }
  if (!found) {
    return error("not_pdf", OPEN_COPY.notPdf, "header:no-%PDF-magic");
  }
  return null;
}

/**
 * Full pre-reader validation: size gate, then a bounded header read.
 * Returns the first failure — never proceeds past a rejection.
 */
export async function validateCandidate(
  candidate: FileCandidate,
  profile: OpenProfile,
): Promise<OpenError | null> {
  const sizeFailure = validateCandidateSize(candidate, profile);
  if (sizeFailure !== null) return sizeFailure;
  let header: Uint8Array;
  try {
    header = new Uint8Array(
      await candidate
        .slice(0, Math.min(candidate.size, HEADER_SNIFF_BYTES))
        .arrayBuffer(),
    );
  } catch {
    return error("malformed", OPEN_COPY.malformed, "header:unreadable");
  }
  return validateCandidateHeader(header, candidate.type);
}
