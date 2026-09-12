import os,sys,subprocess
from pathlib import Path
ROOT=Path(sys.argv[1]); os.chdir(ROOT)
# Defense in depth: this review must not invoke the installed engine for OCR.
original_popen=subprocess.Popen
real_engine=Path('/usr/bin/tesseract').resolve()
def guarded_popen(args,*pos,**kw):
 argv=args if isinstance(args,(list,tuple)) else [args]
 first=Path(str(argv[0]))
 if first.name=='tesseract':
  if first.resolve()==real_engine and list(argv[1:])!=['--version']:
   raise AssertionError('LIGHT REVIEW: real OCR invocation forbidden')
  if first.resolve()!=real_engine and first.read_bytes()[:2]!=b'#!':
   raise AssertionError('LIGHT REVIEW: unrecognized tesseract binary')
 return original_popen(args,*pos,**kw)
subprocess.Popen=guarded_popen
exclude=[
 'test_amount_line_is_recognized_with_canonical_geometry',
 'test_raw_punctuation_and_case_are_retained_verbatim',
 'test_f03_scan_ocr_reads_pixels_only_and_ignores_invisible_layer',
 'test_single_line_psm7_reads_amount_through_inverse_transform',
 'test_userunit_two_render_is_twice_the_physical_pixels',
 'test_blank_raster_completes_with_zero_occurrences',
 'test_timeout_is_a_distinct_terminal',
 'test_invocation_uses_only_neutral_generated_names',
 'test_every_occurrence_and_score_validate',
 'test_non_schema_region_key_is_not_a_plan_channel',
 'test_occurrence_id_includes_page_index',
 'test_explicit_prefix_model_is_hashed_and_pinned_in_argv',
]
import pytest
args=['native/tests/ocr','-q','-k','not ('+' or '.join(exclude)+')','--junitxml=/tmp/inkflip-t27-wave4-logs/light.xml']
print('pytest arguments:',args,flush=True)
raise SystemExit(pytest.main(args))
