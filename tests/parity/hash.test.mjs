import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { canonical, digest, normalize } from "../../packages/contracts/src/index.ts";
import {
  ARTIFACTS,
  PLANNING_VECTORS,
  ROOT,
  nativePython,
  writeJson,
} from "./harness.mjs";

const hex = (u8) => [...u8].map((b) => b.toString(16).padStart(2, "0")).join("");

test("required hash vectors agree in TypeScript and native Python", () => {
  const vectors = JSON.parse(readFileSync(PLANNING_VECTORS, "utf8"));
  assert.ok(vectors.length >= 11);
  const py = spawnSync(
    nativePython(),
    [
      "-c",
      "import json,sys; sys.path.insert(0,'native'); from inkflip.contracts.core import canonical, digest\n"
      + "vectors=json.load(sys.stdin)\n"
      + "out=[]\n"
      + "for v in vectors:\n"
      + "    out.append({'canonical_hex': canonical(v['value']).hex(), 'sha256': digest(v['value'])})\n"
      + "print(json.dumps(out))",
    ],
    { cwd: ROOT, encoding: "utf8", input: JSON.stringify(vectors) },
  );
  assert.equal(py.status, 0, py.stderr);
  const native = JSON.parse(py.stdout);
  const rows = [];
  for (let i = 0; i < vectors.length; i++) {
    const tsHex = hex(canonical(vectors[i].value));
    const tsSha = digest(vectors[i].value);
    assert.equal(tsHex, vectors[i].canonical_hex);
    assert.equal(tsSha, vectors[i].sha256);
    assert.equal(native[i].canonical_hex, vectors[i].canonical_hex);
    assert.equal(native[i].sha256, vectors[i].sha256);
    rows.push({
      value: vectors[i].value,
      ts: tsSha,
      native: native[i].sha256,
    });
  }
  writeJson(join(ARTIFACTS, "hash-vectors.json"), { agreed: true, rows });
});

test("normalization of required amount strings is identical", () => {
  const samples = ["$100", "$1,000", "  keep   $100  "];
  const py = spawnSync(
    nativePython(),
    [
      "-c",
      "import json,sys; sys.path.insert(0,'native'); from inkflip.contracts.core import normalize\n"
      + "print(json.dumps([{'text': normalize(s)[0], 'input': s} for s in json.load(sys.stdin)]))",
    ],
    { cwd: ROOT, encoding: "utf8", input: JSON.stringify(samples) },
  );
  assert.equal(py.status, 0, py.stderr);
  const native = JSON.parse(py.stdout);
  for (const row of native) {
    assert.equal(normalize(row.input).text, row.text);
  }
});
