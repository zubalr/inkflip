#!/usr/bin/env python3
"""Python side of the T03 differential fuzz.

Reads a JSONL corpus ({"id", "doc"}) and emits {"id", "code"} JSONL where
code is 'OK', 'CE:<ContractError code>' or 'RAW:<exception type>'. The
Node driver tests/contracts/differential_fuzz.mjs compares these against
the TypeScript strict parser on identical input.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'native'))

from inkflip.contracts import ContractError, loads_strict  # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding='utf-8') as fh:
        for line in fh:
            row = json.loads(line)
            try:
                loads_strict(row['doc'])
                code = 'OK'
            except ContractError as exc:
                code = 'CE:' + exc.code
            except Exception as exc:  # leaked non-contract exception
                code = 'RAW:' + type(exc).__name__
            sys.stdout.write(
                json.dumps({'id': row['id'], 'code': code}) + '\n'
            )


if __name__ == '__main__':
    main()
