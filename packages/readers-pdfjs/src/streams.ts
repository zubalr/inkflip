/**
 * WebKit/Safari may construct ReadableStream but omit
 * ReadableStream.prototype[Symbol.asyncIterator]. pdf.js 6.x
 * `getTextContent` uses `for await` over `sendWithStream`'s ReadableStream,
 * which then throws TypeError. Installing the iterator is a harness/adapter
 * repair, not a text mock and not a fake worker.
 */
export function ensureReadableStreamAsyncIterator(
  global: typeof globalThis = globalThis,
): boolean {
  const streamCtor = (global as typeof globalThis & { ReadableStream?: typeof ReadableStream })
    .ReadableStream;
  if (typeof streamCtor !== 'function') return false;
  const proto = streamCtor.prototype as ReadableStream<unknown> & {
    [Symbol.asyncIterator]?: () => AsyncIterator<unknown>;
  };
  if (typeof proto[Symbol.asyncIterator] === 'function') return false;
  Object.defineProperty(proto, Symbol.asyncIterator, {
    configurable: true,
    writable: true,
    value: function readableStreamAsyncIterator(
      this: ReadableStream<unknown>,
    ): AsyncIterator<unknown, undefined> {
      const reader = this.getReader();
      return {
        async next() {
          const result = await reader.read();
          if (result.done) {
            reader.releaseLock();
            return { done: true as const, value: undefined };
          }
          return { done: false as const, value: result.value };
        },
        async return() {
          reader.releaseLock();
          return { done: true as const, value: undefined };
        },
      };
    },
  });
  return true;
}

export function isReadableStreamTypeError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /readablestream/i.test(message);
}
