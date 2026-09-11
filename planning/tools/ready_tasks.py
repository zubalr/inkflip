#!/usr/bin/env python3
"""List dependency-ready tasks. Read-only; does not launch agents or contact providers."""
from __future__ import annotations
import argparse, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TERMINAL={'accepted','rejected_complete'}
EXPERIMENTS={'T41','T42','T43','T44','T45'}
def ready(tasks: list[dict], state: dict) -> list[dict]:
    byid={t['id']:t for t in tasks};entries=state.get('tasks',{})
    unknown=set(entries)-set(byid)
    if unknown: raise ValueError(f'Unknown state tasks: {sorted(unknown)}')
    def status(tid): return entries.get(tid,{}).get('status',byid[tid]['status'])
    for tid in byid:
        if status(tid)=='rejected_complete' and tid not in EXPERIMENTS:
            raise ValueError(f'{tid} is not an optional technique experiment')
    return [t for t in tasks if status(t['id'])=='planned' and all(status(d) in TERMINAL for d in t['dependencies'])]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path);p.add_argument('--json',action='store_true');a=p.parse_args()
    tasks=json.loads((ROOT/'execution/tasks.json').read_text());state=json.loads(a.state.read_text()) if a.state else {}
    try:out=ready(tasks,state)
    except ValueError as e:raise SystemExit(str(e))
    if a.json: print(json.dumps(out,indent=2))
    else:
        print('State-derived ready tasks; verify merged evidence and ownership before dispatch:')
        for t in out:print(f"{t['id']} | {t['owner_role']} | {t['title']}")
        if not out:print('None. Inspect in-progress/review/blocked states and genuine dependencies.')
if __name__=='__main__':main()
