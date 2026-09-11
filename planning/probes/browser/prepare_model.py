#!/usr/bin/env python3
"""Copy only an explicitly supplied, hash-verified model. No downloads."""
import argparse, hashlib
from pathlib import Path
EXPECTED='7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'
p=argparse.ArgumentParser();p.add_argument('--eng',required=True,type=Path);a=p.parse_args();data=a.eng.read_bytes()
if len(data)!=4113088 or hashlib.sha256(data).hexdigest()!=EXPECTED:raise SystemExit('Wrong English model size/hash; refusing')
out=Path(__file__).resolve().parent/'assets';out.mkdir(exist_ok=True);(out/'eng.traineddata').write_bytes(data)
print('Verified local model copied. Preserve Apache-2.0 notice before redistributing a run package.')
