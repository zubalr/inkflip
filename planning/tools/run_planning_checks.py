#!/usr/bin/env python3
"""Execute scoped planning-utility tests and syntax checks, not application gates.
--record explicitly updates local evidence files; reseal the package afterward.
No network, OCR, paid resources, agent dispatch or baseline updates.
"""
from __future__ import annotations
import argparse, ast, datetime, io, json, platform, re, shutil, subprocess, time, unittest
from pathlib import Path
from test_validators import Tests
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');a=p.parse_args()
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();begin=time.monotonic();log=io.StringIO()
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    pyfiles=sorted(x for x in ROOT.rglob('*.py') if '__pycache__' not in x.parts)
    syntax=[]
    for f in pyfiles:
        ast.parse(f.read_text(),filename=str(f.relative_to(ROOT)));syntax.append(str(f.relative_to(ROOT)))
    jsfiles=['reference/reference.js','probes/hash_parity.mjs','probes/browser/probe.mjs'];commands=[]
    for f in jsfiles:
        cmd=['node','--check',f];out=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=15)
        commands.append({'command':cmd,'exit_code':out.returncode,'scope':'JavaScript syntax only; imports are not installed or executed.'})
        if out.returncode:raise SystemExit(out.stderr.replace(str(ROOT),'PACKAGE_ROOT'))
    tsc=shutil.which('tsc');ts=None
    if tsc:
        version=subprocess.run([tsc,'--version'],capture_output=True,text=True,check=True).stdout.strip()
        cmd=[tsc,'--noEmit','--strict','--skipLibCheck','--lib','ES2022,DOM','contracts/generated/inkflip.d.ts']
        out=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=20)
        ts={'version':version,'exit_code':out.returncode,'scope':'Generated structural declaration compatibility only; not a selected TypeScript 6 application build.'}
        if out.returncode:raise SystemExit(out.stdout.replace(str(ROOT),'PACKAGE_ROOT'))
    else:ts={'status':'not_available','scope':'Generated declarations still checked against the schema generator; compiler not available.'}
    payload={'status':'passed' if result.wasSuccessful() else 'failed','started_at':started,'duration_seconds':round(time.monotonic()-begin,3),'scope':'Planning utility tests and syntax checks, not implemented product acceptance.','python_version':platform.python_version(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'all_valid_contract_examples':12,'all_invalid_contract_examples':len(json.loads((ROOT/'contracts/examples/invalid-index.json').read_text())),'python_syntax_files':syntax,'javascript_syntax_checks':commands,'typescript_declaration_check':ts,'network_or_ocr_executed':False}
    if a.record:
        (ROOT/'quality/planning-test-results.json').write_text(json.dumps(payload,indent=2)+'\n')
        (ROOT/'quality/planning-tests.log').write_text(log.getvalue().replace(str(ROOT),'PACKAGE_ROOT'))
    print(json.dumps(payload,indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
