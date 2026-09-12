/**
 * Reader availability for an imported report (I10).
 *
 * A report records which readers produced its evidence, but a report can
 * never select, install, or name an executable. The only thing that may
 * run is a reader the host already provides — an allowlist supplied by
 * the app, matched to recorded readers by exact `Reader.id` equality.
 * Recorded readers with no installed match are surfaced by name as
 * unavailable; nothing is silently substituted.
 */
import type { Reader, Report } from "../../contracts/src/index.ts";

/**
 * An installed, host-provided reader identity. The app supplies this
 * allowlist from its own adapters — never from report content.
 */
export interface InstalledReader {
  readonly id: string;
  readonly name: string;
  readonly version: string;
}

export interface ReaderAvailability {
  /** Recorded readers matched to the installed allowlist by id. */
  readonly available: readonly Reader[];
  /** Recorded readers with no installed match — named, never run. */
  readonly missing: readonly Reader[];
}

export function readerAvailability(
  report: Report,
  installed: readonly InstalledReader[],
): ReaderAvailability {
  const installedIds = new Set(installed.map((reader) => reader.id));
  const available: Reader[] = [];
  const missing: Reader[] = [];
  for (const reader of report.readers) {
    (installedIds.has(reader.id) ? available : missing).push(reader);
  }
  return { available, missing };
}

/** Display label for a reader record — name plus version, inert text. */
export function readerLabel(reader: Reader): string {
  return `${reader.name} ${reader.version}`;
}
