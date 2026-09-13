# T46 handoff

- **Task:** T46 browser/native parity (`pdf-t46`)
- **Branch:** `work/cursor/native-assurance`
- **Base:** `78750769d1a29d58b7b79f91c1c8ffd749dc4eac`
- **Implementation commit:** `f4f31fc0bcaf15cdac5342a378ed4db2dd5edb35`
- **Depends on T40 source:** `efa11d4b97ec94b732216524aea4f405b629821f` only as branch ancestor; no T40 runtime dependency
- **Tests:** `node --test tests/parity/*.test.mjs` → **8 passed**; `python3 scripts/check_manual_receipts.py compatibility` → ok
- **Review:** pending
- **Unresolved:** Chromium/Firefox/WebKit GUI and Linux amd64 not executed. Shared `scripts/check_manual_receipts.py` needs coordinator lease (`docs/proposals/T46.md`).
