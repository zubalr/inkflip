/**
 * Narrow ReadableStream async-iteration adapter for runtimes (WebKit/Safari)
 * that construct ReadableStream but omit
 * ReadableStream.prototype[Symbol.asyncIterator].
 *
 * pdf.js 6.x `getTextContent` uses `for await` over `sendWithStream`.
 * This module does **not** install a global prototype polyfill: callers
 * wrap a concrete stream (or use `streamTextContent` when the native
 * iterator is absent) so native implementations stay untouched.
 *
 * Iterator semantics follow the WHATWG Streams `values()` / async iterator
 * algorithm: exhaustion releases the lock without cancel; `return()`
 * cancels unless `preventCancel` is set; a rejected `read()` releases the
 * lock and rethrows.
 */

export type ReadableStreamIteratorOptions = {
  preventCancel?: boolean;
};

type StreamCtor = {
  prototype: {
    [Symbol.asyncIterator]?: (options?: ReadableStreamIteratorOptions) => AsyncIterator<unknown>;
    values?: (options?: ReadableStreamIteratorOptions) => AsyncIterableIterator<unknown>;
  };
};

function readableStreamConstructor(
  global: typeof globalThis = globalThis,
): StreamCtor | undefined {
  const streamCtor = (global as typeof globalThis & { ReadableStream?: StreamCtor }).ReadableStream;
  return typeof streamCtor === 'function' ? streamCtor : undefined;
}

export function hasNativeReadableStreamAsyncIterator(
  global: typeof globalThis = globalThis,
): boolean {
  const streamCtor = readableStreamConstructor(global);
  return typeof streamCtor?.prototype[Symbol.asyncIterator] === 'function';
}

/**
 * Historical name. Never mutates `ReadableStream.prototype`.
 * Returns true when the runtime already provides a native iterator
 * (no adapter needed). Returns false when callers must wrap streams.
 */
export function ensureReadableStreamAsyncIterator(
  global: typeof globalThis = globalThis,
): boolean {
  return hasNativeReadableStreamAsyncIterator(global);
}

export function isReadableStreamTypeError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /readablestream/i.test(message);
}

function releaseReader(reader: ReadableStreamDefaultReader<unknown>): void {
  try {
    reader.releaseLock();
  } catch {
    // Already released by cancel(), a prior return(), or a concurrent next().
  }
}

export function createReadableStreamAsyncIterator<T>(
  stream: ReadableStream<T>,
  options: ReadableStreamIteratorOptions = {},
): AsyncIterator<T, undefined> {
  const preventCancel = options.preventCancel === true;
  const reader = stream.getReader();
  let finished = false;
  let pending: Promise<IteratorResult<T, undefined>> | null = null;

  const settleDone = async (cancelReason: unknown, shouldCancel: boolean): Promise<IteratorResult<T, undefined>> => {
    if (finished) {
      return { done: true as const, value: undefined };
    }
    finished = true;
    try {
      if (shouldCancel && !preventCancel) {
        await reader.cancel(cancelReason);
      }
    } finally {
      releaseReader(reader);
    }
    return { done: true as const, value: undefined };
  };

  const iterator: AsyncIterator<T, undefined> = {
    async next() {
      if (finished) {
        return { done: true as const, value: undefined };
      }
      const run = (async (): Promise<IteratorResult<T, undefined>> => {
        try {
          const result = await reader.read();
          if (finished) {
            return { done: true as const, value: undefined };
          }
          if (result.done) {
            return settleDone(undefined, false);
          }
          return { done: false as const, value: result.value as T };
        } catch (error) {
          finished = true;
          releaseReader(reader);
          throw error;
        }
      })();
      pending = run;
      try {
        return await run;
      } finally {
        if (pending === run) pending = null;
      }
    },
    async return(value?: unknown) {
      const done = settleDone(value, true);
      if (pending) {
        try {
          await pending;
        } catch {
          // Cancel unblocks a pending read; the rejection is the iterator's.
        }
      }
      await done;
      return { done: true as const, value: undefined };
    },
  };
  return iterator;
}

function isAsyncIterable<T>(value: object): value is AsyncIterable<T> {
  return typeof (value as { [Symbol.asyncIterator]?: unknown })[Symbol.asyncIterator] === 'function';
}

/**
 * Prefer the stream's own async iterator when present (including native
 * `ReadableStream.prototype.values`). Otherwise return a per-stream adapter
 * that does not modify the global prototype.
 */
export function asReadableStreamAsyncIterable<T>(
  stream: ReadableStream<T> | AsyncIterable<T>,
  options: ReadableStreamIteratorOptions = {},
): AsyncIterable<T> {
  if (options.preventCancel === true) {
    const withValues = stream as ReadableStream<T> & {
      values?: (opts?: ReadableStreamIteratorOptions) => AsyncIterableIterator<T>;
    };
    if (typeof withValues.values === 'function') {
      return withValues.values({ preventCancel: true });
    }
  } else if (isAsyncIterable<T>(stream)) {
    return stream;
  }
  const iterator = createReadableStreamAsyncIterator(stream as ReadableStream<T>, options);
  return {
    [Symbol.asyncIterator]() {
      return iterator;
    },
  };
}
