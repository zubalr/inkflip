# Design system and component contracts

Canonical tokens: [design-tokens.json](design-tokens.json). Warm off-white canvas, near-white paper, deep ink text, restrained teal action and rust alternative-reader accents. The page should look like an object under examination, not a dashboard tile. Use a single modest paper shadow, no glass panels. Typeface stack is system UI plus Georgia for editorial headings and system monospace for raw technical values. No external font request or redistributed system font. Licensed embedded PDF fonts are a separate fixture/build audit.

Spacing scale is 4/8/12/16/24/32/48/64/96. Primary reading text >=16 px, captions >=13 px, interactive controls >=44 px. Raw JSON is optional, wraps or scrolls within its region, and never compresses the first screen. Line length 60–75 characters for explanatory prose. Focus uses a 3 px blue outline with 2 px offset, not a color-only change. Body/disabled/help text must remain readable; disabled text explains prerequisites.

| Component | Inputs / states | Output / required behavior |
|---|---|---|
| AppHeader | landing/workspace; narrow menu open/closed | Fixed allowlisted navigation only; local file state not in URL |
| InteractiveHero | prepared manifest, active Page/Reading/Compare | Persistent synthetic/prepared labels; flip actual stored output |
| LocalFileGate | idle/drag/validating/rejected/replace-confirm | One File object, no FormData/upload; byte/profile constraints |
| PagePicker | count, selected set, native/OCR limits | Explicit finite selection; virtualized thumbnails; complete denominator |
| RegionSelector | drag/keyboard/edit/committed | Canonical polygon plus visible OCR padding; no silent adjacent-field substitution |
| ReaderSelector | manifest support, prepared/active/unavailable | Named version and method; unavailable option with inline explanation |
| AssetPreparation | missing/downloading/verifying/cached/offline/error | Explicit static download action; no document fields in request |
| DocumentStage | raster/loading/failed; viewport; selected geometry | Bounded canvas, clipped labelled overlay, accessible reading-list sibling |
| ReadingPanel | raw/normalized; reader/occurrence selection | Raw API text preserved; scalar→DOM mapping; duplicate occurrence navigation |
| FindingCard | difference/structure/hypothesis/ambiguous/unmatched | Plain title, actual evidence, scope/limits, detail and export action |
| CoveragePanel | plan + all terminal results | Selected/full-page denominator; completed vs unsupported/error counts |
| ProgressBar | named stage + determinate/indeterminate units | Real progress only, polite stage announcements, cancel always available |
| LocalNote | editing/saved-in-memory; inclusion toggle | Separate human annotation, never edits reading output |
| ExportPreview | evidence/replay/diagnostic; selected data | Actual contents/bytes, original off by default, preview before download |
| ReportImporter | validating/accepted/missing-source/rejected | No HTML/ZIP execution; missing-source local chooser verifies digest |
| RunComparison | changed/ruled/coverage-loss/incomparable | No automatic improved/regressed judgment; baseline immutable |
| ClearControl | pending-run/dirty-report/cleared | Confirm destructive local replacement, generation reset, separate model purge |
| ErrorNotice | typed failure + retry eligibility | Keep usable evidence, specific failed check, no all-clear |

Every component has an empty, loading, normal, failure and keyboard story when applicable. Story fixtures must identify `contract_example` data; they cannot be used as measured gallery manifests. Visual tests include long names, long currency values, Arabic/RTL strings within LTR UI, emoji/supplementary scalars, malformed Unicode rejection, dense duplicate occurrences, and narrow-screen error copy. Use `bdi`/direction isolation for untrusted strings without changing their stored text.

The evidence overlay is a visualization, not a text source. Canvas has an accessible label and an adjacent ordered list of named readings and occurrence buttons. The list can be filtered by page/reader and is fully usable without canvas. Pagination/virtualization keeps a stable focus anchor and announces newly available counts; it cannot remove the active focused row. A visually blank PDF render still has a meaningful failed/empty/readers status.

No global toast is the sole home of an error. Successful downloads receive a short status announcement but the report preview remains inspectable. Error cards have stable IDs so a screen reader can return to the failed check after retry.
