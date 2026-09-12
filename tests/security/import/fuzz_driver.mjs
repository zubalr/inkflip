// Fuzz driver for scripts/fuzz_reports.py (T24).
//
// Protocol: one JSON object per line on stdin, one JSON reply per line on
// stdout.
//   {"seq": n, "mode": "validate",    "payload_b64": "..."}  full import
//     gate for report artifacts (importReport)
//   {"seq": n, "mode": "gate",        "payload_b64": "..."}  same pipeline
//     without the kind==="report" requirement (importArtifact) — used for
//     corpus-manifest/path cases
//   {"seq": n, "mode": "seal",        "report": {...}}  seal() a report and
//     return canonical JSON text — lets the Python fuzzer rebuild valid
//     identity after mutating fields that are covered by the digest
//   {"seq": n, "mode": "normalize",   "text": "..."}  return the
//     scalar-whitespace-v1 normalized view so fuzzed raw_text can be kept
//     contract-consistent
//   {"seq": n, "mode": "hello"}        versions/features
//
// Replies: {"seq": n, "result": "accept"|"reject"|"egress"|"error",
//           "code": "...", "ms": <elapsed>} and for seal/normalize
//           {"seq": n, "result": "sealed"|"normalized", ...}.
//
// Egress tripwires: global fetch/WebSocket/XMLHttpRequest and the
// prototype methods reachable from node:net, node:tls, node:dgram and
// node:child_process are armed before the first case. Any attempted use
// throws an EGRESS-coded error, reported as result "egress". The
// validation module performs no I/O by construction; the tripwires prove
// that property on every fuzz case.
import { createInterface } from 'node:readline';
import * as net from 'node:net';
import * as tls from 'node:tls';
import * as dgram from 'node:dgram';
import * as childProcess from 'node:child_process';
import {
  ContractError,
  normalize,
  seal,
} from '../../../packages/contracts/src/index.ts';
import {
  importArtifact,
  importReport,
} from '../../../packages/reports/validation/index.ts';

const egressAttempts = [];
const egressTripwire = (what) => () => {
  egressAttempts.push(what);
  throw new ContractError('EGRESS', `Egress attempt: ${what}`);
};

// Arm every tripwire reachable from a module namespace or a global.
// (ES module namespace exports are immutable; the prototype methods they
// delegate to are the actual enforcement points.)
globalThis.fetch = egressTripwire('fetch');
globalThis.WebSocket = egressTripwire('WebSocket');
globalThis.XMLHttpRequest = egressTripwire('XMLHttpRequest');
net.Socket.prototype.connect = egressTripwire('net.Socket.connect');
net.Socket.prototype.setNoDelay = net.Socket.prototype.setNoDelay; // touch
tls.TLSSocket.prototype.connect = egressTripwire('tls.TLSSocket.connect');
dgram.Socket.prototype.bind = egressTripwire('dgram.Socket.bind');
dgram.Socket.prototype.send = egressTripwire('dgram.Socket.send');
childProcess.ChildProcess.prototype.spawn = egressTripwire('child_process.spawn');
const TRIPWIRES = [
  'fetch',
  'WebSocket',
  'XMLHttpRequest',
  'net.Socket.connect',
  'tls.TLSSocket.connect',
  'dgram.Socket.bind',
  'dgram.Socket.send',
  'child_process.spawn',
];

const out = (row) => {
  process.stdout.write(JSON.stringify(row) + '\n');
};

const rl = createInterface({ input: process.stdin, terminal: false });
rl.on('line', (line) => {
  let req;
  try {
    req = JSON.parse(line);
  } catch {
    out({ seq: -1, result: 'error', detail: 'bad request line' });
    return;
  }
  const t0 = performance.now();
  const ms = () => Math.round((performance.now() - t0) * 1000) / 1000;
  try {
    if (req.mode === 'hello') {
      out({
        seq: req.seq,
        result: 'hello',
        node: process.version,
        tripwires: TRIPWIRES,
      });
      return;
    }
    if (req.mode === 'stats') {
      out({ seq: req.seq, result: 'stats', egress_attempts: egressAttempts });
      return;
    }
    if (req.mode === 'seal') {
      const sealed = seal(req.report);
      out({ seq: req.seq, result: 'sealed', json: JSON.stringify(sealed) });
      return;
    }
    if (req.mode === 'normalize') {
      const n = normalize(req.text);
      out({ seq: req.seq, result: 'normalized', text: n.text, map: n.map });
      return;
    }
    const bytes = Buffer.from(req.payload_b64, 'base64');
    if (req.mode === 'gate') {
      importArtifact(new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.length));
      out({ seq: req.seq, result: 'accept', ms: ms() });
      return;
    }
    // default: full report import gate
    importReport(new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.length));
    out({ seq: req.seq, result: 'accept', ms: ms() });
  } catch (exc) {
    if (exc instanceof ContractError) {
      out({
        seq: req.seq,
        result: exc.code === 'EGRESS' ? 'egress' : 'reject',
        code: exc.code,
        ms: ms(),
      });
    } else {
      out({
        seq: req.seq,
        result: 'error',
        detail: String(exc && exc.constructor ? exc.constructor.name : exc),
        ms: ms(),
      });
    }
  }
});
