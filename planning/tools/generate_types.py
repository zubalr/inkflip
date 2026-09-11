#!/usr/bin/env python3
"""Generate TS structural types from the exact, closed schema constructs used here.
Semantic constraints (bounds, references, hashes) remain runtime validation rules.
No dependencies or network. --check exits nonzero on generated drift.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'contracts/inkflip.schema.json'
OUTPUT = ROOT / 'contracts/generated/inkflip.d.ts'
KNOWN = {'$schema','$id','$defs','$ref','title','description','type','const','enum','oneOf','anyOf','allOf','properties','required','additionalProperties','items','prefixItems','minItems','maxItems','uniqueItems','minimum','maximum','exclusiveMinimum','exclusiveMaximum','minLength','maxLength','pattern','format','default','contentEncoding','contentMediaType'}
def ts(s: dict | bool) -> str:
    if isinstance(s,bool): return 'unknown' if s else 'never'
    unknown = set(s) - KNOWN
    if unknown: raise ValueError(f'Unsupported schema keywords: {sorted(unknown)}')
    if '$ref' in s:
        if not s['$ref'].startswith('#/$defs/'): raise ValueError('Only local definitions permitted')
        return s['$ref'].split('/')[-1]
    if 'const' in s: return json.dumps(s['const'],ensure_ascii=False)
    if 'enum' in s: return ' | '.join(json.dumps(v,ensure_ascii=False) for v in s['enum'])
    for kind,sep in [('oneOf',' | '),('anyOf',' | '),('allOf',' & ')]:
        if kind in s: return '('+sep.join(ts(x) for x in s[kind])+')'
    t=s.get('type')
    if isinstance(t,list):
        return '('+' | '.join(ts(dict(s,type=x)) for x in t)+')'
    if t in ('number','integer'): return 'number'
    if t=='string': return 'string'
    if t=='boolean': return 'boolean'
    if t=='null': return 'null'
    if t=='array':
        if 'prefixItems' in s:
            items=s['prefixItems'];n=len(items)
            if s.get('minItems')!=n or s.get('maxItems')!=n: raise ValueError('Nonfixed tuple unsupported')
            return '['+', '.join(ts(x) for x in items)+']'
        child=ts(s.get('items',True))
        if s.get('minItems')==s.get('maxItems') and 'minItems' in s and s['minItems']<=12:
            return '['+', '.join([child]*s['minItems'])+']'
        return 'Array<'+child+'>'
    if t=='object':
        fields=[];required=set(s.get('required',[]))
        for key,child in s.get('properties',{}).items():
            fields.append(json.dumps(key)+('' if key in required else '?')+': '+ts(child)+';')
        ap=s.get('additionalProperties',True)
        if ap is not False: raise ValueError('Only closed domain objects supported')
        return '{ '+ ' '.join(fields)+' }'
    raise ValueError(f'Unsupported schema node: {s}')
def generate() -> str:
    schema=json.loads(SCHEMA.read_text())
    lines=['// GENERATED from contracts/inkflip.schema.json. Do not edit.', '// Structural types only; validate cross-references, bounds and evidence semantics at runtime.', '// Schema 1.0.0; regenerate with tools/generate_types.py.','']
    for name,value in schema['$defs'].items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',name): raise ValueError('Invalid TS definition name')
        lines.append('export type '+name+' = '+ts(value)+';')
    lines.append('export type InkflipArtifact = '+ts({k:v for k,v in schema.items() if k not in ('$defs','$schema','$id','title','description')})+';')
    return '\n\n'.join(lines)+'\n'
def main() -> None:
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();out=generate()
    if a.check:
        if not OUTPUT.exists() or OUTPUT.read_text()!=out: raise SystemExit('Generated type drift; run tools/generate_types.py')
        print('Generated types match schema')
    else:
        OUTPUT.parent.mkdir(parents=True,exist_ok=True);OUTPUT.write_text(out);print(OUTPUT.relative_to(ROOT))
if __name__=='__main__':main()
