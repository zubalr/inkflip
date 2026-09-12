"""Review-only bounded readers and direct Git byte comparison; no model imports."""
import hashlib, io, json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
BASE = '008ed367d6d7b462b72f00a22d8d2e40b89e442e'
def sha(data): return hashlib.sha256(data).hexdigest()
def child(path):
    import pypdf
    import pypdfium2 as pdfium
    data = path.read_bytes()
    result = {'path':str(path.relative_to(ROOT)), 'sha256':sha(data), 'bytes':len(data), 'pypdf':pypdf.__version__, 'pdfium':str(pdfium.PDFIUM_INFO), 'pypdfium2':str(pdfium.PYPDFIUM_INFO)}
    password = None
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        result['encrypted'] = reader.is_encrypted
        if reader.is_encrypted:
            result['empty_password'] = int(reader.decrypt(''))
            password = 'fixture'
            result['fixture_password'] = int(reader.decrypt(password))
        result['boxes'] = [list(map(float,p.mediabox)) for p in reader.pages]
        result['raw_text'] = [p.extract_text() for p in reader.pages]
    except Exception as e: result['reader_error'] = type(e).__name__+': '+str(e)
    try:
        with pdfium.PdfDocument(data,password=password) as doc:
            page = doc[0]
            width,height = page.get_size()
            scale = 256/max(width,height)
            bitmap = page.render(scale=scale)
            assert bitmap.width <= 257 and bitmap.height <= 257
            pixels = bytes(bitmap.buffer)
            result.update(size=[bitmap.width,bitmap.height], scale=scale, pixel_sha256=sha(pixels), dark_bytes=sum(v<128 for v in pixels))
            bitmap.close()
            page.close()
    except Exception as e: result['render_error'] = type(e).__name__+': '+str(e)
    print(json.dumps(result))
if len(sys.argv)>1:
    child(Path(sys.argv[1])); raise SystemExit
manifest=json.loads((ROOT/'fixtures/manifest.json').read_text())
old=json.loads(subprocess.check_output(['git','show',BASE+':fixtures/manifest.json'],cwd=ROOT))
verified=[]
for e in old['entries']:
    for name in (e['path'],e['expectations']):
        prior=subprocess.check_output(['git','show',BASE+':fixtures/'+name],cwd=ROOT)
        now=(ROOT/'fixtures'/name).read_bytes()
        assert prior==now,name
        verified.append({'path':name,'sha256':sha(now)})
results=[]
for e in manifest['entries']:
    if e['recipe'].get('version')!='g78.1' or not e['path'].endswith('.pdf'): continue
    run=subprocess.run([sys.executable,__file__,str(ROOT/'fixtures'/e['path'])],capture_output=True,text=True,timeout=10)
    assert run.returncode==0,run.stderr
    result=json.loads(run.stdout)
    result['stderr']=run.stderr
    results.append(result)
index={Path(r['path']).stem:r for r in results}
assert len(results)==23 and len(verified)==32
assert index['bad-pdf-encrypted']['empty_password']==0
assert index['bad-pdf-encrypted']['fixture_password']>0
assert index['bad-pdf-encrypted']['raw_text']==['$100']
for name in ('bad-pdf-truncated','bad-pdf-malformed'): assert 'render_error' in index[name]
assert index['duplicates-four']['raw_text'][0].count('$100')==4
for v in ('absent','malformed'): assert index['mapping-missing-'+v]['pixel_sha256']==index['mapping-missing-control']['pixel_sha256']
assert index['bad-pdf-encrypted']['pixel_sha256']==index['bad-pdf-control']['pixel_sha256']
for name in ('white-contrast-white','paint-order-after','unreadable-blank'): assert index[name]['dark_bytes']==0
for name in ('partial-clip-partial','partial-clip-triangle'): assert 0<index[name]['dark_bytes']<index['partial-clip-control']['dark_bytes']
print(json.dumps({'original_files_verified_against_git':verified,'results':results,'assertions':'passed'},indent=2))
