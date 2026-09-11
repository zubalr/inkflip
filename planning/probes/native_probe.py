#!/usr/bin/env python3
"""Execute fixed synthetic fixtures with installed readers. Never opens user files."""
from pathlib import Path
import hashlib, importlib.metadata as metadata, json, subprocess, platform, re, os, time
from datetime import datetime, timezone
import pypdfium2 as pdfium
from pypdf import PdfReader
from PIL import Image, ImageChops
ROOT=Path(__file__).resolve().parents[1]
def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    started=datetime.now(timezone.utc).isoformat(); clock=time.perf_counter()
    out=ROOT/'probes/results';out.mkdir(parents=True,exist_ok=True)
    records=[]
    for path in sorted((ROOT/'fixtures').glob('*.pdf')):
        doc=pdfium.PdfDocument(path);page=doc[0];tp=page.get_textpage()
        text=tp.get_text_bounded()
        bm=page.render(scale=2);im=bm.to_pil().copy();bm.close()
        if not path.name.startswith('geometry'):im.save(out/(path.stem+'.png'))
        records.append({'fixture':path.name,'sha256':sha(path.read_bytes()),'pdfium_text':text,
          'pypdf_text':PdfReader(path).pages[0].extract_text(),'size':list(page.get_size()),
          'cropbox':list(page.get_cropbox()),'rotation':page.get_rotation(),
          'user_unit':PdfReader(path).pages[0].user_unit,'render_pixels':list(im.size)})
        tp.close();page.close();doc.close()
    a=Image.open(out/'mapping-amount.png');b=Image.open(out/'mapping-control.png')
    identical=ImageChops.difference(a,b).getbbox() is None
    crop=a.crop((80,244,400,390));crop.save(out/'amount-crop.png')
    cmd=['tesseract',str(out/'amount-crop.png'),'stdout','--psm','7','-l','eng']
    ocr=subprocess.run(cmd,text=True,capture_output=True,timeout=30,check=True)
    version=subprocess.run(['tesseract','--version'],text=True,capture_output=True,check=True).stdout.splitlines()[0]
    langs=subprocess.run(['tesseract','--list-langs'],text=True,capture_output=True,check=True)
    location=re.search(r'\"([^\"]+)\"',langs.stdout+langs.stderr)
    data_dir=os.environ.get('TESSDATA_PREFIX') or (location.group(1) if location else None)
    eng=Path(data_dir)/'eng.traineddata' if data_dir else None
    model=eng.read_bytes() if eng and eng.is_file() else None
    result={'started_at':started,'duration_ms':round((time.perf_counter()-clock)*1000),'status':'passed','scope':'fixed synthetic native probe; not browser/product validation',
     'environment':{'python':platform.python_version(),'platform':platform.system(),
      'machine':platform.machine(),'pypdfium2':metadata.version('pypdfium2'),
      'pdfium':str(pdfium.PDFIUM_INFO),'pypdf':metadata.version('pypdf'),
      'pillow':metadata.version('Pillow'),'tesseract':version},
     'assertions':{'same_render_bytes':identical,'mapped_reading':'$1,000' in next(r['pdfium_text'] for r in records if r['fixture']=='mapping-amount.pdf'),
       'control_reading':'$1,000' not in next(r['pdfium_text'] for r in records if r['fixture']=='mapping-control.pdf'),
       'ocr_crop_amount':ocr.stdout.strip()=='$100'},
     'ocr':{'stdout':ocr.stdout,'stderr':ocr.stderr,'psm':7,'crop_pixels':[80,244,400,390],
       'render_scale':2,'model_sha256':sha(model) if model else None,
       'model_bytes':len(model) if model else None,
       'model_git_blob':hashlib.sha1(b'blob '+str(len(model)).encode()+b'\0'+model).hexdigest() if model else None},
     'records':records}
    if not all(result['assertions'].values()):result['status']='failed'
    (out/'native-probe.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'assertions':result['assertions'],'environment':result['environment'],'ocr':result['ocr']},indent=2))
    raise SystemExit(0 if result['status']=='passed' else 1)
if __name__=='__main__':main()
