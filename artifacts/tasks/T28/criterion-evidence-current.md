# T28 criterion evidence — current candidate (cf01857)

Task-namespace evidence record for `acceptance_criteria_evidence` in
`artifacts/tasks/T28/receipt.json`. Each section maps one contract criterion
to the exact committed proof (tests, module behavior and executed commands).
Runs: see `artifacts/tasks/T28/run.json` (binds evaluated_commit) and
`artifacts/tasks/T28/commands.log` (full transcripts).

## Invisible-over-border and white-on-dark controls cannot produce universal hidden/visible verdict

- `native/tests/structure/test_structure.py::ManifestTests::test_no_verdict_fields_anywhere_in_the_module_output` — all three capabilities' complete output contains no hidden/visible/verdict/suspicious/safe string.
- `::PaintOverlapTests::test_white_on_dark_and_white_on_light_controls_get_no_verdict` — F04-style synthesized white-on-dark vs white-on-light controls: identical mode/color records (same locator and basis), schema-valid, no verdict-bearing output in any capability.
- `::RenderModeTests::test_f03_invisible_layer_recorded_without_alert` — F03 `3 Tr` invisible layer records 13 property observations; the raster-only control records none; no alert exists in either direction.
- Module: `native/inkflip/checks/structure.py` emits no verdict field; per-occurrence limitations state "not a hidden or visible verdict".

## no false “all checked”

- `::BudgetAndTerminalTests` — unsupported capability/region/page terminals; object-budget `resource_limit` retains prior evidence; cancellation terminal; closed-handle failure.
- `::UnsupportedCompositingTests` — alpha, non-Normal blend, stroking-alpha and nested-form contexts are flagged or bounded-recorded, never silently passed as fully inspected.
- `::ManifestTests::test_manifest_is_complete_and_schema_valid` — manifest declares approximate overlap support and the explicit no-universal-verdict limitation.
- The receipt's limitations array records the /OC BDC detection boundary explicitly.

## off-crop observation uses raw/native geometry while page display remains crop

- `::CropMetadataTests::test_off_crop_object_keeps_unclipped_native_geometry` — objects outside the crop window keep unclipped canonical polygons (corners outside the window asserted) with the "page display remains the crop" limitation.
- `::CropMetadataTests::test_page_properties_are_recorded` / `::test_userunit_page_properties_carry_it_once` — effective view, UserUnit (once) and physical size recorded from the pypdf dictionary path.

## unsupported compositing explicitly recorded.

- `::UnsupportedCompositingTests::test_transparent_text_is_flagged_per_occurrence_opaque_is_not` — `FPDFPageObj_HasTransparency`-driven per-occurrence limitation on the transparent object only.
- `::UnsupportedCompositingTests::test_non_normal_blend_mode_is_flagged_per_occurrence` — `/BM /Multiply` object flagged (non-Normal blend modes are HasTransparency coverage); scoped plain object is not.
- `::UnsupportedCompositingTests::test_stroking_alpha_is_flagged_symmetrically` — `/CA 0.5` stroke-mode text flagged via the stroke-alpha check; fill-only sibling is not.
- `::UnsupportedCompositingTests::test_alpha_fill_is_recorded_as_unsupported_compositing` and `::test_nested_form_xobject_is_not_traversed_and_recorded` — alpha fills and nested forms recorded, nested text never emitted as a text link.
- Receipt limitation: `/OC` BDC membership has no per-object getter on this binding; such objects may emit ordinary records — a completed check never certifies compositing coverage.
