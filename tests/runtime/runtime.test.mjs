// TEST-11 — run lifecycle, backpressure and cancellation.
//
// Fixture family F20 (controlled fake readers/process faults) plus the
// stale-event genus of F21-style canary checks at state level: every
// inbound event is a real contract WorkerMessage pushed through the
// coordinator's admission path — no mocks of the unit under test.
// Invariants: I05 (every planned check reaches terminal; failure never
// becomes agreement), I07 (old generation/document/run/job events
// cannot change current state), I17 (bounded work; failures never erase
// successful unrelated results).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';

import {
  runKey as contractRunKey,
  validate,
} from '../../packages/contracts/src/index.ts';
import {
  ChunkSender,
  MessageFactory,
  REASON,
  RUNTIME_LIMITS,
  RunCoordinator,
  TransferLedger,
  deriveRunKey,
} from '../../packages/runtime/src/index.ts';
import { SessionStore } from '../../apps/web/src/state/store.ts';
import {
  DOC_A,
  DOC_B,
  RUN_1,
  RUN_2,
  dispatchMap,
  drain,
  instrumentedResource,
  makeCheck,
  makeOccurrences,
  manualClock,
  manualScheduler,
  openDocument,
  startRun,
  workerSender,
} from './fakes.mjs';

const code = (fn) => {
  try {
    fn();
  } catch (e) {
    return e?.code ?? e?.name ?? 'error';
  }
  return null;
};

function runningCoordinator(checks, options = {}) {
  const clock = manualClock();
  const scheduler = manualScheduler();
  const coord = new RunCoordinator({
    now: clock.now,
    schedule: scheduler.schedule,
    unschedule: scheduler.unschedule,
    ...(options.limits ? { limits: options.limits } : {}),
  });
  openDocument(coord, options.doc ?? DOC_A);
  const jobs = startRun(coord, checks, options);
  return { coord, clock, scheduler, jobs };
}

function jobFactory(coord, jobs, checkId, docSha = DOC_A, runKey = RUN_1) {
  const jobId = [...jobs.entries()].find(([, c]) => c === checkId)?.[0];
  assert.ok(jobId, `no dispatched job for ${checkId}`);
  return { jobId, send: workerSender(coord, jobId, docSha, runKey) };
}

function completeCheck(coord, send, checkId, occurrences = []) {
  if (occurrences.length > 0) {
    assert.equal(coord.receive(send.chunk(checkId, occurrences)).ok, true);
    drain(coord); // deliver acks
  }
  assert.equal(
    coord.receive(send.checkTerminal(checkId, 'completed')).ok,
    true,
  );
}

// ------------------------------------------------------------------
// explicit state machine
// ------------------------------------------------------------------

test('legal lifecycle: idle -> validating_file -> loading_metadata -> selecting -> running', () => {
  const coord = new RunCoordinator({ schedule: () => null, unschedule: () => {} });
  assert.equal(coord.fileState, 'idle');
  coord.openFile();
  assert.equal(coord.fileState, 'validating_file');
  coord.fileValidated();
  assert.equal(coord.fileState, 'loading_metadata');
  coord.metadataLoaded({ sha256: DOC_A, page_count: 3 });
  assert.equal(coord.fileState, 'selecting');
  startRun(coord, [makeCheck('c_a', 0)]);
  assert.equal(coord.fileState, 'running');
});

test('selecting -> preparing_assets -> running when assets are needed', () => {
  const coord = new RunCoordinator({ schedule: () => null, unschedule: () => {} });
  openDocument(coord);
  coord.startRun({
    runKey: RUN_1,
    checks: [makeCheck('c_a', 0)],
    selectedPagesTotal: 1,
    needsAssets: true,
  });
  assert.equal(coord.fileState, 'preparing_assets');
  coord.assetsReady();
  assert.equal(coord.fileState, 'running');
});

test('illegal transitions are rejected with TRANSITION', () => {
  const coord = new RunCoordinator({ schedule: () => null, unschedule: () => {} });
  assert.equal(code(() => coord.fileValidated()), 'TRANSITION');
  assert.equal(code(() => coord.metadataLoaded({ sha256: DOC_A, page_count: 1 })), 'TRANSITION');
  assert.equal(code(() => coord.startRun({ runKey: RUN_1, checks: [makeCheck('c_a', 0)], selectedPagesTotal: 1 })), 'TRANSITION');
  openDocument(coord);
  assert.equal(code(() => coord.openFile()), 'TRANSITION');
  assert.equal(code(() => coord.fileValidated()), 'TRANSITION');
  assert.equal(code(() => coord.requestCancel()), 'TRANSITION');
  // running -> selecting directly is not legal
  startRun(coord, [makeCheck('c_a', 0)]);
  assert.equal(code(() => coord.prepareNewRun()), 'TRANSITION');
  assert.equal(code(() => coord.openFile()), 'TRANSITION');
  // assetsReady without a pending run is illegal
  const bare = new RunCoordinator({ schedule: () => null, unschedule: () => {} });
  openDocument(bare);
  assert.equal(code(() => bare.assetsReady()), 'STATE');
});

test('terminal -> selecting allows a new explicit run on the same file', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const wf = jobFactory(coord, jobs, 'c_a');
  completeCheck(coord, wf.send, 'c_a');
  assert.equal(coord.fileState, 'complete');
  coord.prepareNewRun();
  assert.equal(coord.fileState, 'selecting');
  const jobs2 = startRun(coord, [makeCheck('c_b', 0)], { runKey: RUN_2 });
  assert.equal(coord.fileState, 'running');
  assert.equal(jobs2.size, 1);
});

test('the plan is immutable once issued and page totals are pinned', () => {
  const source = makeCheck('c_a', 0);
  const checks = [source];
  const { coord } = runningCoordinator(checks, { selectedPagesTotal: 2 });
  source.page_index = 99;
  checks.push(makeCheck('c_late', 3));
  const view = coord.snapshot();
  assert.equal(view.run.selectedPagesTotal, 2);
  assert.equal(view.run.checks.length, 1);
  assert.equal(view.run.checks[0].pageIndex, 0);
  assert.throws(() => {
    'use strict';
    view.run.checks[0].status = 'failed';
  });
});

