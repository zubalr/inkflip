# Application-artifact interface for the native image (ZCode)

Cursor owns native assembly and the notices that land in the **built
image**. ZCode owns `scripts/check_distribution.py` and the public
distribution manifest. This file is the local source/hash interface for
the application wheel so ZCode can add an application-wheel field without
Cursor editing those active files.

## Produced locally by `python3 scripts/distribution/assemble_native_image.py`

| File | Purpose |
| --- | --- |
| `native/dist/app.wheel.json` | filename, sha256, bytes, lock line for `inkflip==0.0.0` |
| `native/dist/wheels/inkflip-*-py3-none-any.whl` | the wheel bytes (rebuilds change the hash) |
| `native/dist/requirements.lock` | third-party pins plus `inkflip==0.0.0 --hash=sha256:…` |
| `native/dist/notices/INDEX.json` | required notice ids: `inkflip-mit`, `pdfium-binary-appendix`, `node-license` |
| `native/dist/BUILD-CONTEXT.json` | platform/ABI, wheel list, notice index |

## Proposed shared manifest field (ZCode edit)

Add an application-wheel object, for example:

```json
{
  "application_wheel": {
    "name": "inkflip",
    "version": "0.0.0",
    "filename": "inkflip-0.0.0-py3-none-any.whl",
    "sha256": "<from native/dist/app.wheel.json>",
    "wheel_tag": "py3-none-any",
    "notice": "NOTICE",
    "notices_index": "native/dist/notices/INDEX.json"
  }
}
```

Do not treat a substring mention of `inkflip` in a lock file as the wheel.
`scripts/check_native_image_inputs.py` already requires a hashed
`inkflip==` pin and a real PEP 427 tagged wheel.

The committed `release/native-requirements.lock` stays third-party-only until
ZCode owns that manifest change (`check_distribution.py` would otherwise
reject an unexpected package).
