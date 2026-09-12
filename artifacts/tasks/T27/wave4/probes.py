"""Bounded regression replay and in-memory mutations for e0e7d4c only."""
import sys,os,io,json,inspect,unittest,tempfile,dataclasses,importlib.util,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(sys.argv[1]); sys.path.insert(0,str(ROOT/'native'))
from inkflip.readers import tesseract as tr
from PIL import Image
spec=importlib.util.spec_from_file_location('ocr_tests',ROOT/'native/tests/ocr/test_ocr.py')
tests=importlib.util.module_from_spec(spec); spec.loader.exec_module(tests)
# Mutations below execute stub-only tests; this guard enforces it.
original_popen=subprocess.Popen
def guarded_popen(args,*pos,**kw):
 if Path(str(args[0])).name=='tesseract':
  assert Path(args[0]).read_bytes()[:2]==b'#!','real OCR forbidden in probes'
 return original_popen(args,*pos,**kw)
subprocess.Popen=guarded_popen
header='level\tconf\ttext\tleft\ttop\twidth\theight\n'
plan={'id':'replay','page_index':3,'capability':'ocr','region_id':None}
passed=0
with tempfile.TemporaryDirectory() as td:
 root=Path(td); binary=root/'tesseract'; binary.write_text('#!stub'); (root/'eng.traineddata').write_bytes(b'fake')
 with patch.dict(os.environ,{'TESSDATA_PREFIX':str(root)}):
  handle=tr.open_raster(tests.raster_png(101,51),None,1,{'canonical_to_raster':[1,0,0,1,0,0]})
  def run(crop=None,tsv=None):
   out=[]
   with patch.object(tr.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='',stdout=tsv or header+'5\t90\tw\t0\t0\t1\t1\n')):
    r=tr.extract(handle,plan,out.extend,binary=binary,crop=crop)
   json.dumps([r,out],allow_nan=False); return r,out
  def expect_failure(label,fn,reason,count=0):
   global passed
   r,out=fn(); assert r['status']=='failed' and r['reason'].startswith(reason),(label,r)
   assert len(out)==count and r['produced_occurrence_count']==count and len(r['retained_occurrence_ids'])==count
   print('PASS',label,r['reason'],'retained',count); passed+=1
  good='5\t90\t$100.\t0\t0\t1\t1\n'*257
  for label,row in [('short','5\t90\tlost\t0\t0\t1\n'),('zero width','5\t90\tw\t0\t0\t0\t1\n'),('zero height','5\t90\tw\t0\t0\t1\t0\n'),('negative width','5\t90\tw\t0\t0\t-1\t1\n'),('negative height','5\t90\tw\t0\t0\t1\t-1\n')]:
   expect_failure('257 then '+label,lambda row=row:run(tsv=header+good+row),'parser_error',257)
  crop=tr.plan_crop(handle,None,resize=(2,2)); huge=10**309
  for label,bad in [('inverse42',dataclasses.replace(crop,canonical_from_raster=42)),('inverse bigint',dataclasses.replace(crop,canonical_from_raster=[huge,0,0,1,0,0])),('resize bigint',dataclasses.replace(crop,resize=(huge,1))),('scale bigint',dataclasses.replace(crop,raster_scale=huge))]:
   expect_failure(label,lambda bad=bad:run(crop=bad),'geometry_unavailable')
  for label,meta in [('matrix bigint',{'canonical_to_raster':[huge,0,0,1,0,0]}),('scale bigint at open',{'raster_scale_px_per_pt':huge})]:
   try: tr.open_raster(tests.raster_png(2,2),None,1,meta); raise AssertionError('accepted invalid input')
   except tr.AdapterError as e: assert e.reason=='geometry_unavailable'; print('PASS',label,e.reason); passed+=1
  for error,reason in [(OSError('secret diagnostic'),'unreadable_pixels'),(MemoryError('secret diagnostic'),'resource_limit')]:
   with patch.object(Image.Image,'resize',side_effect=error):
    expect_failure('resize '+type(error).__name__,lambda:run(crop=crop),reason)
  handle.close()
print('Independent cases passed:',passed)
original=tr.extract; source=inspect.getsource(original)
def run_case(label,cls,method):
 r=unittest.TestResult(); cls(method).run(r)
 print(label,'tests',r.testsRun,'failures',len(r.failures),'errors',len(r.errors),'skips',len(r.skipped))
 return r
method='test_f08_fiducial_all_four_rotations'
assert run_case('CONTROL F08 all four',tests.TestWave2CanonicalGeometry,method).wasSuccessful()
line='canonical_point = _contract_apply(handle.canonical_from_raster, raster_point)'
mutant=source.replace(line,line+'\n                        canonical_point = (canonical_point[0]+10000, canonical_point[1]+10000)')
ns={};exec(compile(mutant,'<memory-mutant-plus10000>','exec'),tr.__dict__,ns);tr.extract=ns['extract']
try:
 r=run_case('MUTANT +10000pt F08 KILLED',tests.TestWave2CanonicalGeometry,method)
 assert len(r.failures)==4 and not r.errors
finally: tr.extract=original
# Same established controls for the preserved non-axis-aligned and rounded path.
line='                    precision = "estimated"'
mutant=source.replace(line,'                    tl, br = polygon[0], polygon[2]\n                    polygon = [tl,[br[0],tl[1]],br,[tl[0],br[1]]]\n'+line)
ns={};exec(compile(mutant,'<memory-mutant-bbox>','exec'),tr.__dict__,ns);tr.extract=ns['extract']
try: assert not run_case('MUTANT bbox shear KILLED',tests.TestWave2CanonicalGeometry,'test_shear_quad_is_not_axis_aligned').wasSuccessful()
finally: tr.extract=original
with patch.object(tr.CropPlan,'crop_to_raster',lambda self,x,y:(x/self.resize[0]+self.padded[0],y/self.resize[1]+self.padded[1])):
 assert not run_case('MUTANT requested resize KILLED',tests.TestWave2Resize,'test_odd_resize_inverse_uses_actual_destination').wasSuccessful()
print('All light probes and intended mutant kills verified')
