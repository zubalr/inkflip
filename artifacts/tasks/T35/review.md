# T35 Task Review: Runnable Local Reader-Upgrade CI Example

## Task Information
- **Task ID**: T35
- **Beads ID**: pdf-t35
- **Gate**: G3
- **Deliverables**:
  - `examples/reader-upgrade/`
  - `docs/READER_UPGRADE.md`
  - `tests/examples/`
  - `artifacts/tasks/T35/`

## Acceptance Criteria Verification
1. **Example runs end-to-end locally**:
   - Both `examples/reader-upgrade/run.sh` and `test_reader_upgrade.py` execute end-to-end with no network, external SaaS, or cloud dependencies.
   - Tested and verified: profiles installed, corpus inspected, baseline created, comparison evaluated, HTML report exported.
2. **Before/after identities differ as intended**:
   - `prof_before` executable and version (`5.9.0`) differ strictly from `prof_after` (`6.18.0`).
   - Generated reports record differing reader version metadata.
3. **Known rule-failing mutation exits 5 without modifying baseline**:
   - Deliberate mutation of approved text triggers violation of `stable_reading` rule.
   - CLI compare and baseline comparison exit with status 5 (`EXIT_REGRESSION`).
   - Baseline SHA-256 remains byte-identical before and after the failing comparison.
4. **Output reopens in web viewer**:
   - Validated schema conformity via `inkflip validate`.
   - Standalone portable HTML report generated with strict CSP (`default-src 'none'; img-src data:; style-src ...`).
5. **README commands copied verbatim into test**:
   - All documented CLI commands in `examples/reader-upgrade/README.md` are assert-checked verbatim in `test_readme_commands_copied_verbatim_into_test`.

## Evidence Summary
- **Tests**: 3 collected, 3 passed, 0 failed, 0 skipped.
- **Verification Command**: `uv run --project native python -m unittest discover -s tests/examples -v`
