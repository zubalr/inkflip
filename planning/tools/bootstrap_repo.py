#!/usr/bin/env python3
"""Copy planning into a NEW local directory; optional git init only. No install/network/commit."""
from __future__ import annotations
import argparse, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def bootstrap(destination: Path, init_git: bool=False) -> None:
    destination=destination.expanduser().resolve()
    if destination==ROOT or ROOT in destination.parents:
        raise ValueError('Destination must be outside the planning package')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Refusing a nonempty destination. Never bootstrap over the original repository.')
    destination.mkdir(parents=True,exist_ok=True)
    shutil.copytree(ROOT,destination/'planning',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (destination/'execution').mkdir()
    shutil.copyfile(ROOT/'execution/state.example.json',destination/'execution/state.json')
    if init_git:
        subprocess.run(['git','init','-b','main',str(destination)],check=True)
    print('Created local planning checkout. No remote, dependency install, commit or deployment occurred.')
    print('Next: give planning/execution/BOOTSTRAP_PROMPT.md to the T01 implementation session.')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path);p.add_argument('--init-git',action='store_true');a=p.parse_args()
    try:bootstrap(a.destination,a.init_git)
    except (ValueError,subprocess.CalledProcessError) as e:raise SystemExit(str(e))
if __name__=='__main__':main()