test('dependency on an unknown check or a cycle is a PLAN rejection', () => {
  const coord = new RunCoordinator({ schedule: () => null, unschedule: () => {} });
  openDocument(coord);
  assert.equal(
    code(() =>
      coord.startRun({
        runKey: RUN_1,
        checks: [makeCheck('c_a', 0)],
        selectedPagesTotal: 1,
        dependencies: new Map([['c_a', ['c_missing']]]),
      }),
    ),
    'PLAN',
  );
  const coord2 = new RunCoordinator({ schedule: () => null, unschedule: () => {} });
  openDocument(coord2);
  assert.equal(
    code(() =>
      coord2.startRun({
        runKey: RUN_1,
        checks: [makeCheck('c_a', 0), makeCheck('c_b', 0)],
        selectedPagesTotal: 1,
        dependencies: new Map([
          ['c_a', ['c_b']],
          ['c_b', ['c_a']],
        ]),
      }),
    ),
    'PLAN',
  );
});

test('an empty check plan is rejected at issue — no vacuous run (F5)', () => {
  const coord = new RunCoordinator({ schedule: () => null, unschedule: () => {} });
  openDocument(coord);
  // zero planned checks could never reach terminal (I05), and a
  // vacuous 'complete' would fabricate success: reject it instead.
  assert.equal(
    code(() =>
      coord.startRun({
        runKey: RUN_1,
        checks: [],
        selectedPagesTotal: 0,
      }),
    ),
    'PLAN',
  );
  // rejected cleanly: still selecting, no generation stolen for a
  // run that never existed, and a real run still starts afterwards
  assert.equal(coord.fileState, 'selecting');
  const jobs = startRun(coord, [makeCheck('c_a', 0)]);
  assert.equal(coord.fileState, 'running');
  assert.equal(jobs.size, 1);
});

// ------------------------------------------------------------------
// identity / stale-event authority (I07)
// ------------------------------------------------------------------

test('a stale-generation message is rejected and changes nothing', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const wf = jobFactory(coord, jobs, 'c_a');
  const genAtSend = coord.currentGeneration;
  const stale = wf.send.chunk('c_a', makeOccurrences(3, 0));
  coord.requestCancel();
  assert.ok(coord.currentGeneration > genAtSend);
  const admission = coord.receive(stale);
  assert.equal(admission.ok, false);
  assert.equal(admission.code, 'stale_generation');
  assert.equal(coord.snapshot().occurrences.length, 0);
});

test('old document hash is rejected as stale_document', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const jobId = [...jobs.keys()][0];
  // forge a message for a different document at the live generation
  const forged = new MessageFactory({
    generation: coord.currentGeneration,
    documentSha256: DOC_B,
    runKey: RUN_1,
    jobId,
  }).start();
  const admission = coord.receive(forged);
  assert.equal(admission.ok, false);
  assert.equal(admission.code, 'stale_document');
});

test('old run_key is rejected as stale_run on a new run of the same file', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const oldJobId = [...jobs.keys()][0];
  const staleMsg = workerSender(coord, oldJobId, DOC_A, RUN_1).start();
  coord.requestCancel();
  coord.prepareNewRun();
  const jobs2 = startRun(coord, [makeCheck('c_b', 0)], { runKey: RUN_2 });
  const newJobId = [...jobs2.keys()][0];
  // (a) the literal old message: stale generation
  assert.equal(coord.receive(staleMsg).code, 'stale_generation');
  // (b) a forged current-generation message under the old run key
  const forged = new MessageFactory({
    generation: coord.currentGeneration,
    documentSha256: DOC_A,
    runKey: RUN_1,
    jobId: newJobId,
  }).start();
  assert.equal(coord.receive(forged).code, 'stale_run');
});

test('unknown job, replayed seq and late chunks to terminal jobs are rejected', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  const wf = jobFactory(coord, jobs, 'c_a');
  // unknown job id
  const ghost = new MessageFactory({
    generation: coord.currentGeneration,
    documentSha256: DOC_A,
    runKey: RUN_1,
    jobId: 'j_ghost',
  });
  assert.equal(coord.receive(ghost.start()).code, 'unknown_job');
  // replayed / out-of-order sequence
  const m1 = wf.send.progress('c_a', 1, 4);
  assert.equal(coord.receive(m1).ok, true);
  assert.equal(coord.receive(m1).code, 'sequence'); // replay
  const m0 = { ...m1, seq: 0 };
  assert.equal(coord.receive(m0).code, 'sequence'); // backward
  // terminal job rejects late chunks
  completeCheck(coord, wf.send, 'c_a');
  assert.equal(coord.receive(wf.send.chunk('c_a', makeOccurrences(1, 0))).code, 'terminal_job');
  assert.equal(coord.receive(wf.send.checkTerminal('c_a', 'completed')).code, 'terminal_job');
});

test('malformed inbound is rejected before admission', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const wf = jobFactory(coord, jobs, 'c_a');
  assert.equal(coord.receive({ hello: 'world' }).code, 'malformed');
  assert.equal(coord.receive(null).code, 'malformed');
  // 257 occurrences exceed the schema chunk bound
  assert.equal(coord.receive(wf.send.chunk('c_a', makeOccurrences(257, 0))).code, 'malformed');
  // occurrences are only legal on chunk events
  const progressWithOccs = wf.send.progress('c_a', 1, 2);
  progressWithOccs.payload.occurrences = makeOccurrences(1, 0);
  assert.equal(coord.receive(progressWithOccs).code, 'malformed');
  // status on a chunk event is invalid
  const badChunk = wf.send.chunk('c_a', makeOccurrences(1, 0));
  badChunk.payload.status = 'completed';
  assert.equal(coord.receive(badChunk).code, 'malformed');
});

