/**
 * App state surface (T11): the session store that binds the runtime
 * lifecycle coordinator to the UI. See `./store.ts`.
 */
// Extensionless specifier: bundler/Vite resolution. `apps/web` cannot
// yet typecheck `.ts` import specifiers (no allowImportingTsExtensions
// in its tsconfig); tests import `./store.ts` directly under Node.
export {
  SessionStore,
  type AdmissionLike,
  type SessionViewCore,
  type StoreHost,
} from './store';
