# pdf-q38 language-payload repair

Astra owns this narrow dependency follow-up from published main `a4f1069e763fb9769aac421331b91de1fed67837`. Implementation remains pending independent review; this evidence does not accept T02 or T10.

The prior coordinator direction to pass verified model bytes with `cacheMethod: none` was wrong for unmodified Tesseract 7.0.0. The installed source and the [pinned upstream worker](https://github.com/naptha/tesseract.js/blob/v7.0.0/src/worker-script/index.js) agree: `loadLanguage` consumes object `data` as file bytes, but `initialize` also interprets `data` as the language name. The existing client forwards the same objects to both operations. T10's interim cache workaround remains unapproved as exact model-byte provenance.

The maintained Bun patch now normalizes language objects to their codes only in the existing client `initializeInternal` payload. `loadLanguage` still receives the original objects and byte arrays. The same path handles initial creation and reinitialization; string languages remain unchanged. No staged worker, core, model, protocol, package version, or type declaration changed in this follow-up. The earlier cancellation repair remains intact. T10 can therefore pass `[{code: language, data: verifiedBytes}]` with `cacheMethod: none` after independent review and integration.

## Verification before the source checkpoint

- Frozen installation succeeded, and the existing 11 constructor tests passed before edits.
- Three new/strengthened language-payload assertions failed on the prior installed constructor: object initialization, mixed languages, and object reinitialization. The existing lifecycle cases and string-language control passed. The revised suite passes all 14 cases.
- Two real-browser tests load the unchanged staged worker, actual core, and exact pinned English model. Both initialization and reinitialization succeed, and reads from the engine's own virtual filesystem hash to the pinned SHA-256. One worker has IndexedDB unavailable; the other has an explicitly corrupt cache slot. Each case observes exactly one model preparation fetch, no worker model download, and no remote request. A second preparation response would contain corrupt bytes.
- The registered build suite passed all 49 Python cases, including the constructor, browser lifecycle, and real model suites and the environment-override sentinel. Verify passed 49 bootstrap + 2 native-bootstrap + 64 coordination cases (115 total).
- The first frozen-check invocation used a nonexistent flag and failed before executing checks (`frozen-command-attempt.log`). The corrected `--frozen` command passed 25 checks (`frozen.log`). This invocation error is not a product failure.

Bun 1.4.0's patch generator included an internal empty `.bun-tag` hunk. Only that generated cache-marker hunk was removed; the maintained patch still targets exactly `src/createWorker.js` and the previously patched `src/index.d.ts`. The dependency checker enforces this inventory and both installed source hashes. The package manifest and lock remained byte-identical because the existing patch path did not change. A fresh frozen install succeeded after the patch update. Committed-candidate verification follows below; raw earlier logs retain their actual runs.