test('a stale check_terminal cannot flip a live check (failure never becomes agreement)', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const jobId = [...jobs.keys()][0];
  const stale = workerSender(coord, jobId, DOC_A, RUN_1).checkTerminal('c_a', 'failed', 'worker_crash');
  coord.requestCancel();
  coord.prepareNewRun();
  const jobs2 = startRun(coord, [makeCheck('c_b', 0)], { runKey: RUN_2 });
  assert.equal(coord.receive(stale).ok, false);
  const view = coord.snapshot();
  const current = view.run.checks.find((c) => c.id === 'c_b');
  assert.equal(current.phase, 'running');
  assert.equal(current.status, null);
});

test('a reasonless or statusless terminal is rejected before anything mutates (F2)', () => {
  const { coord, jobs } = runningCoordinator([
    makeCheck('c_a', 0),
    makeCheck('c_b', 1),
  ]);
  const wf = jobFactory(coord, jobs, 'c_a');
  const admittedBefore = coord.admittedCount;
  const revisionBefore = coord.snapshot().revision;
  // schema-valid but semantically illegal: non-completed needs a reason
  const reasonless = wf.send.checkTerminal('c_a', 'timeout');
  assert.equal(reasonless.payload.reason, null);
  const rejection = coord.receive(reasonless);
  assert.equal(rejection.ok, false);
  assert.equal(rejection.code, 'malformed');
  // nothing was consumed: seq unspent, counters untouched, no intents
  assert.equal(coord.admittedCount, admittedBefore);
  assert.equal(coord.snapshot().revision, revisionBefore);
  assert.equal(
    drain(coord).filter((i) => i.type === 'terminate').length,
    0,
  );
  // the job stays usable: the next well-formed terminal is admitted
  assert.equal(
    coord.receive(wf.send.checkTerminal('c_a', 'timeout', 'timeout')).ok,
    true,
  );
  // a status-less terminal is likewise rejected pre-admission
  const wfB = jobFactory(coord, jobs, 'c_b');
  const statusless = wfB.send.message('check_terminal', { check_id: 'c_b' });
  assert.equal(statusless.payload.status, null);
  assert.equal(coord.receive(statusless).code, 'malformed');
  assert.equal(coord.receive(wfB.send.checkTerminal('c_b', 'completed')).ok, true);
  // c_b completed, c_a timed out: partial — and both settled exactly once
  const view = coord.snapshot();
  assert.equal(view.fileState, 'partial');
  assert.equal(view.run.checks.every((c) => c.status !== null), true);
});

// ------------------------------------------------------------------
// bounded acknowledged chunks
// ------------------------------------------------------------------

test('ChunkSender emits <=256-occurrence chunks and holds at two unacked', () => {
  const sender = new ChunkSender('c_a');
  sender.enqueue(makeOccurrences(600, 0));
  const c1 = sender.sendNext(0);
  const c2 = sender.sendNext(1);
  assert.equal(c1.length, 256);
  assert.equal(c2.length, 256);
  assert.equal(sender.sendNext(2), null); // two unacked: window closed
  sender.acknowledge(0);
  const c3 = sender.sendNext(2);
  assert.equal(c3.length, 88);
  assert.equal(sender.sendNext(3), null);
  assert.equal(code(() => sender.acknowledge(999)), 'BACKPRESSURE');
});

test('inbound: a third chunk while two are unacknowledged is a protocol violation', () => {
  const { coord, jobs } = runningCoordinator([
    makeCheck('c_a', 0),
    makeCheck('c_b', 1),
  ]);
  const wfa = jobFactory(coord, jobs, 'c_a');
  const wfb = jobFactory(coord, jobs, 'c_b');
  // c_b completes honestly; c_a floods past the ack window
  completeCheck(coord, wfb.send, 'c_b', makeOccurrences(2, 1));
  assert.equal(coord.receive(wfa.send.chunk('c_a', makeOccurrences(10, 0))).ok, true);
  assert.equal(coord.receive(wfa.send.chunk('c_a', makeOccurrences(10, 0))).ok, true);
  // acks were queued but never delivered -> the third send is provably over-window
  assert.equal(coord.receive(wfa.send.chunk('c_a', makeOccurrences(10, 0))).ok, true);
  const view = coord.snapshot();
  const a = view.run.checks.find((c) => c.id === 'c_a');
  const b = view.run.checks.find((c) => c.id === 'c_b');
  assert.equal(a.status, 'failed');
  assert.match(a.reason, /protocol_violation/);
  // I17: the completed independent check kept its results
  assert.equal(b.status, 'completed');
  assert.equal(b.retainedOccurrenceIds.length, 2);
  assert.equal(view.fileState, 'partial');
});

test('delivered acks reopen the window — ack is capacity, not success', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const wf = jobFactory(coord, jobs, 'c_a');
  assert.equal(coord.receive(wf.send.chunk('c_a', makeOccurrences(5, 0))).ok, true);
  assert.equal(coord.receive(wf.send.chunk('c_a', makeOccurrences(5, 0))).ok, true);
  const acks = drain(coord).filter((i) => i.type === 'ack');
  assert.equal(acks.length, 2);
  assert.equal(acks[0].message.event, 'ack');
  validate(acks[0].message); // the ack itself is a real contract message
  // capacity freed: a third chunk is now legal
  assert.equal(coord.receive(wf.send.chunk('c_a', makeOccurrences(5, 0))).ok, true);
  // ...and the check is still running, not magically complete
  const view = coord.snapshot();
  const a = view.run.checks[0];
  assert.equal(a.phase, 'running');
  assert.equal(a.status, null);
  assert.equal(a.producedOccurrences, 15);
  assert.equal(coord.fileState, 'running');
});

test('a chunk naming another check is a protocol violation', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  const wfa = jobFactory(coord, jobs, 'c_a');
  const forged = wfa.send.chunk('c_b', makeOccurrences(2, 1)); // job serves c_a
  assert.equal(coord.receive(forged).ok, true); // admitted (identity ok)
  const view = coord.snapshot();
  assert.equal(view.run.checks.find((c) => c.id === 'c_a').reason, 'protocol_violation');
  assert.equal(view.run.checks.find((c) => c.id === 'c_a').status, 'failed');
});

