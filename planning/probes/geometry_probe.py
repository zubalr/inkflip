#!/usr/bin/env python3
"""Analytical transform probe; does not claim browser overlay or parser correctness."""
from __future__ import annotations
import json, math, random, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from contractlib import apply, inverse

def compose(a,b):
    a0,a1,a2,a3,a4,a5=a;b0,b1,b2,b3,b4,b5=b
    return [a0*b0+a2*b1,a1*b0+a3*b1,a0*b2+a2*b3,a1*b2+a3*b3,a0*b4+a2*b5+a4,a1*b4+a3*b5+a5]
def rotation(deg,w,h):
    return {0:[1,0,0,1,0,0],90:[0,1,-1,0,h,0],180:[-1,0,0,-1,w,h],270:[0,-1,1,0,0,w]}[deg]
def main():
    rng=random.Random(8090);maximum=0.;count=10000
    for _ in range(count):
        cx,cy=rng.uniform(-100,100),rng.uniform(-100,100);w,h=rng.uniform(50,2000),rng.uniform(50,2000);u=rng.choice([.5,1,2,10]);deg=rng.choice([0,90,180,270]);s=rng.uniform(.25,4)
        c=[u,0,0,-u,-u*cx,u*(cy+h)];r=rotation(deg,w*u,h*u);z=[s,0,0,s,0,0];crop=[2,0,0,2,-24,-36]
        m=compose(crop,compose(z,compose(r,c)));p=[rng.uniform(cx,cx+w),rng.uniform(cy,cy+h)];back=apply(inverse(m),apply(m,p));e=max(abs(back[0]-p[0]),abs(back[1]-p[1]));maximum=max(maximum,e)
        assert e<=1e-5
    c=[2,0,0,-2,-40,780];p=[48,220];canonical=list(apply(c,p));display=list(apply(rotation(90,960,700),canonical));raster=list(apply([1.5,0,0,1.5,0,0],display));ocr=list(apply([2,0,0,2,-1000,-120],raster))
    assert canonical==[56,340] and display==[360,56] and raster==[540,84] and ocr==[80,48]
    # Independent corner expectations are not produced by the inverse under test.
    expected={0:[0,0],90:[700,0],180:[960,700],270:[0,960]}
    for deg,e in expected.items():assert list(apply(rotation(deg,960,700),[0,0]))==e
    result={'status':'passed','scope':'analytic affine math only; browser overlays not executed','seed':8090,'roundtrips':count,'max_error_pt':maximum,'tolerance_pt':1e-5,'worked_example':{'pdf_user':p,'canonical':canonical,'rotated':display,'raster':raster,'ocr_crop':ocr},'corner_cases':4}
    (ROOT/'probes/results/geometry-probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
