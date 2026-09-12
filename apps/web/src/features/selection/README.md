# `features/selection` — explicit page and region selection (T08)

Implements Journey B's "page picker" and bounded region specification:
default selection is page 1 only, a run can cover at most the profile page
cap, and no page is ever silently excluded — refusals surface the cap and
the summary always states true selected/total counts.

## Layout

| File | Role |
|---|---|
| `pages.ts` | `PageSelection` — bounded 0-based index set; `selectAll()` caps at `limit` and reports `truncated`; out-of-cap mutations return `"limit"` |
| `region.ts` | Region math: `validateRegionBox` (in-bounds + positive area, never silently clamped), `draggedBox`, `regionToContract` (schema `Region` in `canonical_page` space), `paddedRasterRegion` (8 raster px or 10% of region height, clipped — READER_ADAPTER_CONTRACT), display↔canonical rotation mapping |
| `PagePicker.tsx` | Summary, select-all-up-to-limit, clear, windowed toggle list (48/window, jump for long documents), cap notice |
| `RegionEditor.tsx` | Real bounded raster + drag + numeric pt inputs + padding outline + label |

## Contract notes

- Region ids follow `region_p{page}_{ordinal}`; the geometry records the
  page's `raw_to_canonical` transform id and `precision: "exact"` (user-
  supplied bounds), never a reader-inferred location.
- Drag coordinates cross display→canonical through the document rotation
  only; numeric input is already canonical pt and is validated, not
  clamped.
- The padded OCR crop and the original region stay distinct records, shown
  as separate outlines.