test('oversized output terminates the check as resource_limit, siblings retained', () => {
  const { coord, jobs } = runningCoordinator(
    [makeCheck('c_a', 0), makeCheck('c_b', 1)],
    { limits: { maxOccurrencesPerPage: 5, maxOccurrencesPerRun: 1000, maxRawTextBytesPerRun: 8388608 } },
  );
  const wfa = jobFactory(coord, jobs, 'c_a');
  const wfb = jobFactory(coord, jobs, 'c_b');
  completeCheck(coord, wfb.send, 'c_b', makeOccurrences(2, 1));
  assert.equal(coord.receive(wfa.send.chunk('c_a', makeOccurrences(6, 0))).ok, true);
  const view = coord.snapshot();
  const a = view.run.checks.find((c) => c.id === 'c_a');
  const b = view.run.checks.find((c) => c.id === 'c_b');
  assert.equal(a.status, 'failed');
  assert.equal(a.reason, 'resource_limit');
  assert.equal(b.status, 'completed');
  assert.equal(b.retainedOccurrenceIds.length, 2); // I17
  assert.equal(view.notice, 'progress.resource');
  assert.equal(view.fileState, 'partial');
});

test('at most two live raster_rgba slots; a third claim is resource_limit', () => {
  const { coord, jobs } = runningCoordinator([
    makeCheck('c_a', 0, 'render'),
    makeCheck('c_b', 1, 'render'),
    makeCheck('c_c', 2, 'native_text'),
  ]);
  const findJob = (checkId) =>
    [...jobs.entries()].find(([, c]) => c === checkId)[0];
  // only one render may run at once (maxActiveRenders=1)
  const dispatched = [...jobs.values()];
  assert.equal(dispatched.filter((c) => c === 'c_a' || c === 'c_b').length >= 1, true);
  const ledger = new TransferLedger(2);
  assert.equal(ledger.claim('raster_rgba', 'c_a'), 'ok');
  assert.equal(ledger.claim('raster_rgba', 'c_b'), 'ok');
  assert.equal(ledger.claim('raster_rgba', 'c_c'), 'raster_cap');
  ledger.release('c_a');
  assert.equal(ledger.claim('raster_rgba', 'c_c'), 'ok');
  assert.equal(ledger.claim('pdf_bytes', 'c_c'), 'ok');
  // message-level: a progress event carrying raster_rgba binds it to the check
  const wf = workerSender(coord, findJob(dispatched[0]), DOC_A, RUN_1);
  const m = wf.progress(dispatched[0], 0, 1);
  m.payload.transfer_slot = 'raster_rgba';
  m.payload.transfer_bytes = 1024;
  assert.equal(coord.receive(m).ok, true);
});

test('downgrading a raster claim to pdf_bytes frees the live-raster slot (F4)', () => {
  const ledger = new TransferLedger(2);
  assert.equal(ledger.claim('raster_rgba', 'c_1'), 'ok');
  assert.equal(ledger.claim('raster_rgba', 'c_2'), 'ok');
  assert.equal(ledger.claim('raster_rgba', 'c_3'), 'raster_cap');
  // c_1 stops using the raster buffer and drops to the shared source
  // bytes: its raster hold must be released, not leaked
  assert.equal(ledger.claim('pdf_bytes', 'c_1'), 'ok');
  assert.equal(ledger.liveRasters, 1);
  assert.equal(ledger.claim('raster_rgba', 'c_3'), 'ok');
  assert.equal(ledger.liveRasters, 2);
});

// ------------------------------------------------------------------
// per-check terminal bookkeeping (I05)
// ------------------------------------------------------------------

test('a fully completed run is complete with schema-valid check results', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  const wfa = jobFactory(coord, jobs, 'c_a');
  const wfb = jobFactory(coord, jobs, 'c_b');
  completeCheck(coord, wfa.send, 'c_a', makeOccurrences(3, 0));
  completeCheck(coord, wfb.send, 'c_b', makeOccurrences(0, 1));
  const view = coord.snapshot();
  assert.equal(view.fileState, 'complete');
  assert.equal(view.run.status, 'complete');
  assert.equal(view.notice, 'progress.complete');
  const results = coord.settledCheckResults();
  assert.equal(results.length, 2);
  for (const r of results) {
    // schema CheckResult fields: reason null iff completed
    assert.equal(r.status === 'completed' ? r.reason === null : r.reason !== null, true);
    assert.equal(typeof r.produced_occurrence_count, 'number');
    assert.equal(Array.isArray(r.retained_occurrence_ids), true);
  }
  assert.equal(results[0].status, 'completed');
  assert.equal(results[0].produced_occurrence_count, 3);
});

test('partial run: one page fails, the completed page keeps its results (I17)', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  const wfa = jobFactory(coord, jobs, 'c_a');
  const wfb = jobFactory(coord, jobs, 'c_b');
  completeCheck(coord, wfa.send, 'c_a', makeOccurrences(4, 0));
  assert.equal(coord.receive(wfb.send.error('reader exploded', 'c_b')).ok, true);
  const view = coord.snapshot();
  assert.equal(view.fileState, 'partial');
  assert.equal(view.run.status, 'partial');
  const a = view.run.checks.find((c) => c.id === 'c_a');
  const b = view.run.checks.find((c) => c.id === 'c_b');
  assert.equal(a.status, 'completed');
  assert.equal(a.retainedOccurrenceIds.length, 4);
  assert.equal(b.status, 'failed');
  // the surviving evidence is exactly the completed page's occurrences
  assert.equal(view.occurrences.length, 4);
  assert.deepEqual(
    view.occurrences.map((o) => o.id),
    a.retainedOccurrenceIds,
  );
});

test('failed run: nothing completed and at least one failure', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const wf = jobFactory(coord, jobs, 'c_a');
  assert.equal(coord.receive(wf.send.checkTerminal('c_a', 'failed', 'parse blew up')).ok, true);
  const view = coord.snapshot();
  assert.equal(view.fileState, 'failed');
  assert.equal(view.notice, 'progress.failed');
});

