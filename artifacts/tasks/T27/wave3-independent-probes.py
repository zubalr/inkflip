"""Independent bounded T27 probes; no checkout writes or real OCR."""
import io,sys,os,json,dataclasses,tempfile,inspect,unittest,importlib.util
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(sys.argv[1]); sys.path.insert(0,str(ROOT/'native'))
from inkflip.readers import tesseract as tr
from PIL import Image
from pypdfium2 import PdfDocument
spec=importlib.util.spec_from_file_location('ocr_tests',ROOT/'native/tests/ocr/test_ocr.py')
tests=importlib.util.module_from_spec(spec); spec.loader.exec_module(tests)
head='level\tconf\ttext\tleft\ttop\twidth\theight\n'
def png(w=101,h=51):
 b=io.BytesIO(); Image.new('L',(w,h),255).save(b,format='PNG'); return b.getvalue()
P={'id':'independent','page_index':2,'capability':'ocr','region_id':None}
with tempfile.TemporaryDirectory() as td:
 root=Path(td); binary=root/'tesseract'; binary.write_text('stub'); (root/'eng.traineddata').write_bytes(b'fake-eng')
 with patch.dict(os.environ,{'TESSDATA_PREFIX':str(root)}):
  h=tr.open_raster(png(),None,1,{'canonical_to_raster':[1,0,0,1,0,0]})
  def run(h=h,crop=None,tsv=None):
   out=[]
   with patch.object(tr.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='',stdout=tsv or head+'5\t90\t$100.\t0\t0\t1\t1\n')):
    r=tr.extract(h,P,out.extend,binary=binary,crop=crop)
   json.dumps(out,allow_nan=False); return r,out
  def check(label,fn):
   try: print(label,fn())
   except Exception as e: print(label,'RAW',type(e).__name__,str(e))
  # Precisely bounded cases at changed validation/TSV seams.
  for body in ('5\t90\tlost\t0\t0\t1\n','5\t90\tzero\t0\t0\t0\t1\n','5\t90\tnegative\t0\t0\t-1\t1\n'):
   check('TSV '+repr(body),lambda:run(tsv=head+body))
  crop=tr.plan_crop(h,None,resize=(2,2))
  check('crop inverse integer',lambda:run(crop=dataclasses.replace(crop,canonical_from_raster=42)))
  check('huge int matrix',lambda:tr.open_raster(png(),None,1,{'canonical_to_raster':[10**309,0,0,1,0,0]}))
  check('huge int resize',lambda:run(crop=dataclasses.replace(crop,resize=(10**309,1))))
  with patch.object(Image.Image,'resize',side_effect=OSError('injected allocation failure')):
   check('resize OSError',lambda:run(crop=crop))
  # More than one full chunk proves accumulated counts survive a parser error.
  good='5\t90\t$100.\t0\t0\t1\t1\n'*257
  r,out=run(tsv=head+good+'5\tnan\tbad\t0\t0\t1\t1\n'); assert r['status']=='failed' and len(out)==257 and len(r['retained_occurrence_ids'])==257
  print('PASS partial parser failure retains 257 words and ids')
  for conf in ('nan','inf','-inf'):
   r,out=run(tsv=head+f'5\t{conf}\tword\t0\t0\t1\t1\n'); assert r['status']=='failed' and not out
  print('PASS nonfinite confidence rejected')
  # Actual F08 UserUnit-2 fiducial: 372,250..472,350 user coordinates,
  # physical canonical (744,100)..(944,300); s=.5 -> square in 520x400 raster.
  configs={
   0:([.5,0,0,.5,0,0],(372,50,100,100),[[744,100],[944,100],[944,300],[744,300]]),
   90:([0,.5,-.5,0,400,0],(250,372,100,100),[[744,300],[744,100],[944,100],[944,300]]),
   180:([-.5,0,0,-.5,520,400],(48,250,100,100),[[944,300],[744,300],[744,100],[944,100]]),
   270:([0,-.5,.5,0,0,520],(50,48,100,100),[[944,100],[944,300],[744,300],[744,100]])}
  data=(ROOT/'fixtures/development/userunit-2.pdf').read_bytes()
  for rot,(matrix,box,expected) in configs.items():
   with PdfDocument(data) as doc:
    page=doc[0]; bitmap=page.render(scale=1,rotation=rot); image=bitmap.to_pil().copy(); bitmap.close(); page.close()
   x,y,w,hh=box; gray=image.convert('L'); assert min(gray.getpixel((xx,yy)) for xx in range(x-1,x+2) for yy in range(y+48,y+53))<200
   b=io.BytesIO(); image.save(b,format='PNG'); handle=tr.open_raster(b.getvalue(),None,1,{'canonical_to_raster':matrix})
   r,out=run(h=handle,tsv=head+f'5\t90\tfiducial\t{x}\t{y}\t{w}\t{hh}\n')
   assert r['status']=='completed' and out[0]['geometry']['polygon']==expected,(rot,out)
   print('PASS independent F08 anchor',rot,image.size,out[0]['geometry']['polygon']); handle.close()
  h.close()
# In-memory mutants leave the immutable source file untouched.
original=tr.extract; src=inspect.getsource(original)
def test_run(label,cls,method):
 result=unittest.TestResult(); cls(method).run(result)
 print(label,'run',result.testsRun,'failures',len(result.failures),'errors',len(result.errors),'skips',len(result.skipped))
 return result.wasSuccessful()
assert test_run('control rotation',tests.TestWave2CanonicalGeometry,'test_all_four_rotations_with_real_tiny_renders')
assert test_run('control numeric',tests.TestWave2CanonicalGeometry,'test_contract_numeric_example_recovers_56_340')
needle='canonical_point = _contract_apply(handle.canonical_from_raster, raster_point)'
mut=src.replace(needle,needle+'\n                        canonical_point = (canonical_point[0]+10000, canonical_point[1]+10000)')
ns={}; exec(compile(mut,'<memory-mutant-offset>','exec'),tr.__dict__,ns); tr.extract=ns['extract']
try:
 assert test_run('MUTANT +10000pt rotation SURVIVES',tests.TestWave2CanonicalGeometry,'test_all_four_rotations_with_real_tiny_renders')
 assert not test_run('MUTANT +10000pt numeric KILLED',tests.TestWave2CanonicalGeometry,'test_contract_numeric_example_recovers_56_340')
finally: tr.extract=original
needle='                    precision = "estimated"'
mut=src.replace(needle,'                    tl, br = polygon[0], polygon[2]\n                    polygon = [tl, [br[0],tl[1]], br, [tl[0],br[1]]]\n'+needle)
ns={}; exec(compile(mut,'<memory-mutant-bbox>','exec'),tr.__dict__,ns); tr.extract=ns['extract']
try: assert not test_run('MUTANT two-corner bbox shear KILLED',tests.TestWave2CanonicalGeometry,'test_shear_quad_is_not_axis_aligned')
finally: tr.extract=original
# Resize regression must detect using requested factors in the inverse.
with patch.object(tr.CropPlan,'crop_to_raster',lambda self,x,y:(x/self.resize[0]+self.padded[0],y/self.resize[1]+self.padded[1])):
 assert not test_run('MUTANT requested-factor inverse KILLED',tests.TestWave2Resize,'test_odd_resize_inverse_uses_actual_destination')
print('All bounded probes completed')
