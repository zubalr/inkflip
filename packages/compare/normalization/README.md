# `@inkflip/compare/normalization` — scalar-whitespace-v1 (T12)

The normalized view of a raw reading plus the **reversible scalar-index
map** between the two. Raw text is never modified, dropped or re-ordered
(I03); normalization only collapses each maximal Unicode `White_Space`
run into one `U+0020` and keeps leading/trailing whitespace as that
single space.

The collapse itself is `normalize` from `@inkflip/contracts` — the same
function the report validator uses to recompute `normalized_text` and
`normalization_map`, so views produced here are byte-for-byte the
contract views. This module adds what the contract deliberately does
not: index conversion in both directions, raw-slice recovery and an
integrity check over the segment map.

## What it never does

Per `planning/architecture/ALIGNMENT_AND_FINDINGS.md`: no casefold, no
NFKC/NFKD, no ligature expansion, no combining-mark removal, no
punctuation removal, no minus-sign collapse. `"1,000"`, `"1000"`,
`"100"`, `"-100"`, `"not paid"` and `"paid"` stay different values.
Zero-width space and BOM are not `White_Space` and survive untouched.

## Index units

All indices are **Unicode scalar values** (code points), matching the
contract and the Python port — a supplementary character such as
`U+1F600` is one scalar here but two `string.length` units. Converting
to UTF-16 selection offsets is a UI-adapter concern and does not happen
in this package.

## API

| export | purpose |
| --- | --- |
| `normalizeText(raw)` | build `{ raw, rawScalars, text, scalars, map }` |
| `checkNormalizedView(view)` | structural integrity check; throws `ContractError 'NORMALIZATION'` |
| `normalizedToRawStart/End(view, i)` | normalized scalar index → raw offsets (runs map to the whole run) |
| `normalizedRangeToRaw(view, s, e)` | half-open normalized range → covering raw range |
| `rawToNormalized(view, i)` | raw scalar index → normalized index |
| `rawRangeToNormalized(view, s, e)` | half-open raw range → normalized range |
| `rawSlice(view, s, e)` | raw scalars `[s,e)` re-joined — raw text never rewritten |
| `rawSliceForNormalizedRange(view, s, e)` | raw substring behind a normalized range |
| `MATERIAL_SCALAR_RE` / `isMaterialScalar` | digits (Nd), currency (Sc), math signs (Sm), dashes (Pd) |
| `COMBINING_MARK_RE` / `isCombiningMark` | `M*` marks — must survive untouched |
| `isWhitespaceScalar` | `White_Space` membership (the contract `WS` table) |
| `NORMALIZATION_VERSION` | `'scalar-whitespace-v1'` |

## Executable example

```sh
node --input-type=module -e '
import { normalizeText, rawSliceForNormalizedRange, checkNormalizedView }
  from "./packages/compare/normalization/index.ts";
const view = normalizeText("  Total:\t$1,000.00   ");
checkNormalizedView(view);                    // throws if a map is invalid
console.log(view.text);                       // " Total: $1,000.00 "
const i = view.text.indexOf("$1,000.00");
console.log(rawSliceForNormalizedRange(view, i, i + 9)); // "$1,000.00"
'
```

Tests: `node --test tests/alignment/normalization.test.mjs`