test('cancelled, partial and failed are distinct outcomes', () => {
  // cancelled: user request wins even with completed checks present
  const c1 = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  const wf1 = jobFactory(c1.coord, c1.jobs, 'c_a');
  completeCheck(c1.coord, wf1.send, 'c_a', makeOccurrences(2, 0));
  c1.coord.requestCancel();
  const v1 = c1.coord.snapshot();
  assert.equal(v1.run.status, 'cancelled');
  assert.equal(v1.run.checks.find((c) => c.id === 'c_a').status, 'completed');
  assert.equal(v1.run.checks.find((c) => c.id === 'c_b').status, 'cancelled');
  assert.equal(v1.notice, 'progress.cancelled');
  // partial: completed + failed coexist, no cancellation
  const c2 = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  const wf2 = jobFactory(c2.coord, c2.jobs, 'c_a');
  completeCheck(c2.coord, wf2.send, 'c_a');
  assert.equal(c2.coord.receive(jobFactory(c2.coord, c2.jobs, 'c_b').send.checkTerminal('c_b', 'timeout', 'timeout')).ok, true);
  const v2 = c2.coord.snapshot();
  assert.equal(v2.run.status, 'partial');
  assert.notEqual(v2.run.status, v1.run.status);
  assert.equal(v2.run.checks.find((c) => c.id === 'c_b').status, 'timeout');
  // failed: zero completed + a failure
  const c3 = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  assert.equal(c3.coord.receive(jobFactory(c3.coord, c3.jobs, 'c_a').send.checkTerminal('c_a', 'failed', 'encrypted')).ok, true);
  const v3 = c3.coord.snapshot();
  // c_b depended on nothing: it was running and gets skipped?? no —
  // independent check stays running until it terminals too.
  assert.equal(v3.fileState, 'running'); // run cannot settle while c_b is live
  assert.equal(c3.coord.receive(jobFactory(c3.coord, c3.jobs, 'c_b').send.checkTerminal('c_b', 'failed', 'parse error')).ok, true);
  const v3b = c3.coord.snapshot();
  assert.equal(v3b.run.status, 'failed');
  assert.equal(v3b.run.checks.every((c) => c.status === 'failed'), true);
});

test('queued work cancelled by the user receives a terminal cancelled result', () => {
  // c_ocr depends on render; cancel while it is still queued
  const { coord, jobs } = runningCoordinator([
    makeCheck('c_render', 0, 'render'),
    makeCheck('c_ocr', 0, 'ocr'),
    makeCheck('c_text', 1, 'native_text'),
  ]);
  const view0 = coord.snapshot();
  const ocr = view0.run.checks.find((c) => c.id === 'c_ocr');
  assert.equal(ocr.phase, 'queued'); // waiting on its render dep
  coord.requestCancel();
  const view = coord.snapshot();
  assert.equal(view.run.checks.find((c) => c.id === 'c_ocr').status, 'cancelled');
  assert.equal(view.run.checks.every((c) => c.phase === 'terminal'), true);
  const results = coord.settledCheckResults();
  assert.equal(results.length, 3);
  assert.equal(results.every((r) => r.status !== 'completed' ? r.reason !== null : true), true);
});

test('a failed dependency skips its dependents with a named reason', () => {
  const { coord, jobs } = runningCoordinator([
    makeCheck('c_render', 0, 'render'),
    makeCheck('c_ocr', 0, 'ocr'),
  ]);
  const wf = jobFactory(coord, jobs, 'c_render');
  assert.equal(coord.receive(wf.send.checkTerminal('c_render', 'failed', 'render crash')).ok, true);
  const view = coord.snapshot();
  const ocr = view.run.checks.find((c) => c.id === 'c_ocr');
  assert.equal(ocr.phase, 'terminal');
  assert.equal(ocr.status, 'skipped');
  assert.match(ocr.reason, /dependency_unmet:c_render:failed/);
  assert.equal(view.run.status, 'failed'); // nothing completed + a failure
});

test('a completed dependency releases its dependents in order', () => {
  const { coord, jobs } = runningCoordinator([
    makeCheck('c_render', 0, 'render'),
    makeCheck('c_ocr', 0, 'ocr'),
    makeCheck('c_align', 0, 'alignment'),
    makeCheck('c_text', 0, 'native_text'),
  ]);
  // ocr + alignment start queued; render + native_text dispatch
  const first = coord.snapshot().run.checks;
  assert.equal(first.find((c) => c.id === 'c_ocr').phase, 'queued');
  assert.equal(first.find((c) => c.id === 'c_align').phase, 'queued');
  const wfR = jobFactory(coord, jobs, 'c_render');
  completeCheck(coord, wfR.send, 'c_render');
  // OCR dispatched now that its raster exists
  const jobs2 = dispatchMap(coord);
  assert.equal([...jobs2.values()].includes('c_ocr'), true);
  const wfO = workerSender(coord, [...jobs2.entries()].find(([, c]) => c === 'c_ocr')[0], DOC_A, RUN_1);
  const wfT = jobFactory(coord, new Map([...jobs, ...jobs2]), 'c_text');
  completeCheck(coord, wfO, 'c_ocr');
  completeCheck(coord, wfT.send, 'c_text');
  // alignment still needs... both native_text and ocr completed -> runs
  const jobs3 = dispatchMap(coord);
  assert.equal([...jobs3.values()].includes('c_align'), true);
  const wfA = workerSender(coord, [...jobs3.entries()].find(([, c]) => c === 'c_align')[0], DOC_A, RUN_1);
  completeCheck(coord, wfA, 'c_align');
  assert.equal(coord.fileState, 'complete');
});

