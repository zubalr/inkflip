import { test } from "node:test";
import assert from "node:assert/strict";
import { ensureReadableStreamAsyncIterator } from "../../packages/readers-pdfjs/src/streams.ts";

test("installs ReadableStream async iterator when the runtime omitted it", async () => {
  const chunks = [];
  const original = ReadableStream.prototype[Symbol.asyncIterator];
  try {
    // Simulate WebKit: construct streams, but for-await is missing.
    // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
    delete ReadableStream.prototype[Symbol.asyncIterator];
    assert.equal(typeof ReadableStream.prototype[Symbol.asyncIterator], "undefined");
    const installed = ensureReadableStreamAsyncIterator();
    assert.equal(installed, true);
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue({ items: [{ str: "A" }], styles: {}, lang: "en" });
        controller.close();
      },
    });
    for await (const value of stream) {
      chunks.push(value);
    }
    assert.equal(chunks.length, 1);
    assert.equal(chunks[0].items[0].str, "A");
  } finally {
    if (original) {
      ReadableStream.prototype[Symbol.asyncIterator] = original;
    }
  }
});
