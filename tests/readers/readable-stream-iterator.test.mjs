import { test } from "node:test";
import assert from "node:assert/strict";
import {
  asReadableStreamAsyncIterable,
  createReadableStreamAsyncIterator,
  ensureReadableStreamAsyncIterator,
  hasNativeReadableStreamAsyncIterator,
} from "../../packages/readers-pdfjs/src/streams.ts";

class BareReadableStream extends ReadableStream {}
delete BareReadableStream.prototype[Symbol.asyncIterator];
if (typeof BareReadableStream.prototype.values === "function") {
  delete BareReadableStream.prototype.values;
}

function makeChunks(chunks, { errorAt = -1, cancelProbe } = {}) {
  let i = 0;
  return new BareReadableStream({
    start(controller) {
      if (errorAt === 0) {
        controller.error(new Error("read-reject"));
        return;
      }
    },
    pull(controller) {
      if (errorAt >= 0 && i === errorAt) {
        controller.error(new Error("read-reject"));
        return;
      }
      if (i >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(chunks[i]);
      i += 1;
    },
    cancel(reason) {
      if (cancelProbe) cancelProbe.cancelled = true;
      cancelProbe && (cancelProbe.reason = reason);
    },
  });
}

test("does not replace a native ReadableStream async iterator", () => {
  const original = ReadableStream.prototype[Symbol.asyncIterator];
  assert.equal(typeof original, "function");
  const before = hasNativeReadableStreamAsyncIterator();
  const reported = ensureReadableStreamAsyncIterator();
  assert.equal(before, true);
  assert.equal(reported, true);
  assert.equal(ReadableStream.prototype[Symbol.asyncIterator], original);
});

test("exhaustion releases the lock without cancel", async () => {
  const probe = { cancelled: false };
  const stream = makeChunks(["A", "B"], { cancelProbe: probe });
  const got = [];
  for await (const value of asReadableStreamAsyncIterable(stream)) {
    got.push(value);
  }
  assert.deepEqual(got, ["A", "B"]);
  assert.equal(stream.locked, false);
  assert.equal(probe.cancelled, false);
});

test("read rejection releases the lock", async () => {
  const stream = makeChunks([], { errorAt: 0 });
  const iterable = asReadableStreamAsyncIterable(stream);
  await assert.rejects(async () => {
    for await (const _ of iterable) {
      /* drain */
    }
  }, /read-reject/);
  assert.equal(stream.locked, false, "error_stream_still_locked must be false after repair");
});

test("early break cancels unless preventCancel is set", async () => {
  const cancelDefault = { cancelled: false };
  const stream = makeChunks(["a", "b", "c"], { cancelProbe: cancelDefault });
  for await (const value of asReadableStreamAsyncIterable(stream)) {
    if (value === "a") break;
  }
  assert.equal(cancelDefault.cancelled, true, "early_return_cancelled must be true after repair");
  assert.equal(stream.locked, false);

  const cancelPrevented = { cancelled: false };
  const held = makeChunks(["a", "b"], { cancelProbe: cancelPrevented });
  const iter = createReadableStreamAsyncIterator(held, { preventCancel: true });
  const first = await iter.next();
  assert.equal(first.value, "a");
  await iter.return();
  assert.equal(cancelPrevented.cancelled, false);
  assert.equal(held.locked, false);
});

test("repeated next/return after completion stay done", async () => {
  const stream = makeChunks(["only"]);
  const iter = createReadableStreamAsyncIterator(stream);
  const a = await iter.next();
  const b = await iter.next();
  const c = await iter.next();
  const d = await iter.return();
  const e = await iter.return();
  assert.deepEqual(a, { done: false, value: "only" });
  assert.equal(b.done, true);
  assert.equal(c.done, true);
  assert.equal(d.done, true);
  assert.equal(e.done, true);
  assert.equal(stream.locked, false);
});

test("REVIEW.md reproduction is inverted after the adapter repair", async () => {
  const cancelProbe = { cancelled: false };
  const early = makeChunks(["a", "b"], { cancelProbe });
  for await (const value of asReadableStreamAsyncIterable(early)) {
    if (value === "a") break;
  }
  const errorStream = makeChunks([], { errorAt: 0 });
  let errorLocked = true;
  try {
    for await (const _ of asReadableStreamAsyncIterable(errorStream)) {
      /* drain */
    }
  } catch {
    errorLocked = errorStream.locked;
  }
  assert.deepEqual(
    {
      early_return_cancelled: cancelProbe.cancelled,
      error_stream_still_locked: errorLocked,
    },
    { early_return_cancelled: true, error_stream_still_locked: false },
  );
});
