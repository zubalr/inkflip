/**
 * Human-entered annotations (T23).
 *
 * Notes are the user's own words attached to a finding or a page. They are
 * NEVER machine readings: `origin` is pinned to the contract's
 * "human_entered" literal, they land only in `report.annotations` (never
 * `occurrences`), and they never overwrite or reinterpret evidence. The
 * export engine treats them as opt-in content and prunes notes whose
 * finding is not in the exported selection.
 *
 * Note identity is content-derived — the same text on the same finding
 * twice is still two notes (each carries a creation counter suffix), so a
 * repeated observation stays individually removable.
 */
import type { Annotation } from "../../../../../packages/contracts/src/index.ts";
import { digest } from "../../../../../packages/contracts/src/index.ts";

export interface NoteDraft {
  /** Finding the note attaches to; null means a page-level note. */
  readonly findingId: string | null;
  readonly pageIndex: number;
  readonly text: string;
  /** Optional user-supplied label (e.g. initials); never auto-filled. */
  readonly authorLabel?: string | null;
}

export const MAX_NOTE_CHARS = 2000;

let noteCounter = 0;

/**
 * Build a contract-valid human annotation from a draft. Returns null when
 * the text is empty — the UI disables the action rather than storing
 * placeholder content.
 */
export function createAnnotation(draft: NoteDraft): Annotation | null {
  const text = draft.text.trim();
  if (text.length === 0) return null;
  noteCounter += 1;
  const id = `note_${digest({
    finding: draft.findingId,
    page: draft.pageIndex,
    text,
    n: noteCounter,
  }).slice(0, 16)}`;
  const author = draft.authorLabel?.trim() ?? "";
  return {
    id,
    finding_id: draft.findingId,
    page_index: draft.pageIndex,
    text: text.slice(0, MAX_NOTE_CHARS),
    author_label: author.length > 0 ? author.slice(0, 80) : null,
    origin: "human_entered",
  };
}

/** Notes belonging to one finding (or the page-level note bucket). */
export function notesForFinding(
  notes: readonly Annotation[],
  findingId: string | null,
): Annotation[] {
  return notes.filter((n) => n.finding_id === findingId);
}
