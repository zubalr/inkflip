#!/usr/bin/env python3
"""Original, deterministic PDF mechanisms. Fixed harmless samples, not a payload tool.
No font programs are embedded: uses PDF base-14 Helvetica. Stdlib only.
"""
from pathlib import Path
import argparse, hashlib, json

def pdf(objects):
    b=bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n'); offsets=[0]
    for n,obj in enumerate(objects,1):
        offsets.append(len(b)); b.extend(f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n')
    pos=len(b); b.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for off in offsets[1:]: b.extend(f'{off:010d} 00000 n \n'.encode())
    b.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{pos}\n%%EOF\n'.encode()); return bytes(b)

def stream(data):
    return f'<< /Length {len(data)} >>\nstream\n'.encode()+data+b'\nendstream'

def make(amount_map=False, covered=False, rotation=0, unit=1, origin=False):
    head=b'BT /F0 16 Tf 48 352 Td (SYNTHETIC EXAMPLE) Tj ET\nBT /F0 12 Tf 48 320 Td (No real transaction. Reader behavior only.) Tj ET\n'
    body=head+b'BT /F1 48 Tf 48 220 Td ($100) Tj ET\n'
    if covered:
        body=head+b'BT /F0 48 Tf 48 220 Td ($1,000) Tj ET\n1 1 1 rg 44 208 220 62 re f\n0 0 0 rg BT /F0 48 Tf 48 220 Td ($100) Tj ET\n'
    body+=b'BT /F0 12 Tf 48 130 Td (Rendered marks and extracted text are separate.) Tj ET\n'
    cmap=b'/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n/CMapName /InkflipExample def\n/CMapType 2 def\n1 begincodespacerange\n<00> <FF>\nendcodespacerange\n'
    cmap+=b'3 beginbfchar\n<24> <0024>\n<30> <0030>\n<31> '+(b'<0031002C0030>' if amount_map else b'<0031>')+b'\nendbfchar\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n'
    boxes='/MediaBox [0 0 520 400] /CropBox [0 0 520 400]' if not origin else '/MediaBox [-20 -30 520 420] /CropBox [20 40 500 390]'
    objs=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
      f'<< /Type /Page /Parent 2 0 R {boxes} /Rotate {rotation} /UserUnit {unit} /Resources << /Font << /F0 4 0 R /F1 6 0 R >> >> /Contents 5 0 R >>'.encode(),
      b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',stream(body),
      b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding /ToUnicode 7 0 R >>',stream(cmap)]
    return pdf(objs)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'fixtures'); a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    spec={'mapping-amount.pdf':dict(amount_map=True),'mapping-control.pdf':{},'covered-amount.pdf':dict(covered=True)}
    for r in [0,90,180,270]: spec[f'geometry-{r}.pdf']=dict(rotation=r,unit=2,origin=True)
    rows=[]
    for name,kw in spec.items():
        data=make(**kw); (a.out/name).write_bytes(data); rows.append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'recipe':kw,'rights':'Original synthetic sample; no embedded font program','generator':'probes/make_fixtures.py'})
    (a.out/'generated-manifest.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps({'generated':len(rows)}))
if __name__=='__main__':main()
