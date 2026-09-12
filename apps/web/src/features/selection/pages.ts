/**
 * PageSelection (T08) — the explicit, bounded set of pages a run may cover.
 *
 * Contract: "page selection never silently excludes a page" and "a reader
 * cannot silently choose all 1,000 pages" (PRODUCT_AND_JOURNEYS Journey B).
 * The rules that enforce it:
 *
 * - Default is page 0 only — nothing is preselected beyond it.
 * - Every mutation that would exceed `limit` is REFUSED and recorded as
 *   `limited`: the UI surfaces the cap instead of dropping pages quietly.
 * - `selectAll()` selects the first `min(limit, total)` pages and reports
 *   `truncated` — an honest, visible cap, not a silent exclusion.
 * - `pages()` returns the sorted 0-based indices — exactly the set a plan
 *   may enumerate, so the check plan can never claim a page the user did
 *   not select.
 */
export type SelectResult = "ok" | "limit" | "invalid";

export interface SelectionSummary {
  readonly selected: number;
  readonly total: number;
  readonly limit: number;
  /** True when total > limit, so a full run cannot cover the document. */
  readonly truncated: boolean;
  /** Sticky: a mutation was refused by the cap since the last clear. */
  readonly limitHit: boolean;
}

export class PageSelection {
  readonly total: number;
  readonly limit: number;
  private readonly set = new Set<number>();
  private limited = false;

  constructor(total: number, limit: number) {
    this.total = Math.max(0, Math.floor(total));
    this.limit = Math.max(1, Math.floor(limit));
    if (this.total > 0) this.set.add(0); // explicit default: page 1 only
  }

  /** Sorted selected page indices (0-based). */
  pages(): number[] {
    return [...this.set].sort((a, b) => a - b);
  }

  has(index: number): boolean {
    return this.set.has(index);
  }

  get size(): number {
    return this.set.size;
  }

  /** A cap refusal happened since construction/last clear. */
  get limitHit(): boolean {
    return this.limited;
  }

  private valid(index: number): boolean {
    return Number.isInteger(index) && index >= 0 && index < this.total;
  }

  add(index: number): SelectResult {
    if (!this.valid(index)) return "invalid";
    if (this.set.has(index)) return "ok";
    if (this.set.size >= this.limit) {
      this.limited = true;
      return "limit";
    }
    this.set.add(index);
    return "ok";
  }

  remove(index: number): SelectResult {
    if (!this.valid(index)) return "invalid";
    this.set.delete(index);
    return "ok";
  }

  toggle(index: number): SelectResult {
    return this.set.has(index) ? this.remove(index) : this.add(index);
  }

  /**
   * Inclusive range add. Refuses atomically when the *entire* range would
   * not fit — a partially applied range would silently exclude pages.
   */
  addRange(from: number, to: number): SelectResult {
    const lo = Math.min(from, to);
    const hi = Math.max(from, to);
    if (!this.valid(lo) || !this.valid(hi)) return "invalid";
    const needed = hi - lo + 1 - [...this.set].filter((p) => p >= lo && p <= hi).length;
    if (this.set.size + needed > this.limit) {
      this.limited = true;
      return "limit";
    }
    for (let i = lo; i <= hi; i++) this.set.add(i);
    return "ok";
  }

  /**
   * Select the first `min(limit,total)` pages — the honest "everything the
   * run can cover" action. `truncated` in the summary says the rest remain
   * unchecked, visibly.
   */
  selectAll(): void {
    this.set.clear();
    const n = Math.min(this.limit, this.total);
    for (let i = 0; i < n; i++) this.set.add(i);
  }

  clear(): void {
    this.set.clear();
    this.limited = false;
  }

  summary(): SelectionSummary {
    return {
      selected: this.set.size,
      total: this.total,
      limit: this.limit,
      truncated: this.total > this.limit,
      limitHit: this.limited,
    };
  }
}