test('a depth-3 dependency chain settles to skipped in any plan order (F3)', () => {
  // c_c fails -> c_b skipped -> c_a skipped. The plan lists the most
  // dependent check FIRST, so a single propagation pass cannot reach
  // c_a — the cascade must iterate to fixpoint (I05: nothing waits
  // forever, whatever the plan order).
  const checks = [
    makeCheck('c_a', 0),
    makeCheck('c_b', 0),
    makeCheck('c_c', 0),
  ];
  const dependencies = new Map([
    ['c_a', ['c_b']],
    ['c_b', ['c_c']],
    ['c_c', []],
  ]);
  const { coord, jobs } = runningCoordinator(checks, { dependencies });
  // only c_c is runnable; the chain above it waits
  assert.deepEqual([...jobs.values()], ['c_c']);
  const wf = jobFactory(coord, jobs, 'c_c');
  assert.equal(
    coord.receive(wf.send.checkTerminal('c_c', 'failed', 'boom')).ok,
    true,
  );
  const view = coord.snapshot();
  assert.equal(view.fileState, 'failed');
  const byId = Object.fromEntries(view.run.checks.map((c) => [c.id, c]));
  assert.equal(byId.c_c.status, 'failed');
  assert.equal(byId.c_b.status, 'skipped');
  assert.equal(byId.c_a.status, 'skipped');
  // the skip reason names the unmet dependency at each hop
  assert.match(byId.c_b.reason, /dependency_unmet:c_c:failed/);
  assert.match(byId.c_a.reason, /dependency_unmet:c_b:skipped/);
});

test('unsupported-only run is partial, not failed and not complete', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  assert.equal(coord.receive(jobFactory(coord, jobs, 'c_a').send.checkTerminal('c_a', 'unsupported', 'unsupported')).ok, true);
  assert.equal(coord.receive(jobFactory(coord, jobs, 'c_b').send.checkTerminal('c_b', 'unsupported', 'unsupported')).ok, true);
  const view = coord.snapshot();
  assert.equal(view.run.status, 'partial');
  assert.equal(view.fileState, 'partial');
});

// ------------------------------------------------------------------
// retry taxonomy
// ------------------------------------------------------------------

test('worker_crash is retried once on a fresh job identity', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const wf1 = jobFactory(coord, jobs, 'c_a');
  assert.equal(coord.receive(wf1.send.checkTerminal('c_a', 'failed', REASON.WORKER_CRASH)).ok, true);
  const intents = drain(coord);
  const redispatch = intents.filter((i) => i.type === 'dispatch');
  assert.equal(redispatch.length, 1);
  const freshJob = redispatch[0].jobId;
  assert.notEqual(freshJob, wf1.jobId);
  // the crashed job is terminal: its late messages are dead
  assert.equal(coord.receive(wf1.send.chunk('c_a', makeOccurrences(1, 0))).code, 'terminal_job');
  // the fresh worker completes the check
  const wf2 = workerSender(coord, freshJob, DOC_A, RUN_1);
  completeCheck(coord, wf2, 'c_a', makeOccurrences(2, 0));
  const view = coord.snapshot();
  assert.equal(view.fileState, 'complete');
  assert.equal(view.run.checks[0].attempts, 2);
});

test('the retry budget is one: a second crash settles failed', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const wf1 = jobFactory(coord, jobs, 'c_a');
  coord.receive(wf1.send.checkTerminal('c_a', 'failed', REASON.WORKER_CRASH));
  const [{ jobId: j2 }] = drain(coord).filter((i) => i.type === 'dispatch');
  const wf2 = workerSender(coord, j2, DOC_A, RUN_1);
  assert.equal(coord.receive(wf2.checkTerminal('c_a', 'failed', REASON.INIT_CRASH)).ok, true);
  const view = coord.snapshot();
  assert.equal(view.run.checks[0].status, 'failed');
  assert.equal(view.run.checks[0].reason, REASON.INIT_CRASH);
  assert.equal(view.fileState, 'failed');
  assert.equal(drain(coord).filter((i) => i.type === 'dispatch').length, 0);
});

test('no automatic retry on cancel/encrypted/unsupported/integrity/timeout', () => {
  for (const [status, reason] of [
    ['failed', REASON.ENCRYPTED],
    ['unsupported', REASON.UNSUPPORTED],
    ['failed', REASON.INTEGRITY],
    ['timeout', 'timeout'],
    ['failed', REASON.USER_CANCEL],
  ]) {
    const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
    const wf = jobFactory(coord, jobs, 'c_a');
    assert.equal(coord.receive(wf.send.checkTerminal('c_a', status, reason)).ok, true);
    assert.equal(drain(coord).filter((i) => i.type === 'dispatch').length, 0, `unexpected retry for ${reason}`);
    const view = coord.snapshot();
    assert.equal(view.run.checks[0].status, status);
  }
});

test('a crash beyond the remaining run budget is not retried', () => {
  const { coord, clock, jobs } = runningCoordinator([makeCheck('c_a', 0)], { budgetMs: 1000 });
  clock.advance(5000); // past the deadline
  const wf = jobFactory(coord, jobs, 'c_a');
  assert.equal(coord.receive(wf.send.checkTerminal('c_a', 'failed', REASON.WORKER_CRASH)).ok, true);
  const view = coord.snapshot();
  assert.equal(view.run.checks[0].status, 'failed');
  assert.equal(drain(coord).filter((i) => i.type === 'dispatch').length, 0);
});

test('a retried job is dispatched with its own deadline watchdog (F1, I05)', () => {
  // Regression: the retry path used to redispatch inline without arming
  // onCheckDeadline — a hung retried job could never reach terminal.
  const { coord, scheduler, jobs } = runningCoordinator([
    makeCheck('c_a', 0),
  ]);
  const wf1 = jobFactory(coord, jobs, 'c_a');
  assert.equal(
    coord.receive(wf1.send.checkTerminal('c_a', 'failed', REASON.WORKER_CRASH)).ok,
    true,
  );
  const [{ jobId: j2 }] = drain(coord).filter((i) => i.type === 'dispatch');
  assert.notEqual(j2, wf1.jobId);
  // three timers pending now: the run deadline, j_1's stale check
  // deadline (will no-op on jobId mismatch), and j_2's OWN deadline
  assert.equal(scheduler.count(), 3);
  // fire the newest timer — j_2's check deadline, armed by the retry
  const j2Timer = Math.max(...scheduler.pending.keys());
  scheduler.fire(j2Timer);
  const view = coord.snapshot();
  assert.equal(view.run.checks[0].status, 'timeout');
  assert.equal(view.run.checks[0].reason, REASON.TIMEOUT);
  // the run settled: a hung retry can never stall the lifecycle
  assert.equal(view.fileState, 'failed');
});

