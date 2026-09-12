/**
 * Runtime lifecycle error surface (T11).
 *
 * Distinct from `ContractError` in `@inkflip/contracts`: contract errors
 * describe untrusted data that failed validation; a `RuntimeError`
 * describes a lifecycle protocol violation by the local embedder or a
 * worker (illegal transition, terminal mutation, unknown job).
 * Every rejection carries a stable machine-readable `code`.
 */
export class RuntimeError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(`${code}: ${message}`);
    this.name = 'RuntimeError';
    this.code = code;
  }
}

export function requireRuntime(
  condition: boolean,
  code: string,
  message: string,
): asserts condition {
  if (!condition) throw new RuntimeError(code, message);
}
