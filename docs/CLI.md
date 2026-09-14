# Native CLI

The native command is `inkflip`. In this checkout run it as
`PYTHONPATH=native python -m inkflip.cli` after putting `native/.venv/bin` on
`PATH`, or through `examples/reader-upgrade/bin/inkflip` after putting that
directory and the frozen interpreter directory on `PATH`. The frozen venv
supplies the local `python` name; do not create a global `python` alias.

Source and output paths are local files only. Remote URL sources are refused.
An output path that aliases the source, including a symlink or hard link, is
refused even with `--replace-output`. Existing outputs also require
`--replace-output`. Baseline creation never overwrites.

Page numbers are 1-based. `--pages all` is allowed up to the native page cap
and does not imply OCR. `--ocr-pages` is required for OCR, limited to 20 pages.
`--region x0,y0,x1,y1` is canonical unrotated physical points and requires
exactly one selected page. Named profiles are trusted installed names, not
paths or commands. Missing named profiles fail closed; there is no silent
PDFium fallback.

## Commands

```sh
inkflip readers list --json
inkflip inspect FILE --out REPORT [--reader pdfium|pypdf|tesseract] [--pages 1] [--ocr-pages PAGES] [--region x0,y0,x1,y1] [--profile native-default] [--embed-source]
inkflip compare-readers FILE --readers A,B --out DIR
inkflip models prepare --manifest FILE [--cache DIR]
inkflip corpus run --manifest FILE --source-root DIR --profile ID --out DIR [--jobs 1] [--resume]
inkflip baseline create --run DIR --rules FILE --out FILE --approved-by LABEL --rationale TEXT
inkflip compare LEFT RIGHT --out DIR [--rules FILE] [--mode reader_upgrade] [--fail-on changed]
inkflip report REPORT --format html --out FILE
inkflip replay REPORT --source FILE --profile ID --out FILE
inkflip validate REPORT
```

`--embed-source` includes the original document bytes inside the exported
report, enabling `replay` on another machine without the source file. It
increases report size and means the report carries a copy of the document —
treat the exported file with the same care as the original PDF.
`--reader tesseract` requires `--ocr-pages`. Model preparation copies
allowlisted files after digest verification; `{}` is not a ready cache.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Completed under the declared policy. Unruled reading differences stay informational. |
| 2 | Invalid arguments, configuration, or imported contract. |
| 3 | Partial run or unavailable requested capability; evidence is retained. |
| 4 | No successful result (runtime or read failure). |
| 5 | Declared acceptance rule failed, or `--fail-on changed`. |
| 6 | Incomparable runs. |
| 130 | Cancellation. |

Replay reconstructs the recorded pages, OCR pages and region. It refuses a
source hash mismatch and a reader version or named-profile mismatch.

HTML export uses `core.validate` and emits script-free HTML with a CSP.