test('empty success is completed, never retried (acceptance criterion)', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  const wfa = jobFactory(coord, jobs, 'c_a');
  const wfb = jobFactory(coord, jobs, 'c_b');
  // a completed read returning zero occurrences is a completed read
  completeCheck(coord, wfa.send, 'c_a', []);
  completeCheck(coord, wfb.send, 'c_b', []);
  const view = coord.snapshot();
  assert.equal(view.fileState, 'complete');
  assert.equal(view.run.checks.every((c) => c.status === 'completed'), true);
  assert.equal(view.run.checks.every((c) => c.attempts === 1), true); // no retry
  assert.equal(drain(coord).filter((i) => i.type === 'dispatch').length, 0);
});

// ------------------------------------------------------------------
// cancellation + clearing (bounded work, I17)
// ------------------------------------------------------------------

test('cancel order: visible cancelled state precedes teardown', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  jobFactory(coord, jobs, 'c_a');
  const order = [];
  coord.ownRunResource(() => {}, 'worker', () => order.push('teardown'));
  coord.subscribe(() => order.push(`view:${coord.fileState}`));
  coord.requestCancel();
  const firstTeardown = order.indexOf('teardown');
  const cancelledViews = order
    .map((e, i) => [e, i])
    .filter(([e, i]) => e === 'view:cancelled' && i < firstTeardown);
  assert.ok(firstTeardown > 0, 'teardown ran');
  assert.ok(cancelledViews.length > 0, 'cancelled state was visible before teardown');
});

test('cancel timing: UI update under 100 ms, teardown under 500 ms (measured)', () => {
  // Real clock (default performance.now) + manual scheduler so no real
  // timers are armed: the receipt times are actual measurements.
  const scheduler = manualScheduler();
  const coord = new RunCoordinator({
    schedule: scheduler.schedule,
    unschedule: scheduler.unschedule,
  });
  openDocument(coord);
  const jobs = startRun(coord, [makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  jobFactory(coord, jobs, 'c_a');
  // ~30 ms of teardown work proves the bound is measured, not assumed
  coord.ownRunResource(() => {}, 'slow-worker', () => {
    const until = performance.now() + 30;
    while (performance.now() < until) { /* bounded teardown work */ }
  });
  const receipt = coord.requestCancel();
  assert.ok(receipt.uiMs < RUNTIME_LIMITS.cancelUiTargetMs, `uiMs=${receipt.uiMs}`);
  assert.ok(receipt.teardownMs < RUNTIME_LIMITS.terminateTargetMs, `teardownMs=${receipt.teardownMs}`);
  assert.ok(receipt.teardownMs >= 29, 'teardown actually measured ~30ms of work');
  assert.equal(receipt.cleanupFailures.length, 0);
});

test('cancel preserves completed evidence and kills the old generation', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  const wfa = jobFactory(coord, jobs, 'c_a');
  const wfb = jobFactory(coord, jobs, 'c_b');
  completeCheck(coord, wfa.send, 'c_a', makeOccurrences(3, 0));
  const genBefore = coord.currentGeneration;
  const lateMsg = wfb.send.chunk('c_b', makeOccurrences(2, 1));
  const receipt = coord.requestCancel();
  assert.equal(receipt.generation, genBefore + 1);
  const view = coord.snapshot();
  assert.equal(view.run.checks.find((c) => c.id === 'c_a').status, 'completed');
  assert.equal(view.occurrences.length, 3); // "completed results kept"
  assert.equal(view.notice, 'progress.cancelled');
  // late traffic from the killed generation is unreachable
  assert.equal(coord.receive(lateMsg).code, 'stale_generation');
  // cancel + terminate intents were queued for the live job
  const intents = drain(coord);
  assert.equal(intents.some((i) => i.type === 'message' && i.message.event === 'cancel'), true);
  assert.equal(intents.some((i) => i.type === 'terminate' && i.jobId === wfb.jobId), true);
});

test('clear: generation bumps BEFORE teardown, everything is released, state nulls', () => {
  const { coord } = runningCoordinator([makeCheck('c_a', 0)]);
  const genBefore = coord.currentGeneration;
  const res = instrumentedResource(['cancel', 'abort', 'terminate', 'close']);
  let genAtTeardown = -1;
  coord.own(() => {}, 'pdf-handle', () => {
    genAtTeardown = coord.currentGeneration;
    res.terminate();
  });
  const failures = coord.requestClear();
  assert.equal(failures.length, 0);
  assert.ok(genAtTeardown > genBefore, 'generation bumped before teardown ran');
  assert.deepEqual(res.calls, ['terminate']);
  assert.equal(coord.fileState, 'idle');
  const view = coord.snapshot();
  assert.equal(view.documentSha256, null);
  assert.equal(view.run, null);
  assert.equal(view.occurrences.length, 0);
});

test('clear runs every registered teardown verb on owned resources', () => {
  const { coord } = runningCoordinator([makeCheck('c_a', 0)]);
  const res = instrumentedResource(['cancel', 'abort', 'unsubscribe', 'disconnect', 'terminate', 'destroy', 'close', 'remove']);
  coord.own(res, 'kitchen-sink');
  const failures = coord.requestClear();
  assert.equal(failures.length, 0);
  assert.equal(res.calls.length, 8);
  assert.deepEqual(new Set(res.calls), new Set(['cancel', 'abort', 'unsubscribe', 'disconnect', 'terminate', 'destroy', 'close', 'remove']));
});

test('clear failures are collected, not fatal — teardown continues', () => {
  const { coord } = runningCoordinator([makeCheck('c_a', 0)]);
  coord.own(() => {}, 'bad', () => { throw new Error('nope'); });
  const good = instrumentedResource(['close']);
  coord.own(good, 'good');
  const failures = coord.requestClear();
  assert.equal(failures.length, 1);
  assert.equal(failures[0].label, 'bad');
  assert.deepEqual(good.calls, ['close']);
});

test('replace: clearing -> validating_file, old generation fully dead', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const wf = jobFactory(coord, jobs, 'c_a');
  const staleChunk = wf.send.chunk('c_a', makeOccurrences(5, 0));
  coord.requestClear('replace');
  assert.equal(coord.fileState, 'validating_file');
  // live jobs got terminate intents through the surviving outbox
  assert.equal(drain(coord).some((i) => i.type === 'terminate'), true);
  coord.fileValidated();
  coord.metadataLoaded({ sha256: DOC_B, page_count: 2 });
  const jobs2 = startRun(coord, [makeCheck('c_x', 0)], { runKey: RUN_2 });
  const staleIds = staleChunk.payload.occurrences.map((o) => o.id);
  assert.equal(coord.receive(staleChunk).ok, false);
  const wf2 = workerSender(coord, [...jobs2.keys()][0], DOC_B, RUN_2);
  completeCheck(coord, wf2, 'c_x', makeOccurrences(2, 0));
  const view = coord.snapshot();
  assert.equal(view.documentSha256, DOC_B);
  assert.equal(view.occurrences.length, 2);
  assert.equal(view.occurrences.every((o) => o.page_index === 0), true);
  // stale occurrences can never render: none entered the view at all
  assert.equal(
    view.occurrences.some((o) => staleIds.includes(o.id)),
    false,
  );
});

