#!/usr/bin/env python3
"""Validate this planning package offline. No application, network or cloud execution.
Checks links/files, closed domain schema/examples, task DAG/fields, traceability,
fixture hashes, generated types, safe static config and package SHA-256 manifest.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
import yaml
from jsonschema import Draft202012Validator
from contractlib import loads_strict, validate, ContractError
ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={'FILE_MANIFEST.json','SHA256SUMS.txt'}
SKIP_DIRS={'__pycache__','.git','node_modules'}
TASK_FIELDS={'id','title','status','owner_role','dependencies','gate','contract_version','input_files','current_code_anchors','purpose','deliverables','allowed_scope','forbidden_scope','non_goals','invariants','fixture_ids','test_ids','acceptance_criteria','commands','evidence_artifacts','failure_behavior','rollback','plan_mismatch','required_updates'}
REQUIRED=['START_HERE.md','PROJECT_BRIEF.md','PACKAGE_INDEX.md','PACKAGE_AUDIT.md','DECISIONS.md','ASSUMPTIONS_AND_PROBES.md','OWNER_INPUTS.md','LICENSE','architecture/TARGET_ARCHITECTURE.md','architecture/COORDINATES.md','architecture/CLI_AND_REGRESSION.md','architecture/REPORT_EXPORT_IMPORT.md','product/copy.json','product/ACCESSIBILITY.md','reference/index.html','contracts/inkflip.schema.json','contracts/generated/inkflip.d.ts','research/sources.json','research/upstream-ledger.json','research/experiments.json','quality/test-matrix.json','execution/tasks.json','execution/requirements.json','execution/gates.json','execution/COORDINATOR_PROMPT.md','execution/BOOTSTRAP_PROMPT.md','execution/OWNERSHIP.md','execution/RELEASE_CHECKLIST.md','deployment/wrangler.example.json','deployment/_headers','launch/CLAIMS_LEDGER.md','tools/test_validators.py','tools/seal_package.py','execution/gate-runner.json','reference/README.md']
class PackageError(ValueError):pass
def need(condition: bool, message: str):
    if not condition:raise PackageError(message)
def files(root: Path):
    return sorted(p for p in root.rglob('*') if p.is_file() and not any(s in SKIP_DIRS for s in p.relative_to(root).parts))
def sha(p: Path):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p: Path):return json.loads(p.read_text(encoding='utf-8'))
def safe_path(root: Path, name: str) -> Path:
    need(not name.startswith(('/', '\\')) and '\\' not in name and ':' not in name,'Unsafe package path '+name)
    p=(root/name).resolve();need(p.is_relative_to(root.resolve()),'Path escapes package '+name);return p
def check_dag(tasks: list[dict]) -> list[str]:
    by={t['id']:t for t in tasks};need(len(by)==len(tasks),'Duplicate task ID')
    for t in tasks:
        need(TASK_FIELDS<=set(t),f"Task {t.get('id')} missing fields: {TASK_FIELDS-set(t)}")
        need(re.fullmatch(r'T\d{2}',t['id']) is not None,'Invalid task ID')
        need(t['contract_version']=='1.0.0','Task contract mismatch')
        for k in ('title','owner_role','input_files','purpose','deliverables','allowed_scope','forbidden_scope','invariants','fixture_ids','test_ids','acceptance_criteria','commands','evidence_artifacts','failure_behavior','rollback','plan_mismatch','required_updates'):
            need(bool(t[k]),f"Task {t['id']} empty {k}")
        need(len(t['dependencies'])==len(set(t['dependencies'])),'Duplicate task dependency')
        need(set(t['dependencies'])<=set(by),f"Unknown task dependency {t['id']}")
    color={};order=[]
    def visit(tid):
        need(color.get(tid)!=1,'Task dependency cycle at '+tid)
        if color.get(tid)==2:return
        color[tid]=1
        for d in by[tid]['dependencies']:visit(d)
        color[tid]=2;order.append(tid)
    for tid in by:visit(tid)
    return order
def anchors(text: str) -> set[str]:
    out=set();counts={}
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*\s*$',text,re.M):
        h=re.sub(r'<[^>]+>','',heading);h=re.sub(r'\[([^]]+)\]\([^)]*\)',r'\1',h)
        h=re.sub(r'[^\w\- ]','',h.lower()).replace(' ','-');n=counts.get(h,0);counts[h]=n+1;out.add(h if not n else h+'-'+str(n))
    out.update(re.findall(r'id=["\']([^"\']+)["\']',text))
    return out
def check_links(root:Path) -> int:
    count=0
    depfile=root/'config/planning-probe-dependencies.json'
    declared=load(depfile) if depfile.exists() else []
    setup_refs={(x['source_file'],x['target']) for x in declared}
    for x in declared:
        need(safe_path(root,x['source_file']).is_file() and safe_path(root,x['setup_instructions']).is_file(),'Missing declared dependency instructions')
        need(x['status']=='not_installed_registry_blocked' and x['package']=='tesseract.js' and x['version']=='7.0.0','Unexpected probe dependency declaration')
    for p in files(root):
        if p.suffix.lower() not in ('.md','.html'):continue
        text=p.read_text();stripped=re.sub(r'```.*?```','',text,flags=re.S)
        links=re.findall(r'\[[^\]]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)',stripped) if p.suffix=='.md' else re.findall(r'(?:href|src)=["\']([^"\']+)["\']',text)
        for target in links:
            if target.startswith(('https:','http:','mailto:','data:','blob:','javascript:')):
                need(not target.startswith('javascript:'),'JavaScript link in '+str(p));continue
            if '{' in target or '$' in target:continue
            if (str(p.relative_to(root)),target) in setup_refs:
                # This exact installed npm asset is expressly not claimed as a
                # package file. Report separately; never waive arbitrary paths.
                continue
            target=unquote(target);parts=urlsplit(target)
            if not parts.path:dest=p
            else:dest=(p.parent/parts.path).resolve()
            need(dest.is_relative_to(root.resolve()),f'Link escapes package: {p.relative_to(root)} -> {target}')
            need(dest.exists(),f'Broken link: {p.relative_to(root)} -> {target}')
            if parts.fragment and dest.suffix=='.md':need(parts.fragment in anchors(dest.read_text()),f'Broken anchor: {p.relative_to(root)} -> {target}')
            count+=1
    return count
def check_integrity(root:Path) -> int:
    manifest=load(root/'FILE_MANIFEST.json');need(set(manifest['self_reference_exclusions'])==EXCLUDE,'Manifest exclusions changed')
    recorded={x['path']:x for x in manifest['files']};actual={str(p.relative_to(root)) for p in files(root)}-EXCLUDE
    need(set(recorded)==actual,'Manifest file set mismatch: '+str(sorted(set(recorded)^actual)))
    sums={}
    for line in (root/'SHA256SUMS.txt').read_text().splitlines():
        h,p=line.split('  ',1);sums[p]=h
    need(set(sums)==actual,'Checksum file set differs')
    for path,x in recorded.items():
        p=safe_path(root,path);need(p.stat().st_size==x['bytes'] and sha(p)==x['sha256']==sums[path],'Checksum mismatch '+path)
    return len(recorded)
def run(root:Path=ROOT, integrity:bool=True, required:bool=True) -> dict:
    root=root.resolve();allfiles=files(root)
    if required:
        for name in REQUIRED:need((root/name).is_file() and (root/name).stat().st_size>0,'Missing/nonempty required artifact '+name)
    for p in allfiles:
        need(not p.is_symlink(),'Symlink in package '+str(p));need(p.stat().st_size>0,'Empty artifact '+str(p.relative_to(root)))
        need(p.suffix.lower() not in ('.ttf','.otf','.woff','.woff2','.joblib','.pkl','.onnx','.wasm'),'Unnecessary/font/model binary '+str(p.relative_to(root)))
    for p in allfiles:
        if p.suffix.lower() in ('.md','.json','.py','.js','.mjs','.css','.html','.txt','.yml','.yaml'):
            text=p.read_text(encoding='utf-8')
            machine_prefixes=('/mnt/'+'data/','/home/'+'oai/','/Us'+'ers/')
            need(not any(x in text for x in machine_prefixes),'Machine-specific working path in '+str(p.relative_to(root)))
            secret_patterns=(r'ghp_[A-Za-z0-9]{30,}',r'AKIA[0-9A-Z]{16}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
            need(not any(re.search(x,text) for x in secret_patterns),'Credential-like content in '+str(p.relative_to(root)))
    jsoncount=0;yamlcount=0
    for p in allfiles:
        if p.suffix=='.json':load(p);jsoncount+=1
        elif p.suffix in ('.yaml','.yml'):yaml.safe_load(p.read_text());yamlcount+=1
    schema=load(root/'contracts/inkflip.schema.json');Draft202012Validator.check_schema(schema)
    refs=re.findall(r'"\$ref"\s*:\s*"([^"]+)"',json.dumps(schema))
    for ref in refs:need(ref.startswith('#/$defs/') and ref[8:] in schema['$defs'],'Nonlocal/invalid schema ref '+ref)
    validfiles=sorted((root/'contracts/examples/valid').glob('*.json'))
    for p in validfiles:validate(loads_strict(p.read_bytes()))
    invalids=load(root/'contracts/examples/invalid-index.json')
    for x in invalids:
        p=root/x['path']
        try:validate(loads_strict(p.read_bytes()))
        except ContractError as e:need(e.code==x['expected_code'],f"{x['path']}: expected {x['expected_code']}, got {e.code}")
        else:raise PackageError('Invalid fixture accepted '+x['path'])
    tasks=load(root/'execution/tasks.json');order=check_dag(tasks);tids={t['id'] for t in tasks};tests=load(root/'quality/test-matrix.json');testids={t['id'] for t in tests};reqs=load(root/'execution/requirements.json');gates=load(root/'execution/gates.json');gids={g['id'] for g in gates};fids={f['id'] for f in load(root/'quality/fixture-catalog.json')}
    need(len(testids)==len(tests),'Duplicate test ID');need(len({r['id'] for r in reqs})==len(reqs),'Duplicate requirement ID')
    for t in tasks:
        need(t['gate'] in gids,'Unknown gate');need(set(t['test_ids'])<=testids,'Unknown task test');need(set(t['fixture_ids'])<=fids,'Unknown task fixture')
        for path in t['input_files']:need(safe_path(root,path).is_file(),f"Task {t['id']} missing input {path}")
        for kind in ('workers','reviews'):need((root/f"execution/{kind}/{t['id']}.md").is_file(),'Missing task brief')
        need(any(t['id'] in r['task_ids'] for r in reqs),'Task has no requirement')
    for t in tests:
        need(set(t['task_ids'])<=tids and t['commands'] and t['assertions'],'Invalid test record');need(set(t['fixture_ids'])<=fids,'Test fixture unknown')
    for r in reqs:
        need(set(r['task_ids'])<=tids and r['task_ids'],'Requirement task unknown/empty');need(set(r['test_ids'])<=testids and r['test_ids'],'Requirement test unknown/empty');need(r['gate'] in gids,'Requirement gate unknown')
        for p in r['spec_files']:need(safe_path(root,p).is_file(),'Requirement spec missing '+p)
    for g in gates:
        need(g['task'] in tids and set(g['required_task_ids'])<=tids,'Gate task unknown')
        need(g['task'] not in g['required_task_ids'],'Gate cannot require its owner to be accepted before its scenario')
        need(g.get('scenario_commands') and not any('scripts/gate.py' in c for c in g['scenario_commands']),'Gate scenario is empty or recursive')
    runner=load(root/'execution/gate-runner.json')
    need(runner['recursive_gate_dispatch'] is False and runner['pre_release']['deploys'] is False,'Unsafe gate runner policy')
    need(set(runner['pre_release']['required_gate_ids'])<=gids,'Unknown prerequisite gate')
    sources=load(root/'research/sources.json');sids={s['id'] for s in sources};experiments=load(root/'research/experiments.json');pids={p['id'] for p in experiments}
    need(len(sids)==len(sources),'Duplicate source ID')
    for source in sources:
        for key in ('id','title','url','access_date','status','interpretation','remaining_verification'):
            need(bool(source.get(key)),f"Source {source.get('id')} missing {key}")
    need(len(pids)==len(experiments),'Duplicate experiment ID')
    pcolors={};pby={p['id']:p for p in experiments}
    def probe_visit(pid):
        need(pcolors.get(pid)!=1,'Experiment dependency cycle at '+pid)
        if pcolors.get(pid)==2:return
        pcolors[pid]=1
        for dep in pby[pid]['dependencies']:
            need(dep in pby,'Unknown experiment dependency');probe_visit(dep)
        pcolors[pid]=2
    for pid in pby:probe_visit(pid)
    for x in experiments:
        need(x['task'] in tids and set(x['source_ids'])<=sids and set(x['fixture_ids'])<=fids,'Experiment references invalid')
        need(set(x['dependencies'])<=pids,'Unknown probe dependency');need(safe_path(root,x['procedure']).is_file(),'Probe procedure missing '+x['procedure'])
        if x['execution_status'] in ('executed','blocked'):need(safe_path(root,x['result_artifact']).is_file(),'Missing actual probe/blocked receipt '+x['result_artifact'])
    # Generated original fixture digest agreement, not unexecuted expectation correctness.
    fm=load(root/'fixtures/generated-manifest.json')
    entries=fm['fixtures'] if isinstance(fm,dict) else fm
    for entry in entries:
        name=entry.get('file',entry.get('path',entry.get('name')));p=root/'fixtures'/name
        need(p.is_file() and sha(p)==entry['sha256'],'Fixture digest mismatch '+str(name))
    conf=load(root/'deployment/wrangler.example.json')
    need('assets' in conf and 'main' not in conf,'Not asset-only config')
    forbidden={'d1_databases','r2_buckets','kv_namespaces','queues','durable_objects','ai','containers','workflows','services','triggers'}
    need(not (forbidden&set(conf)),'Metered binding enabled');need(not conf['assets'].get('run_worker_first',False),'Dynamic Worker routing enabled')
    # Verify only current source-generated TS, not an installed browser implementation.
    import generate_types
    need((root/'contracts/generated/inkflip.d.ts').read_text()==generate_types.generate(),'Generated type drift')
    linkcount=check_links(root)
    integritycount=check_integrity(root) if integrity else 0
    return {'status':'passed','files':len(allfiles),'json_files':jsoncount,'yaml_files':yamlcount,'valid_contract_examples':len(validfiles),'invalid_contract_examples':len(invalids),'tasks':len(tasks),'tests':len(tests),'requirements':len(reqs),'gates':len(gates),'sources':len(sources),'experiments':len(experiments),'internal_package_links_checked':linkcount,'declared_uninstalled_probe_dependencies':len(load(root/'config/planning-probe-dependencies.json')),'checksums_verified':integritycount,'dag_acyclic':True,'first_ready_task':order[0] if order else None,'scope':'planning integrity, not implemented product acceptance'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--no-integrity',action='store_true',help='Before sealing only; does not verify manifest.');p.add_argument('--json',action='store_true');a=p.parse_args()
    try:r=run(integrity=not a.no_integrity)
    except Exception as e: print('PACKAGE VALIDATION FAILED: '+str(e),file=sys.stderr);raise SystemExit(1)
    print(json.dumps(r,indent=2) if a.json else '\n'.join(f'{k}: {v}' for k,v in r.items()))
if __name__=='__main__':main()
