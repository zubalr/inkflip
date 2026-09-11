#!/usr/bin/env python3
"""Protocol model and synthetic parent timeout; not actual browser/PDF containment."""
from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Coordinator:
    def __init__(self):self.generation=0;self.digest=None;self.sequence={};self.completed={}
    def replace(self,digest):self.generation+=1;self.digest=digest;self.sequence={};self.completed={}
    def accept(self,generation,digest,job,seq,value):
        if generation!=self.generation or digest!=self.digest or seq<=self.sequence.get(job,-1):return False
        self.sequence[job]=seq;self.completed[job]=value;return True
    def cancel(self):self.generation+=1;self.sequence={}
def main():
    c=Coordinator();c.replace('A');g=c.generation;assert c.accept(g,'A','read',0,'old')
    c.replace('B');assert not c.accept(g,'A','read',1,'late-A');assert c.accept(c.generation,'B','good',0,[])
    assert not c.accept(c.generation,'B','good',0,['duplicate']);saved=dict(c.completed);old=c.generation;c.cancel();assert not c.accept(old,'B','bad',1,'late-B');assert c.completed==saved
    start=time.monotonic();p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    timed_out=False
    try:p.wait(timeout=.15)
    except subprocess.TimeoutExpired:
        timed_out=True;p.kill();p.wait(timeout=2)
    elapsed=round((time.monotonic()-start)*1000,2)
    assert timed_out and p.poll() is not None
    result={'status':'passed','scope':'small protocol model + one synthetic child timeout; not browser/parser watchdog proof','assertions':{'stale_document_rejected':True,'duplicate_sequence_rejected':True,'cancelled_generation_rejected':True,'empty_success_retained':True,'synthetic_child_terminated':True},'child_elapsed_ms':elapsed,'child_deadline_ms':150,'child_returncode':p.returncode}
    (ROOT/'probes/results/lifecycle-probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
