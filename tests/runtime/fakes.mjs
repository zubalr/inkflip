// TEST-11 helpers (fixture family F20): controlled fake readers and
// process faults — scripted jobs that emit real contract WorkerMessages
// through the coordinator's admission path, plus instrumented resources,
// a manual scheduler and a manual clock. Nothing here is product code;
// fakes exist so crash/hang/cancel/stale behaviour is exercised honestly.
import { normalize } from '../../packages/contracts/src/index.ts';
import { MessageFactory } from '../../packages/runtime/src/index.ts';

export const DOC_A = 'a'.repeat(64);
export const DOC_B = 'b'.repeat(64);
export const RUN_1 = 'c'.repeat(64);
export const RUN_2 = 'd'.repeat(64);

export function makeDoc(sha256 = DOC_A, pageCount = 4) {
  return { sha256, page_count: pageCount };
}

/** Drive idle -> validating_file -> loading_metadata -> selecting. */
export function openDocument(coord, sha256 = DOC_A, pageCount = 4) {
  coord.openFile();
  coord.fileValidated();
  coord.metadataLoaded(makeDoc(sha256, pageCount));
}

export function makeCheck(id, pageIndex, capability = 'native_text') {
  return {
    id,
    page_index: pageIndex,
    reader_ids: ['r_test'],
    capability,
    region_id: null,
  };
}

let occCounter = 0;
export function makeOccurrences(n, checkPage = 0, prefix = 'o') {
  const out = [];
  for (let i = 0; i < n; i++) {
    const ordinal = occCounter++;
    const raw = `synthetic reading ${ordinal}`;
    const nm = normalize(raw);
    out.push({
      id: `${prefix}_${ordinal}`,
      reader_id: 'r_test',
      page_index: checkPage,
      ordinal,
      raw_text: raw,
      normalized_text: nm.text,
      normalization_map: nm.map,
      geometry: {
        precision: 'page_only',
        space: 'canonical_page',
        polygon: null,
        transform_ids: [],
        basis: 'test fixture occurrence',
      },
      engine_score: null,
      source_asset_id: null,
      raw_source_locator: `fixture locator ${ordinal}`,
      limitations: [],
    });
  }
  return out;
}

/**
 * Worker-side sender for one job: stamps the real five-tuple identity
 * and allocates strictly increasing seq values exactly like a worker.
 */
export function workerSender(coord, jobId, documentSha256, runKey) {
  return new MessageFactory({
    generation: coord.currentGeneration,
    documentSha256,
    runKey,
    jobId,
  });
}

/** Start a run and return {jobId -> checkId} from dispatch intents. */
export function startRun(coord, checks, options = {}) {
  coord.startRun({
    runKey: options.runKey ?? RUN_1,
    checks,
    selectedPagesTotal: options.selectedPagesTotal ?? 2,
    budgetMs: options.budgetMs ?? 120000,
    ...(options.dependencies !== undefined
      ? { dependencies: options.dependencies }
      : {}),
    ...(options.needsAssets !== undefined
      ? { needsAssets: options.needsAssets }
      : {}),
  });
  return dispatchMap(coord);
}

/** Drain outbox and keep only dispatch intents as {jobId, checkId}. */
export function dispatchMap(coord) {
  const map = new Map();
  for (const intent of coord.drainOutbox()) {
    if (intent.type === 'dispatch') map.set(intent.jobId, intent.checkId);
  }
  return map;
}

/** All intents drained since last call (dispatch/terminate/ack/message). */
export function drain(coord) {
  return coord.drainOutbox();
}

/** A resource that records which teardown verbs were invoked. */
export function instrumentedResource(verbs = ['terminate', 'close']) {
  const calls = [];
  const resource = { calls };
  for (const verb of verbs) {
    resource[verb] = () => calls.push(verb);
  }
  return resource;
}

/** Manual scheduler: queued timers fire only when told to. */
export function manualScheduler() {
  let next = 0;
  const pending = new Map();
  return {
    pending,
    schedule(fn, ms) {
      const id = ++next;
      pending.set(id, { fn, ms });
      return id;
    },
    unschedule(id) {
      pending.delete(id);
    },
    fire(id) {
      const entry = pending.get(id);
      if (entry) {
        pending.delete(id);
        entry.fn();
      }
    },
    fireAll() {
      for (const [id] of [...pending]) this.fire(id);
    },
    count() {
      return pending.size;
    },
  };
}

/** Manual clock: `now()` returns t; `advance(ms)` moves it. */
export function manualClock(t0 = 1000) {
  let t = t0;
  return {
    now: () => t,
    advance: (ms) => {
      t += ms;
    },
    set: (v) => {
      t = v;
    },
  };
}
