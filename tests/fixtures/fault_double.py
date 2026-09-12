"""Bounded F20 child; no reader imports, model loads, network or large memory.

The consumer must still enforce its own deadline. Even a broken consumer
cannot leave this fixture running beyond two seconds.
"""
import json
import sys
import time
from pathlib import Path


def main():
    scenario = json.loads(Path(sys.argv[1]).read_text())
    for event in scenario['events']:
        print(json.dumps(event), flush=True)
    mode = scenario['scenario']
    if mode == 'crash':
        return 17
    if mode in ('hang', 'cancel'):
        time.sleep(2)
        return 18
    if mode == 'stale':
        print(json.dumps({'generation': 1, 'job': 'old-job', 'state': 'completed', 'text': 'STALE'}), flush=True)
    print(json.dumps({'generation': 2, 'job': 'second', 'state': scenario['expected_terminal']}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
