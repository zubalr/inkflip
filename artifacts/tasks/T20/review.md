# T20 integration review — repeated/ambiguous/order/unmatched evidence UX

Reviewer: independent read-only review agent (two rounds, same reviewer resumed).
Implementer: Devin coordinator session (work/devin/t20, worktree pdf-t20).

Reviewed `102b79e` (implementation) against `f191be5`, then verified fix
commits `a3f1eef` and `cbfd8d4`. Full findings and per-item verdicts are in
`peer-review.md`.

Round 1 returned CHANGES-REQUIRED: a blocker (candidate pointer clicks
bubbled to the finding card and wiped the selection — first-candidate-wins
persisted for mouse input) and three majors (unconditional "same readings"
copy on order-only findings; one-sided findings mislabeled as page-level
comparisons; ambiguous findings under-naming the evaluated candidate set),
plus minors. All were fixed and verified in round 2, which returned
APPROVE-WITH-NOTES; its three new minor findings were also fixed.

Evidence executed: `bun run test:browser -- tests/browser/ambiguity.spec.ts`
(5/5, bound to 876f4c8 in run.json) plus a 33-test regression sweep across
viewer/open/g1/large-mobile specs (all green post-fix). A pre-spec
real-pipeline probe verified order-only and unmatched findings on actual
PDF.js/Tesseract output (documented in commands.log).

Inspected-but-untested seams and remaining limitations are recorded in
peer-review.md (example-doc surface for the ambiguous UI, basis-substring
detection for imported reports, pre-existing listbox ARIA structure, and
files touched outside the brief's owned paths disclosed as coordinator-seam
edits).

Verdict: approved for integration. This review does not close the product
task and does not claim gate completion.
