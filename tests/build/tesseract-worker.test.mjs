import assert from 'node:assert/strict';
import { getEventListeners } from 'node:events';
import { readFileSync, realpathSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');
const packageRoot = realpathSync(process.env.INKFLIP_TEST_TESSERACT_PACKAGE ?? join(root, 'apps/web/node_modules/tesseract.js'));
const sourcePath = join(packageRoot, 'src/createWorker.js');
const source = readFileSync(sourcePath, 'utf8');
const upstreamRequire = createRequire(sourcePath);

// Execute the installed constructor. Replace only its owned transport boundary;
// jobs, initialization sequencing, rejection and cancellation stay production code.
function harness({ stall, reject, image } = {}) {
  const workers = [];
  const messages = [];
  const progress = [];
  const transport = {
    defaultOptions: { logger: (message) => progress.push(message) },
    spawnWorker: () => {
      const worker = { terminated: 0, handler: null };
      workers.push(worker);
      return worker;
    },
    terminateWorker: (worker) => { worker.terminated += 1; },
    onMessage: (worker, handler) => { worker.handler = handler; },
    loadImage: () => image ?? Promise.resolve(new Uint8Array([1])),
    send: (worker, message) => {
      assert.equal(worker.terminated, 0, 'must not send to a terminated transport');
      messages.push(message);
      if (message.action === stall) return;
      queueMicrotask(() => worker.handler({
        ...message,
        status: message.action === reject ? 'reject' : 'resolve',
        data: message.action === reject ? 'initialization rejected' : { text: 'control' },
      }));
    },
  };
  const module = { exports: {} };
  vm.runInNewContext(source, {
    module, console,
    require: (path) => path === './worker/node' ? transport : upstreamRequire(path),
  }, { filename: sourcePath });
  return { createWorker: module.exports, workers, messages, progress };
}

async function until(predicate) {
  for (let turn = 0; turn < 30; turn += 1) {
    if (predicate()) return;
    await Promise.resolve();
  }
  assert.fail('expected constructor stage was never reached');
}

test('already aborted signal prevents worker creation', { timeout: 1000 }, async () => {
  const h = harness();
  const controller = new AbortController();
  const reason = new Error('cancel before spawn');
  controller.abort(reason);
  await assert.rejects(h.createWorker('eng', 1, { signal: controller.signal }), (e) => e === reason);
  assert.equal(h.workers.length, 0);
});

for (const stage of ['load', 'loadLanguage', 'initialize']) {
  test(`abort physically terminates a stalled ${stage} and settles readiness`, { timeout: 1000 }, async () => {
    const h = harness({ stall: stage });
    const controller = new AbortController();
    const reason = new Error(`cancel ${stage}`);
    const ready = h.createWorker('eng', 1, { signal: controller.signal });
    const rejected = assert.rejects(ready, (e) => e === reason);
    await until(() => h.messages.some((m) => m.action === stage));
    controller.abort(reason);
    assert.equal(h.workers[0].terminated, 1, 'termination is synchronous, before readiness can settle');
    await rejected;
    assert.equal(getEventListeners(controller.signal, 'abort').length, 0);
    const count = h.messages.length;
    h.workers[0].handler({ ...h.messages.at(-1), status: 'resolve', data: {} });
    h.workers[0].handler({ status: 'progress', data: { status: 'late', progress: 1 } });
    await Promise.resolve();
    assert.equal(h.messages.length, count, 'late success cannot advance initialization');
    assert.equal(h.progress.length, 0, 'late progress is ignored');
  });

  test(`${stage} rejection releases the worker and settles readiness`, { timeout: 1000 }, async () => {
    const h = harness({ reject: stage });
    const controller = new AbortController();
    await assert.rejects(h.createWorker('eng', 1, { signal: controller.signal }), (e) => e === 'initialization rejected');
    assert.equal(h.workers[0].terminated, 1);
    assert.equal(getEventListeners(controller.signal, 'abort').length, 0);
  });
}

test('raw worker error rejects initialization and releases its transport', { timeout: 1000 }, async () => {
  const h = harness({ stall: 'initialize' });
  const ready = h.createWorker();
  const rejected = assert.rejects(ready, /raw worker failed/);
  await until(() => h.messages.some((m) => m.action === 'initialize'));
  h.workers[0].onerror({ message: 'raw worker failed' });
  await rejected;
  assert.equal(h.workers[0].terminated, 1);
});

test('termination rejects an outstanding job and is idempotent', { timeout: 1000 }, async () => {
  const h = harness({ stall: 'recognize' });
  const controller = new AbortController();
  const worker = await h.createWorker('eng', 1, { signal: controller.signal });
  const job = worker.recognize(new Uint8Array([1]));
  const rejected = assert.rejects(job, /terminated/);
  await until(() => h.messages.some((m) => m.action === 'recognize'));
  await worker.terminate();
  await rejected;
  await worker.terminate();
  controller.abort();
  assert.equal(h.workers[0].terminated, 1);
  assert.equal(getEventListeners(controller.signal, 'abort').length, 0);
});

test('delayed image loading cannot send a new job after cancellation', { timeout: 1000 }, async () => {
  let releaseImage;
  const h = harness({ image: new Promise((resolve) => { releaseImage = resolve; }) });
  const controller = new AbortController();
  const worker = await h.createWorker('eng', 1, { signal: controller.signal });
  const reason = new Error('cancel image loading');
  const job = worker.recognize('delayed input');
  const rejected = assert.rejects(job, (e) => e === reason);
  controller.abort(reason);
  releaseImage(new Uint8Array([1]));
  await rejected;
  assert.equal(h.messages.filter((m) => m.action === 'recognize').length, 0);
  assert.equal(h.workers[0].terminated, 1);
});

test('successful initialization and recognition preserve the existing protocol', { timeout: 1000 }, async () => {
  const h = harness();
  const worker = await h.createWorker([{ code: 'eng', data: new Uint8Array([4, 5]) }], 1);
  assert.deepEqual(h.messages.map((m) => m.action), ['load', 'loadLanguage', 'initialize']);
  const result = await worker.recognize(new Uint8Array([1]), {}, { text: true });
  assert.equal(result.data.text, 'control');
  assert.deepEqual(Array.from(h.messages[1].payload.langs[0].data), [4, 5]);
  assert.equal(h.messages[2].payload.langs, 'eng', 'initialize receives the language code, never model bytes');
  await worker.terminate();
  assert.equal(h.workers[0].terminated, 1);
});

test('mixed language payloads keep bytes for loading and codes for initialization', { timeout: 1000 }, async () => {
  const h = harness();
  const langs = ['eng', { code: 'ara', data: new Uint8Array([4, 5, 6]) }];
  const worker = await h.createWorker(langs, 1);
  assert.equal(h.messages[1].payload.langs, langs, 'loading retains the original payloads');
  assert.equal(h.messages[2].payload.langs, 'eng+ara');
  assert.deepEqual(Array.from(langs[1].data), [4, 5, 6], 'initialization does not mutate supplied bytes');
  await worker.terminate();
});

test('reinitialization normalizes new object payloads without changing their model bytes', { timeout: 1000 }, async () => {
  const h = harness();
  const worker = await h.createWorker('eng', 1);
  const langs = ['eng', { code: 'ara', data: new Uint8Array([7, 8]) }];
  await worker.reinitialize(langs, 1);
  const loads = h.messages.filter((m) => m.action === 'loadLanguage');
  assert.equal(loads.length, 2);
  assert.equal(loads[1].payload.langs.length, 1);
  assert.equal(loads[1].payload.langs[0], langs[1]);
  assert.equal(h.messages.at(-1).payload.langs, 'eng+ara');
  await worker.terminate();
});

test('string language initialization remains unchanged', { timeout: 1000 }, async () => {
  const h = harness();
  const worker = await h.createWorker('eng+ara', 1);
  assert.equal(h.messages[1].payload.langs, 'eng+ara');
  assert.equal(h.messages[2].payload.langs, 'eng+ara');
  await worker.reinitialize('eng+ara', 1);
  assert.equal(h.messages.at(-1).payload.langs, 'eng+ara');
  await worker.terminate();
});
