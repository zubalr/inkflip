# macOS-native Tesseract (2026-09-13 Mac release)

On this Mac, host CLI OCR uses Homebrew Tesseract plus the pinned English
model. The production linux/amd64 image packages a hashed Debian
`tesseract-ocr` 5.5.0 closure and the same pinned `eng.traineddata`.
Apple Silicon `docker build --platform linux/amd64` is qemu emulation —
not native x86_64 hardware certification (deferred).

## Runtime

- Executable: `/opt/homebrew/bin/tesseract` (Homebrew `tesseract` 5.5.3 on this host)
- Model: `apps/web/public/models/tessdata-fast-eng/7d4322bd/eng.traineddata`
  (digest `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`)
- `TESSDATA_PREFIX` must point at the directory that contains `eng.traineddata`

## Commands

```sh
export TESSDATA_PREFIX="apps/web/public/models/tessdata-fast-eng/7d4322bd"
native/.venv/bin/python -m inkflip.cli inspect fixtures/public/mapping-control.pdf \
  --reader tesseract --ocr-pages 1 --out /tmp/inkflip-ocr.json --replace-output
```

`scripts/measure_performance.py` sets `TESSDATA_PREFIX` to the pinned model
when present and records `ocr_cli` timings. That is a macOS host measurement,
not linux/amd64 image proof.

## Packaging note

Install Tesseract from Homebrew on Apple Silicon:

```sh
brew install tesseract
```

Do not copy that Darwin binary into a Linux container. The production image
installs the hashed Debian amd64 debs from `native/dist/tesseract/debs`
offline (`dpkg -i`; no `apt-get` in the image).
