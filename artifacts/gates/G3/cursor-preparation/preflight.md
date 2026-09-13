# G3 cursor preparation (not a gate receipt)

Branch `work/cursor/native-assurance` at T52 source
`95438c95fc36c5e10052119829b147a24d2c6fad`, based on the published T35 repair
checkpoint `78750769d1a29d58b7b79f91c1c8ffd749dc4eac`.

## Preflight command

```sh
uv run --project native python -m pytest native/tests/gates -q
```

Result: **6 passed**. Scenarios cover inspect/named readers, corpus partial
failure/resume, immutable baseline + declared regression (exit 5), HTML
report transfer identities, documented exit-code constants, and the local
reader-upgrade script presence.

HTML transfer and browser reopen of `inspect.html` (named pypdf inspect,
`chk_pypdf_text_p0`) and `comparison.html` (declared regression) are recorded
in `browser-reopen.md` with screenshots bound to those file SHA-256 values.

## Not done here

`python scripts/gate.py G3` is the authoritative G3 run. It still requires
accepted Beads receipts for T26–T35. This directory is preparation evidence
only. No manufactured acceptance receipt.
