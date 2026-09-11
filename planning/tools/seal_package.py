#!/usr/bin/env python3
"""Hash and validate this package; optionally produce a safe ZIP outside the package.
No network, application installation, repository mutation or deployment.
"""
from __future__ import annotations
import argparse, hashlib, json, zipfile
from pathlib import Path
from validate_package import ROOT, EXCLUDE, files, sha, run

def seal() -> dict:
    records=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)}
             for p in files(ROOT) if str(p.relative_to(ROOT)) not in EXCLUDE]
    manifest={'format':'inkflip-planning-manifest-v1','hash_algorithm':'sha256',
      'self_reference_exclusions':sorted(EXCLUDE),
      'exclusion_rule':'Only FILE_MANIFEST.json and SHA256SUMS.txt exclude themselves. Every other delivered artifact, including audit and index, is hashed.',
      'files':records}
    (ROOT/'FILE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (ROOT/'SHA256SUMS.txt').write_text(''.join(r['sha256']+'  '+r['path']+'\n' for r in records))
    return run()

def archive(destination:Path,replace:bool=False) -> dict:
    destination=destination.expanduser().resolve()
    if destination.is_relative_to(ROOT.resolve()):raise ValueError('ZIP must be outside the package to avoid self-inclusion.')
    if destination.exists() and not replace:raise ValueError('Destination exists; use --replace only for an intended regenerated archive.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    expected=[]
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in files(ROOT):
            name=ROOT.name+'/'+str(p.relative_to(ROOT));expected.append(name);z.write(p,name)
    with zipfile.ZipFile(destination) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or names!=expected:raise ValueError('ZIP inventory mismatch/duplicate paths.')
        if z.testzip() is not None:raise ValueError('ZIP CRC verification failed.')
        for n in names:
            if n.startswith(('/', '\\')) or '\\' in n or '..' in Path(n).parts:raise ValueError('Unsafe ZIP path.')
        for p in files(ROOT):
            data=z.read(ROOT.name+'/'+str(p.relative_to(ROOT)))
            if hashlib.sha256(data).hexdigest()!=sha(p):raise ValueError('Archived bytes differ: '+p.name)
    digest=sha(destination)
    destination.with_suffix(destination.suffix+'.sha256').write_text(digest+'  '+destination.name+'\n')
    return {'status':'passed','archive_name':destination.name,'archive_bytes':destination.stat().st_size,
            'sha256':digest,'entries':len(expected),'crc_and_all_archived_bytes_verified':True}

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--zip',type=Path);a.add_argument('--replace',action='store_true');args=a.parse_args()
    result={'package':seal()}
    if args.zip:result['archive']=archive(args.zip,args.replace)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