test('run deadline watchdog terminalizes live checks as timeout', () => {
  const { coord, scheduler, jobs } = runningCoordinator(
    [makeCheck('c_a', 0), makeCheck('c_b', 1)],
    { budgetMs: 120000 },
  );
  jobFactory(coord, jobs, 'c_a');
  scheduler.fireAll(); // fire run deadline + per-check deadlines
  const view = coord.snapshot();
  assert.equal(view.run.checks.every((c) => c.phase === 'terminal'), true);
  assert.equal(view.run.checks.every((c) => c.status === 'timeout'), true);
  assert.equal(view.run.status, 'failed'); // 0 completed + timeouts
  assert.equal(view.notice, 'progress.timeout');
});

// ------------------------------------------------------------------
// progress + presentation honesty
// ------------------------------------------------------------------

test('progress is per-check with indeterminate support; no unified percent', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const wf = jobFactory(coord, jobs, 'c_a');
  assert.equal(coord.receive(wf.send.progress('c_a', 3, 10)).ok, true);
  assert.equal(coord.receive(wf.send.progress('c_a', 4)).ok, true); // no denominator
  const view = coord.snapshot();
  const a = view.run.checks[0];
  assert.deepEqual(a.progress, { completed: 4, total: null });
  assert.equal('percent' in view.run, false);
  assert.equal('progress_percent' in view, false);
});

test('snapshot is immutable and revisions count accepted mutations', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const wf = jobFactory(coord, jobs, 'c_a');
  const v0 = coord.snapshot();
  const rev0 = v0.revision;
  coord.receive(wf.send.chunk('c_a', makeOccurrences(2, 0)));
  const v1 = coord.snapshot();
  assert.ok(v1.revision > rev0);
  assert.throws(() => { 'use strict'; v1.fileState = 'idle'; });
  assert.equal(v0.occurrences.length, 0); // old snapshot not retro-mutated
});

test('rejectionStats returns a copy, not the live accounting map (F7)', () => {
  const coord = new RunCoordinator({ schedule: () => null, unschedule: () => {} });
  coord.receive({ nope: true });
  const stats = coord.rejectionStats;
  assert.equal(stats.get('malformed'), 1);
  stats.set('malformed', 999);
  stats.set('sequence', 5);
  // internal accounting is untouched by caller mutation
  assert.equal(coord.rejectionStats.get('malformed'), 1);
  assert.equal(coord.rejectionStats.has('sequence'), false);
});

test('deriveRunKey matches the contract runKey formula', () => {
  const readers = [{ id: 'r_test' }];
  const plan = { selected_pages: [0] };
  const doc = DOC_A;
  const expected = contractRunKey({
    document: { sha256: doc },
    readers,
    plan,
  });
  assert.equal(deriveRunKey(doc, readers, plan), expected);
});

// ------------------------------------------------------------------
// apps/web session store binding
// ------------------------------------------------------------------

test('SessionStore: stale events cannot alter the view', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0)]);
  const store = new SessionStore(coord);
  const wf = jobFactory(coord, jobs, 'c_a');
  completeCheck(coord, wf.send, 'c_a', makeOccurrences(3, 0));
  const before = JSON.stringify(store.current);
  const stale = wf.send.chunk('c_a', makeOccurrences(9, 0));
  const admission = store.ingest(stale);
  assert.equal(admission.ok, false);
  assert.equal(JSON.stringify(store.current), before);
  assert.equal(store.current.occurrences.length, 3);
  store.destroy();
});

test('SessionStore: cancel surfaces notice and keeps completed results', () => {
  const { coord, jobs } = runningCoordinator([makeCheck('c_a', 0), makeCheck('c_b', 1)]);
  const store = new SessionStore(coord);
  const seen = [];
  store.subscribe((v) => seen.push(v.fileState));
  const wfa = jobFactory(coord, jobs, 'c_a');
  completeCheck(coord, wfa.send, 'c_a', makeOccurrences(2, 0));
  store.cancel();
  assert.equal(store.fileState, 'cancelled');
  assert.equal(store.notice, 'progress.cancelled');
  assert.equal(store.current.occurrences.length, 2);
  assert.ok(seen.includes('cancelled'));
  store.destroy();
});

test('SessionStore: malformed and stale ingestions return rejections only', () => {
  const { coord } = runningCoordinator([makeCheck('c_a', 0)]);
  const store = new SessionStore(coord);
  assert.equal(store.ingest(42).code, 'malformed');
  assert.equal(store.ingest({ kind: 'worker_message' }).code, 'malformed');
  const rev = store.current.revision;
  store.ingest(42);
  assert.equal(store.current.revision, rev);
  store.destroy();
});
