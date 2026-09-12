from pathlib import Path
import hashlib, json, shutil, subprocess, difflib
root = Path('/Users/zubair/Code/Projects/pdf project/worktrees/review-codex-q38')
out = Path('/private/tmp/inkflip-q38-review')
copy = out / 'patch-source'
copy.mkdir(exist_ok=True)
record = json.loads((root / 'config/dependency-patches.json').read_text())['tesseract.js@7.0.0']
installed = root / 'apps/web/node_modules/tesseract.js'
for name in record['files']:
    dest = copy / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(installed / name, dest)
subprocess.run(['git', 'apply', '--reverse', str(root / record['patch_path'])], cwd=copy, check=True)
for name, hashes in record['files'].items():
    assert hashlib.sha256((copy / name).read_bytes()).hexdigest() == hashes['upstream_sha256'], name
    print('Reconstructed upstream digest matches:', name)
base_patch = subprocess.check_output(['git', 'show', 'a4f1069e763fb9769aac421331b91de1fed67837:' + record['patch_path']], cwd=root)
subprocess.run(['git', 'apply', '-'], input=base_patch, cwd=copy, check=True)
assert (copy / 'src/index.d.ts').read_bytes() == (installed / 'src/index.d.ts').read_bytes()
print('Earlier public types unchanged byte-for-byte')
for name in record['files']:
    print(''.join(difflib.unified_diff((copy / name).read_text().splitlines(True), (installed / name).read_text().splitlines(True), fromfile='base/' + name, tofile='candidate/' + name)), end='')
